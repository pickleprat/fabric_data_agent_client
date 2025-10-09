#!/usr/bin/env python3
"""
Fabric Data Agent External Client

A standalone Python client for calling Microsoft Fabric Data Agents from outside
of the Fabric environment using interactive browser authentication.

Requirements:
- azure-identity
- openai
- python-dotenv (optional, for environment variables)

Usage:
1. Set your TENANT_ID and DATA_AGENT_URL in the script or environment variables
2. Run the script - it will open a browser for authentication
3. The client will fetch a bearer token and make calls to your data agent
"""

import time
import uuid
import os
import warnings
from typing import Optional
from azure.identity import InteractiveBrowserCredential
from openai import OpenAI
from dotenv import load_dotenv
import json 
import re 

# Suppress OpenAI Assistants API deprecation warnings
# (Fabric Data Agents don't support the newer Responses API yet)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*Assistants API is deprecated.*"
)

# Optional: Load from .env file if available
try:
    load_dotenv()
except ImportError:
    pass


class FabricDataAgentClient:
    """
    Client for calling Microsoft Fabric Data Agents from external applications.
    
    This client handles:
    - Interactive browser authentication with Azure AD
    - Automatic token refresh
    - Bearer token management for API calls
    - Proper cleanup of resources
    """
    
    def __init__(self, 
        tenant_id: str, 
        data_agent_url: str, 
        auth_token: Optional[str] = None, 
        enable_cache: bool = False, 
        cache_ttl: Optional[int] = None):
        """
        Initialize the Fabric Data Agent client.
        
        Args:
            tenant_id (str): Your Azure tenant ID
            data_agent_url (str): The published URL of your Fabric Data Agent
            auth_token (str, optional): Authentication token for bypassing interactive authentication.
                                      If not provided, will fall back to InteractiveBrowserCredential.
        """
        self.tenant_id = tenant_id
        self.data_agent_url = data_agent_url
        self.credential = None
        self.auth_token = auth_token
        self.token = None  
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl  
        self._cache = {}
        
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not data_agent_url:
            raise ValueError("data_agent_url is required")
        
        print(f"Initializing Fabric Data Agent Client...")
        print(f"Tenant ID: {tenant_id}")
        print(f"Data Agent URL: {data_agent_url}")
        
        if auth_token:
            print(f"Auth Token: Provided (will use token-based authentication)")
        else:
            print(f"Auth Token: Not provided (will use interactive browser authentication)")
        
        self._authenticate()

    def _cache_get(self, key):
        """Retrieve cached value if caching enabled and not expired."""
        if not self.enable_cache:
            return None
        entry = self._cache.get(key)
        if not entry:
            return None
        if self.cache_ttl is not None:
            if (time.time() - entry["ts"]) > self.cache_ttl:
                # expired
                try:
                    del self._cache[key]
                except Exception:
                    pass
                return None
        return entry["value"]

    def _cache_set(self, key, value):
        """Store value in cache if enabled."""
        if not self.enable_cache:
            return
        self._cache[key] = {"ts": time.time(), "value": value}

    def _format_api_error(self, e: Exception) -> str:
        """Return a detailed string for API-related errors when possible."""
        try:
            # OpenAI v1 exceptions often include status_code and response
            status = getattr(e, "status_code", None)
            name = e.__class__.__name__
            details = str(e)
            body = None
            resp = getattr(e, "response", None)
            if resp is not None:
                try:
                    body = getattr(resp, "text", None) or getattr(resp, "content", None)
                except Exception:
                    body = None
            parts = []
            parts.append(f"Exception: {name}")
            if status is not None:
                parts.append(f"HTTP Status: {status}")
            if details:
                parts.append(f"Message: {details}")
            if body:
                # Avoid dumping extremely long payloads
                body_str = body if isinstance(body, str) else str(body)
                if len(body_str) > 4000:
                    body_str = body_str[:4000] + "... [truncated]"
                parts.append("Response Body:\n" + body_str)
            return "\n".join(parts)
        except Exception:
            return str(e)
    
    def _authenticate(self):
        """
        Authenticate using the provided auth token, with fallback to InteractiveBrowserCredential.
        """
        try:
            print("\n🔐 Starting authentication...")
            
            if self.auth_token:
                print("Using provided authentication token...")
                # Test the auth token by attempting to create a client and make a simple call
                try:
                    # We'll validate the token when we first use it in _get_openai_client
                    self.credential = None
                    print("✅ Authentication token accepted (will be validated on first use)")
                    return
                except Exception as token_error:
                    print(f"⚠️ Auth token validation failed: {token_error}")
                    print("Falling back to interactive browser authentication...")
                    # Clear the invalid token and fall through to interactive auth
                    self.auth_token = None
            
            # Use interactive browser authentication (either as primary or fallback)
            if not self.auth_token:
                print("Using interactive browser authentication...")
                print("A browser window will open for you to sign in to your Microsoft account.")
                
                self.credential = InteractiveBrowserCredential(
                    tenant_id=self.tenant_id,
                )
                
                # Get initial token for interactive auth
                self._refresh_token()
                print("✅ Interactive authentication successful!")
                
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            raise
            
    def _refresh_token(self):
        """
        Refresh the authentication token (only applicable for credential-based auth).
        """
        try:
            print("🔄 Refreshing authentication token...")
            
            if self.auth_token:
                # Using direct auth token - no refresh needed
                print("✅ Using provided auth token (no refresh required)")
                return
            
            if self.credential is None:
                raise ValueError("No credential available for token refresh")
            
            self.token = self.credential.get_token("https://api.fabric.microsoft.com/.default")
            print(f"✅ Token obtained, expires at: {time.ctime(self.token.expires_on)}")
            
        except Exception as e:
            print(f"❌ Token refresh failed: {e}")
            # If token refresh fails and we have a credential, try to fall back to interactive auth
            if self.credential is not None:
                print("🔄 Attempting to re-authenticate...")
                try:
                    self.token = self.credential.get_token("https://api.fabric.microsoft.com/.default")
                    print(f"✅ Re-authentication successful, expires at: {time.ctime(self.token.expires_on)}")
                except Exception as reauth_error:
                    print(f"❌ Re-authentication also failed: {reauth_error}")
                    raise
            else:
                raise

    def _get_openai_client(self) -> OpenAI:
        """
        Create an OpenAI client configured for Fabric Data Agent calls.
        
        Returns:
            OpenAI: Configured OpenAI client
        """
        
        if self.auth_token:
            # Using direct auth token
            bearer_token = self.auth_token
            print("🔑 Using provided auth token for API calls")
            
            # Test the token by creating a client and attempting a simple operation
            try:
                test_client = OpenAI(
                    api_key="",  # Not used - we use Bearer token
                    base_url=self.data_agent_url,
                    default_query={"api-version": "2024-05-01-preview"},
                    default_headers={
                        "Authorization": f"Bearer {bearer_token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "ActivityId": str(uuid.uuid4())
                    }
                )
                # If we get here, the token format is at least valid
                return test_client
            except Exception as token_error:
                print(f"⚠️ Auth token appears to be invalid: {token_error}")
                print("Falling back to interactive browser authentication...")
                # Clear the invalid token and fall back to credential-based auth
                self.auth_token = None
                
                # Initialize interactive credential if not already done
                if self.credential is None:
                    print("Initializing interactive browser credential...")
                    self.credential = InteractiveBrowserCredential(
                        tenant_id=self.tenant_id,
                    )
                    self._refresh_token()
        
        # Using credential-based authentication (either primary or fallback)
        if not self.auth_token:
            # Check if token needs refresh (refresh 5 minutes before expiry)
            if self.token and self.token.expires_on <= (time.time() + 300):
                self._refresh_token()
            
            if not self.token:
                if self.credential is None:
                    raise ValueError("No valid authentication method available")
                self._refresh_token()
            
            if not self.token:
                raise ValueError("No valid authentication token available")
            
            bearer_token = self.token.token
            print("🔑 Using credential-based token for API calls")
        
        return OpenAI(
            api_key="",  # Not used - we use Bearer token
            base_url=self.data_agent_url,
            default_query={"api-version": "2024-05-01-preview"},
            default_headers={
                "Authorization": f"Bearer {bearer_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "ActivityId": str(uuid.uuid4())
            }
        )
    
    def ask(self, question: str, timeout: int = 120) -> str:
        """
        Ask a question to the Fabric Data Agent.
        
        Args:
            question (str): The question to ask
            timeout (int): Maximum time to wait for response in seconds
            
        Returns:
            str: The response from the data agent
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")
        
        print(f"\n❓ Asking: {question}")
        
        try:
            # Cache check
            cache_key = ("ask", question.strip(), timeout)
            cached = self._cache_get(cache_key)
            if cached is not None:
                print("💾 Cache hit for ask()")
                return cached

            client = self._get_openai_client()
            
            # Create assistant without specifying model or instructions
            assistant = client.beta.assistants.create(model="not used")
            
            # Create thread and send message
            thread = client.beta.threads.create()
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=question
            )
            
            # Start the run
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id
            )
            
            # Monitor the run with timeout
            start_time = time.time()
            while run.status in ["queued", "in_progress"]:
                if time.time() - start_time > timeout:
                    print(f"⏰ Request timed out after {timeout} seconds")
                    break
                
                print(f"⏳ Status: {run.status}")
                time.sleep(2)
                
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
            
            print(f"✅ Final status: {run.status}")
            
            # Get the response messages
            messages = client.beta.threads.messages.list(
                thread_id=thread.id,
                order="asc"
            )
            
            # Extract assistant responses
            responses = []
            for msg in messages:
                if msg.role == "assistant":
                    try:
                        content = msg.content[0]
                        # Handle different content types safely
                        if hasattr(content, 'text'):
                            text_content = getattr(content, 'text', None)
                            if text_content is not None and hasattr(text_content, 'value'):
                                responses.append(text_content.value)
                            elif text_content is not None:
                                responses.append(str(text_content))
                            else:
                                responses.append(str(content))
                        else:
                            responses.append(str(content))
                    except (IndexError, AttributeError):
                        responses.append(str(msg.content))
            
            # Clean up resources
            try:
                client.beta.threads.delete(thread_id=thread.id)
            except Exception as cleanup_error:
                print(f"⚠️ Cleanup warning: {cleanup_error}")
            
            # Return the response
            if responses:
                result = "\n".join(responses)
                # Cache store
                self._cache_set(cache_key, result)
                return result
            else:
                return "No response received from the data agent."
        
        except Exception as e:
            detailed = self._format_api_error(e)
            print(f"❌ Error calling data agent:\n{detailed}")
            return f"Error while calling data agent:\n{detailed}"
    
    def get_run_details(self, question: str) -> dict:
        """
        Ask a question and return detailed run information including steps.
        
        Args:
            question (str): The question to ask
            
        Returns:
            dict: Detailed response including run steps, metadata, and SQL queries if lakehouse data source
        """
        print(f"\n🔍 Getting detailed run info for: {question}")
        
        try:
            # Cache check
            cache_key = ("details", question.strip())
            cached = self._cache_get(cache_key)
            if cached is not None:
                print("💾 Cache hit for get_run_details()")
                return cached

            client = self._get_openai_client()
            
            # Create assistant and thread without specifying model or instructions
            assistant = client.beta.assistants.create(model="not used")
            thread = client.beta.threads.create()
            
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=question
            )
            
            # Start and monitor run
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id
            )
            
            while run.status in ["queued", "in_progress"]:
                print(f"⏳ Status: {run.status}")
                time.sleep(2)
                run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            
            # Get detailed run steps
            steps = client.beta.threads.runs.steps.list(
                thread_id=thread.id,
                run_id=run.id
            )
            
            # Get messages
            messages = client.beta.threads.messages.list(
                thread_id=thread.id,
                order="asc"
            )
            
            # Extract SQL queries and data from steps if lakehouse data source is detected
            sql_analysis = self._extract_sql_queries_with_data(steps)
            
            # Also try the old regex method as backup
            if not sql_analysis["queries"]:
                regex_queries = self._extract_sql_queries(steps)
                if regex_queries:
                    sql_analysis["queries"] = regex_queries
                    sql_analysis["data_retrieval_query"] = regex_queries[0] if regex_queries else None
            
            # Also extract data from the final assistant message
            messages_data = messages.model_dump()
            assistant_messages = [msg for msg in messages_data.get('data', []) if msg.get('role') == 'assistant']
            if assistant_messages:
                latest_message = assistant_messages[-1]
                content = latest_message.get('content', [])
                if content and len(content) > 0:
                    # Extract text content
                    text_content = ""
                    if isinstance(content[0], dict):
                        if 'text' in content[0]:
                            if isinstance(content[0]['text'], dict) and 'value' in content[0]['text']:
                                text_content = content[0]['text']['value']
                            else:
                                text_content = str(content[0]['text'])
                    else:
                        text_content = str(content[0])
                    
                    # Extract structured data from the assistant's text response
                    if text_content:
                        text_data_preview = self._extract_data_from_text_response(text_content)
                        if text_data_preview:
                            # Add the text-based data preview
                            if sql_analysis["queries"]:
                                # If we have queries but no data previews, or empty previews, use the text-based one
                                if not sql_analysis["data_previews"] or not any(sql_analysis["data_previews"]):
                                    sql_analysis["data_previews"] = [text_data_preview]
                                else:
                                    # Add to existing previews
                                    sql_analysis["data_previews"].append(text_data_preview)
                                
                                # If we don't have a specific data retrieval query identified, use the first query
                                if not sql_analysis["data_retrieval_query"] and sql_analysis["queries"]:
                                    sql_analysis["data_retrieval_query"] = sql_analysis["queries"][0]
                                    sql_analysis["data_retrieval_query_index"] = 1
            
            # Clean up
            try:
                client.beta.threads.delete(thread_id=thread.id)
            except Exception as cleanup_error:
                print(f"⚠️ Warning: Thread cleanup failed: {cleanup_error}")
            
            result = {
                "question": question,
                "run_status": run.status,
                "run_steps": steps.model_dump(),
                "messages": messages.model_dump(),
                "timestamp": time.time()
            }
            
            # Add SQL analysis if found
            if sql_analysis["queries"]:
                result["sql_queries"] = sql_analysis["queries"]
                result["sql_data_previews"] = sql_analysis["data_previews"]
                result["data_retrieval_query"] = sql_analysis["data_retrieval_query"]
                
                print(f"🗃️ Found {len(sql_analysis['queries'])} SQL queries in lakehouse operations")
                
                for i, query in enumerate(sql_analysis["queries"], 1):
                    print(f"📄 SQL Query {i}:")
                    print(f"   {query}")
                    
                    # Show data preview if this query retrieved data
                    if i == sql_analysis["data_retrieval_query_index"]:
                        print(f"   🎯 This query retrieved the data!")
                        if sql_analysis["data_previews"][i-1]:
                            print(f"   📊 Data Preview:")
                            preview = sql_analysis["data_previews"][i-1]
                            
                            # Check if the preview is a raw markdown table (single item)
                            if len(preview) == 1 and '\n' in preview[0] and '|' in preview[0]:
                                # This is a raw markdown table, print it directly
                                print(preview[0])
                            else:
                                # This is parsed row data, print line by line
                                for line in preview[:5]:  # Show first 5 lines
                                    print(f"      {line}")
                                if len(preview) > 5:
                                    print(f"      ... and {len(preview) - 5} more lines")
                    print()  # Empty line for readability
            
            # Cache store
            self._cache_set(cache_key, result)
            return result
            
        except Exception as e:
            detailed = self._format_api_error(e)
            print(f"❌ Error getting run details:\n{detailed}")
            return {"error": str(e), "error_details": detailed}

    def _extract_sql_queries_with_data(self, steps) -> dict:
        """
        Extract SQL queries from run steps using direct JSON parsing and output analysis.
        
        Args:
            steps: The run steps from the OpenAI API
            
        Returns:
            dict: Contains queries, data previews, and which query retrieved data
        """
        sql_queries = []
        data_previews = []
        data_retrieval_query = None
        data_retrieval_query_index = None
        
        try:
            for step_idx, step in enumerate(steps.data):
                if hasattr(step, 'step_details') and step.step_details:
                    step_details = step.step_details
                    
                    # Check for tool calls which typically contain the SQL queries
                    if hasattr(step_details, 'tool_calls') and step_details.tool_calls:
                        for tool_idx, tool_call in enumerate(step_details.tool_calls):
                            # Extract SQL from function arguments
                            sql_from_args = self._extract_sql_from_function_args(tool_call)
                            if sql_from_args:
                                sql_queries.extend(sql_from_args)
                            
                            # Extract SQL from tool call output (where it's actually located in Fabric)
                            sql_from_output = self._extract_sql_from_output(tool_call)
                            if sql_from_output:
                                sql_queries.extend(sql_from_output)
                            
                            # Extract data from tool call output
                            data_preview = self._extract_structured_data_from_output(tool_call)
                            if data_preview:
                                # If we found data and SQL in this step, it's likely the retrieval query
                                if sql_from_args or sql_from_output:
                                    all_sql_this_call = sql_from_args + sql_from_output
                                    data_retrieval_query = all_sql_this_call[-1] if all_sql_this_call else None
                                    data_retrieval_query_index = len(sql_queries)
                            
                            data_previews.append(data_preview)
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract SQL queries: {e}")
        
        # Remove duplicates while preserving order
        unique_queries = list(dict.fromkeys(sql_queries))
        
        return {
            "queries": unique_queries,
            "data_previews": data_previews,
            "data_retrieval_query": data_retrieval_query,
            "data_retrieval_query_index": data_retrieval_query_index
        }

    def _extract_sql_from_function_args(self, tool_call) -> list:
        """
        Extract SQL queries from tool call function arguments.
        
        Args:
            tool_call: OpenAI tool call object
            
        Returns:
            list: SQL queries found
        """
        sql_queries = []
        
        try:
            if hasattr(tool_call, 'function') and tool_call.function:
                if hasattr(tool_call.function, 'arguments'):
                    args_str = tool_call.function.arguments
                    
                    # Parse the arguments JSON
                    args = json.loads(args_str)
                    
                    if isinstance(args, dict):
                        # Common keys where SQL queries are stored in Fabric Data Agents
                        sql_keys = ['sql', 'query', 'sql_query', 'statement', 'command', 'code']
                        
                        for key in sql_keys:
                            if key in args and args[key]:
                                sql_query = str(args[key]).strip()
                                if sql_query and len(sql_query) > 10:  # Basic validation
                                    sql_queries.append(sql_query)
                        
                        # Also check for nested structures
                        for key, value in args.items():
                            if isinstance(value, dict):
                                for nested_key in sql_keys:
                                    if nested_key in value and value[nested_key]:
                                        sql_query = str(value[nested_key]).strip()
                                        if sql_query and len(sql_query) > 10:
                                            sql_queries.append(sql_query)
        
        except (json.JSONDecodeError, AttributeError) as e:
            # If JSON parsing fails, fall back to basic string search
            try:
                args_str = str(tool_call.function.arguments)
                # Look for common SQL patterns in the string
                if any(keyword in args_str.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                    # Use minimal regex as fallback
                    import re
                    sql_pattern = r'"(?:sql|query|statement|code)"\s*:\s*"([^"]+)"'
                    matches = re.findall(sql_pattern, args_str, re.IGNORECASE)
                    sql_queries.extend([match.strip() for match in matches if len(match.strip()) > 10])
            except Exception as parse_error:
                print(f"⚠️ Warning: Could not parse tool call arguments: {parse_error}")
        
        return sql_queries

    def _extract_sql_from_output(self, tool_call) -> list:
        """
        Extract SQL queries from tool call output.
        
        Args:
            tool_call: OpenAI tool call object
            
        Returns:
            list: SQL queries found in output
        """
        sql_queries = []
        
        try:
            if hasattr(tool_call, 'output') and tool_call.output:
                output_str = str(tool_call.output)
                
                # First try to parse as JSON
                try:
                    output_json = json.loads(output_str)
                    
                    if isinstance(output_json, dict):
                        # Look for SQL in common keys
                        sql_keys = ['sql', 'query', 'sql_query', 'statement', 'command', 'code', 'generated_code']
                        for key in sql_keys:
                            if key in output_json and output_json[key]:
                                sql_query = str(output_json[key]).strip()
                                if sql_query and len(sql_query) > 10:
                                    sql_queries.append(sql_query)
                        
                        # Check nested structures
                        for key, value in output_json.items():
                            if isinstance(value, dict):
                                for nested_key in sql_keys:
                                    if nested_key in value and value[nested_key]:
                                        sql_query = str(value[nested_key]).strip()
                                        if sql_query and len(sql_query) > 10:
                                            sql_queries.append(sql_query)
                
                except json.JSONDecodeError:
                    # If not JSON, use regex to find SQL patterns
                    pass
                
                # Always also try regex as backup/additional method
                if any(keyword in output_str.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'FROM']):
                    # Enhanced regex patterns for SQL extraction
                    sql_patterns = [
                        r'"(?:sql|query|statement|code|generated_code)"\s*:\s*"([^"]+)"',
                        r"'(?:sql|query|statement|code|generated_code)'\s*:\s*'([^']+)'",
                        r'(SELECT\s+.*?FROM\s+.*?)(?=\s*[;}"\'\n]|\s*$)',
                        r'(INSERT\s+INTO\s+.*?)(?=\s*[;}"\'\n]|\s*$)',
                        r'(UPDATE\s+.*?SET\s+.*?)(?=\s*[;}"\'\n]|\s*$)',
                        r'(DELETE\s+FROM\s+.*?)(?=\s*[;}"\'\n]|\s*$)'
                    ]
                    
                    for pattern in sql_patterns:
                        matches = re.findall(pattern, output_str, re.IGNORECASE | re.DOTALL)
                        for match in matches:
                            clean_query = match.strip().replace('\\n', '\n').replace('\\t', '\t')
                            clean_query = re.sub(r'\s+', ' ', clean_query)
                            if len(clean_query) > 10:
                                sql_queries.append(clean_query)
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract SQL from output: {e}")
        
        return sql_queries

    def _extract_structured_data_from_output(self, tool_call) -> list:
        """
        Extract structured data from tool call output using JSON parsing.
        
        Args:
            tool_call: OpenAI tool call object
            
        Returns:
            list: Formatted data lines
        """
        data_lines = []
        
        try:
            if hasattr(tool_call, 'output') and tool_call.output:
                output_str = str(tool_call.output)
                
                # Try to parse as JSON first
                try:
                    data = json.loads(output_str)
                    
                    if isinstance(data, list) and len(data) > 0:
                        # Handle list of records (typical query result)
                        if isinstance(data[0], dict):
                            headers = list(data[0].keys())
                            data_lines.append("| " + " | ".join(headers) + " |")
                            data_lines.append("|" + "---|" * len(headers))
                            
                            for row in data[:10]:  # Limit to first 10 rows
                                values = [str(row.get(h, "")) for h in headers]
                                data_lines.append("| " + " | ".join(values) + " |")
                    
                    # Also allow already-structured preview arrays
                    elif isinstance(data, dict) and "rows" in data and isinstance(data["rows"], list):
                        rows = data["rows"]
                        if rows and isinstance(rows[0], dict):
                            headers = list(rows[0].keys())
                            data_lines.append("| " + " | ".join(headers) + " |")
                            data_lines.append("|" + "---|" * len(headers))
                            for row in rows[:10]:
                                values = [str(row.get(h, "")) for h in headers]
                                data_lines.append("| " + " | ".join(values) + " |")
                
                except json.JSONDecodeError:
                    # If not JSON, try to detect simple markdown-like rows already
                    pass
        
        except Exception as e:
            print(f"⚠️ Warning: Could not parse structured data from output: {e}")
        
        return data_lines

    # =============================
    # Visualization helpers (Step 1)
    # =============================
    def _extract_json_from_text(self, text: str) -> Optional[dict]:
        """Attempt to extract the largest JSON object from a text blob."""
        try:
            # Fast path: direct JSON
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # Fallback: find the first '{' and last '}' and try to parse
        try:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                candidate = text[start:end+1]
                return json.loads(candidate)
        except Exception:
            return None
        return None

    def _parse_markdown_table_to_records(self, lines: list[str]) -> list[dict]:
        """Convert markdown table lines to list of dict rows."""
        try:
            if not lines:
                return []
            # Join if a single markdown block is provided
            if len(lines) == 1 and ('|' in lines[0] and '\n' in lines[0]):
                lines = [ln for ln in lines[0].split('\n') if ln.strip()]
            # Find header and separator
            header_line = None
            sep_idx = None
            for i, ln in enumerate(lines):
                if '|' in ln and ('---' in ln or ln.strip().startswith('|-')):
                    sep_idx = i
                    # header is previous non-empty line with '|'
                    j = i - 1
                    while j >= 0 and (not lines[j].strip() or '|' not in lines[j]):
                        j -= 1
                    if j >= 0:
                        header_line = lines[j]
                    break
            if header_line is None:
                # Try first line as header
                header_line = lines[0] if '|' in lines[0] else None
                if header_line is None:
                    return []
                sep_idx = 1 if len(lines) > 1 else None

            headers = [h.strip().strip('|').strip() for h in header_line.split('|') if h.strip()]
            data_lines = lines[sep_idx+1:] if sep_idx is not None else lines[1:]
            rows = []
            for ln in data_lines:
                if '|' not in ln:
                    continue
                cells = [c.strip() for c in ln.split('|') if c.strip()]
                if len(cells) < len(headers):
                    # pad
                    cells = cells + [''] * (len(headers) - len(cells))
                row = {headers[i]: cells[i] if i < len(cells) else '' for i in range(len(headers))}
                # skip separator-like lines
                if all(set(v) <= set('-:') for v in row.values() if v):
                    continue
                rows.append(row)
            return rows
        except Exception:
            return []

    def _infer_column_types(self, records: list[dict]) -> list[dict]:
        """Infer basic column types from preview records."""
        if not records:
            return []
        headers = list(records[0].keys())
        cols = []
        for h in headers:
            # Inspect up to first 50 samples
            vals = [r.get(h) for r in records[:50]]
            ctype = "string"
            # numeric?
            try:
                numeric_samples = 0
                for v in vals:
                    if v is None or v == "":
                        continue
                    float(v)
                    numeric_samples += 1
                if numeric_samples >= max(1, len(vals)//3):
                    ctype = "number"
            except Exception:
                pass
            # simple datetime detection
            if ctype == "string":
                for v in vals:
                    if not v:
                        continue
                    if isinstance(v, str) and re.search(r"^\d{4}-\d{2}-\d{2}", v):
                        ctype = "date"
                        break
            cols.append({"name": h, "type": ctype})
        return cols

    def _infer_roles_and_chart(self, columns: list[dict], records: list[dict]) -> tuple[list[dict], str]:
        """Assign roles and suggest a default chart."""
        # roles: dimension (categorical), measure (numeric), time (date)
        roles = []
        dims = [c for c in columns if c.get("type") == "string"]
        nums = [c for c in columns if c.get("type") == "number"]
        dates = [c for c in columns if c.get("type") in ("date", "datetime")]

        for c in columns:
            t = c.get("type")
            role = "dimension"
            if t == "number":
                role = "measure"
            elif t in ("date", "datetime"):
                role = "time"
            roles.append({"name": c["name"], "type": t, "role": role})

        # Chart suggestion
        chart = "table"
        if dates and nums:
            chart = "line"
        elif dims and nums:
            # few categories? consider pie if very few unique dims
            chart = "bar"
            try:
                if records and len(set(str(r.get(dims[0]["name"])) for r in records if r.get(dims[0]["name"])) ) <= 6:
                    chart = "pie"
            except Exception:
                pass

        return roles, chart

    def _normalize_visualization_spec(self, raw: dict) -> dict:
        """Ensure the visualization spec has all required fields with safe defaults."""
        spec = {
            "intent": raw.get("intent") or "",
            "chart_suggestion": raw.get("chart_suggestion") or "table",
            "dataset_description": raw.get("dataset_description") or "",
            "columns": [],
            "data_preview": [],
            "provenance": {
                "sql_query": None,
                "source": raw.get("provenance", {}).get("source") if isinstance(raw.get("provenance"), dict) else None,
            },
            "limits": {
                "row_count": None,
                "preview_rows": None,
            },
            "notes": raw.get("notes") or "",
        }
        # columns
        cols = raw.get("columns")
        if isinstance(cols, list):
            norm_cols = []
            for c in cols:
                if isinstance(c, dict) and "name" in c:
                    norm_cols.append({
                        "name": c.get("name"),
                        "type": c.get("type") or "string",
                        "role": c.get("role") or "dimension",
                    })
            spec["columns"] = norm_cols
        # data
        data = raw.get("data_preview")
        if isinstance(data, list) and (not data or isinstance(data[0], dict)):
            spec["data_preview"] = data
        # limits
        lim = raw.get("limits")
        if isinstance(lim, dict):
            spec["limits"]["row_count"] = lim.get("row_count")
            spec["limits"]["preview_rows"] = lim.get("preview_rows")
        # provenance.sql_query
        prov = raw.get("provenance")
        if isinstance(prov, dict) and prov.get("sql_query"):
            spec["provenance"]["sql_query"] = prov.get("sql_query")
        return spec

    def get_visualization_spec(self, question: str, max_preview_rows: int = 50, timeout: int = 120) -> dict:
        """
        Step 1: Convert a user's visualization request into a structured data+metadata spec.

        Attempts to obtain a strict JSON payload from the agent. If not available,
        falls back to constructing the spec from get_run_details() and parsed previews.
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        # Cache
        cache_key = ("viz_spec", question.strip(), max_preview_rows, timeout)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        client = self._get_openai_client()

        # 1) Try to instruct the agent to return JSON directly
        instruction = (
            "You are a data assistant returning visualization-ready data. "
            "Return ONLY a JSON object with the following fields: "
            "intent, chart_suggestion (bar|line|pie|table), dataset_description, "
            "columns (array of {name,type(role from string|number|date|datetime),role from dimension|measure|time}), "
            "data_preview (array of objects, up to N rows), provenance {sql_query, source}, "
            "limits {row_count, preview_rows}, notes. Do not include any text outside the JSON. "
            f"Limit data_preview to at most {max_preview_rows} rows."
        )

        try:
            assistant = client.beta.assistants.create(model="not used")
            thread = client.beta.threads.create()
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=f"{instruction}\nUser request: {question}"
            )
            run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=assistant.id)
            start = time.time()
            while run.status in ["queued", "in_progress"]:
                if time.time() - start > timeout:
                    break
                time.sleep(2)
                run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            messages = client.beta.threads.messages.list(thread_id=thread.id, order="asc")
            final_text = ""
            for msg in messages:
                if msg.role == "assistant" and msg.content:
                    try:
                        part = msg.content[0]
                        if hasattr(part, 'text') and getattr(part, 'text', None) is not None and hasattr(part.text, 'value'):
                            final_text = part.text.value
                        else:
                            final_text = str(part)
                    except Exception:
                        final_text = str(msg.content)

            # Cleanup
            try:
                client.beta.threads.delete(thread_id=thread.id)
            except Exception:
                pass

            # Try parse JSON
            parsed = self._extract_json_from_text(final_text) if final_text else None
            if isinstance(parsed, dict):
                spec = self._normalize_visualization_spec(parsed)
                # Cache and return
                self._cache_set(cache_key, spec)
                return spec
        except Exception as e:
            # Continue to fallback path
            print(f"⚠️ Visualization JSON request failed, falling back. Details: {e}")

        # 2) Fallback: use get_run_details() to extract previews and SQL
        details = self.get_run_details(question)
        spec: dict = {
            "intent": question,
            "chart_suggestion": "table",
            "dataset_description": "",
            "columns": [],
            "data_preview": [],
            "provenance": {"sql_query": None, "source": None},
            "limits": {"row_count": None, "preview_rows": None},
            "notes": "Constructed from run details preview; agent did not return structured JSON.",
        }

        sql_query = details.get("data_retrieval_query") or None
        if sql_query:
            spec["provenance"]["sql_query"] = sql_query
            spec["provenance"]["source"] = "lakehouse"

        previews = details.get("sql_data_previews") or []
        records: list[dict] = []
        # Take the first non-empty preview and parse
        for pv in previews:
            if not pv:
                continue
            # pv could be [markdown_table_str] or list of lines
            recs = self._parse_markdown_table_to_records(pv)
            if recs:
                records = recs[:max_preview_rows]
                break

        if records:
            inferred_cols = self._infer_column_types(records)
            roles, chart = self._infer_roles_and_chart(inferred_cols, records)
            spec["columns"] = roles
            spec["data_preview"] = records
            spec["chart_suggestion"] = chart or "table"
            spec["limits"]["preview_rows"] = len(records)
        else:
            spec["notes"] += " No tabular preview rows were available."

        # Cache and return
        self._cache_set(cache_key, spec)
        return spec

    def _extract_markdown_table(self, text: str) -> str:
        """
        Extract raw markdown table from the assistant's text response.
        
        Args:
            text (str): The assistant's text response
            
        Returns:
            str: Raw markdown table if found, or empty string if no table found
        """
        lines = text.split('\n')
        table_lines = []
        in_table = False
        header_found = False
        
        for line in lines:
            line_stripped = line.strip()
            
            # Check if this line contains markdown table separators
            if '|' in line_stripped and ('---' in line_stripped or '-' in line_stripped and line_stripped.count('-') > 3):
                table_lines.append(line)
                in_table = True
                header_found = True
            elif '|' in line_stripped and (in_table or not header_found):
                # This is a table row (header or data row)
                table_lines.append(line)
                in_table = True
            elif in_table and line_stripped == '':
                # Empty line - might continue table, add it but don't break yet
                table_lines.append(line)
            elif in_table and '|' not in line_stripped and line_stripped != '':
                # Non-table line after we were in a table - end of table
                break
        
        # Clean up trailing empty lines
        while table_lines and table_lines[-1].strip() == '':
            table_lines.pop()
        
        # Return the raw markdown table if we found at least a header and separator
        if len(table_lines) >= 2:
            return '\n'.join(table_lines)
        else:
            return ""

    def _extract_data_from_text_response(self, text_content: str) -> list:
        """
        Extract structured data from the assistant's text response.
        First tries to find raw markdown tables, then falls back to numbered list parsing.
        
        Args:
            text_content (str): The text content from the assistant
            
        Returns:
            list: Formatted data lines (raw markdown table as single item, or parsed rows)
        """
        import re
        
        # First, try to extract a raw markdown table
        markdown_table = self._extract_markdown_table(text_content)
        if markdown_table:
            # Return the raw markdown table as a single formatted block
            return [markdown_table]
        
        # Fallback to numbered list parsing (existing logic)
        data_lines = []
        
        try:
            lines = text_content.split('\n')
            
            # Look for numbered lists with data (like the example output)
            numbered_pattern = r'^\d+\.\s+'
            data_rows = []
            
            for line in lines:
                line = line.strip()
                if re.match(numbered_pattern, line):
                    # Remove the number prefix
                    clean_line = re.sub(numbered_pattern, '', line)
                    data_rows.append(clean_line)
            
            if data_rows and len(data_rows) > 0:
                # Try to parse the structured data from the text
                first_row = data_rows[0]
                if ':' in first_row:
                    # Parse key-value format
                    # Example: "Date: 4/29/2020, State: WI, Positive: 7,660, ..."
                    
                    # Extract headers from first row
                    headers = []
                    values_first_row = []
                    
                    pairs = first_row.split(', ')
                    for pair in pairs:
                        if ':' in pair:
                            key, value = pair.split(':', 1)
                            headers.append(key.strip())
                            values_first_row.append(value.strip())
                    
                    if headers:
                        # Create table format
                        data_lines.append("| " + " | ".join(headers) + " |")
                        data_lines.append("|" + "---|" * len(headers))
                        
                        # Add first row
                        data_lines.append("| " + " | ".join(values_first_row) + " |")
                        
                        # Parse remaining rows
                        for row in data_rows[1:]:
                            values = []
                            pairs = row.split(', ')
                            for pair in pairs:
                                if ':' in pair:
                                    _, value = pair.split(':', 1)
                                    values.append(value.strip())
                            
                            if len(values) == len(headers):
                                data_lines.append("| " + " | ".join(values) + " |")
                            
                        return data_lines
                
                # If we couldn't parse structured format, return the raw rows as-is
                if not data_lines and data_rows:
                    # Just show the numbered list data
                    return [f"Row {i+1}: {row}" for i, row in enumerate(data_rows)]
            
            # Alternative: Look for table-like structures in the text
            # Check if there are lines that look like table rows
            potential_table_lines = []
            for line in lines:
                line = line.strip()
                # Look for lines with multiple separators that could be table data
                if line and ('|' in line or line.count(',') >= 2 or line.count(':') >= 2):
                    potential_table_lines.append(line)
            
            if potential_table_lines and not data_lines:
                return potential_table_lines[:10]  # Return first 10 lines
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract data from text response: {e}")
        
        return data_lines

    def _format_list_data(self, data_list) -> list:
        """
        Format a list of data records into table format.
        """
        data_lines = []
        
        if len(data_list) > 0 and isinstance(data_list[0], dict):
            headers = list(data_list[0].keys())
            data_lines.append("| " + " | ".join(headers) + " |")
            data_lines.append("|" + "---|" * len(headers))
            
            for row in data_list[:10]:  # Limit to first 10 rows
                values = [str(row.get(h, "")) for h in headers]
                data_lines.append("| " + " | ".join(values) + " |")
        
        return data_lines

    def _extract_data_preview(self, text: str) -> list:
        """
        Extract data preview from text output.
        
        Args:
            text (str): Text to search for tabular data
            
        Returns:
            list: List of data rows found
        """
        data_lines = []
        
        try:
            # Look for JSON-like data structures
            json_pattern = r'\[[\s\S]*?\]'
            json_matches = re.findall(json_pattern, text)
            
            for match in json_matches:
                try:
                    # Try to parse as JSON
                    data = json.loads(match)
                    if isinstance(data, list) and len(data) > 0:
                        # Convert to readable format
                        if isinstance(data[0], dict):
                            # List of dictionaries (typical query result)
                            headers = list(data[0].keys())
                            data_lines.append("| " + " | ".join(headers) + " |")
                            data_lines.append("|" + "---|" * len(headers))
                            
                            for row in data[:10]:  # Limit to first 10 rows
                                values = [str(row.get(h, "")) for h in headers]
                                data_lines.append("| " + " | ".join(values) + " |")
                        break  # Found valid JSON data
                except json.JSONDecodeError:
                    continue
            
            # If no JSON found, look for pipe-separated tables
            if not data_lines:
                lines = text.split('\n')
                table_lines = []
                
                for line in lines:
                    # Look for lines that contain multiple pipe characters (table format)
                    if line.count('|') >= 2:
                        table_lines.append(line.strip())
                    elif table_lines and line.strip() == "":
                        # End of table
                        break
                    elif table_lines and not line.strip().startswith('|'):
                        # Non-table line after table started
                        break
                
                if table_lines:
                    data_lines = table_lines[:15]  # Limit to first 15 lines
            
            # Look for CSV-like data
            if not data_lines:
                lines = text.split('\n')
                csv_lines = []
                
                for line in lines:
                    # Look for comma-separated values with consistent column count
                    if ',' in line and len(line.split(',')) >= 2:
                        csv_lines.append(line.strip())
                        if len(csv_lines) >= 10:  # Limit preview
                            break
                    elif csv_lines:
                        break
                
                if len(csv_lines) > 1:  # At least header + one data row
                    data_lines = csv_lines
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract data preview: {e}")
        
        return data_lines

    def _extract_sql_queries(self, steps) -> list:
        """
        Extract SQL queries from run steps when lakehouse data source is used.
        
        Args:
            steps: The run steps from the OpenAI API
            
        Returns:
            list: List of SQL queries found in the steps
        """
        sql_queries = []
        
        try:
            for step in steps.data:
                if hasattr(step, 'step_details') and step.step_details:
                    step_details = step.step_details
                    
                    # Check for tool calls that might contain SQL
                    if hasattr(step_details, 'tool_calls') and step_details.tool_calls:
                        for tool_call in step_details.tool_calls:
                            # Look for SQL queries in tool call details
                            if hasattr(tool_call, 'function') and tool_call.function:
                                if hasattr(tool_call.function, 'arguments'):
                                    args_str = str(tool_call.function.arguments)
                                    # Look for SQL patterns in arguments
                                    sql_queries.extend(self._find_sql_in_text(args_str))
                            
                            # Check tool call outputs for SQL
                            if hasattr(tool_call, 'output') and tool_call.output:
                                output_str = str(tool_call.output)
                                sql_queries.extend(self._find_sql_in_text(output_str))
                    
                    # Check step details for any SQL content
                    step_str = str(step_details)
                    sql_queries.extend(self._find_sql_in_text(step_str))
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract SQL queries: {e}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_queries = []
        for query in sql_queries:
            if query not in seen:
                seen.add(query)
                unique_queries.append(query)
        
        return unique_queries

    def _find_sql_in_text(self, text: str) -> list:
        """
        Find SQL queries in text using pattern matching.
        
        Args:
            text (str): Text to search for SQL queries
            
        Returns:
            list: List of SQL queries found
        """
        import re
        
        sql_queries = []
        
        # Common SQL keywords that indicate a query
        sql_patterns = [
            r'(SELECT\s+.*?FROM\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\)|\s*,)',
            r'(INSERT\s+INTO\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(UPDATE\s+.*?SET\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(DELETE\s+FROM\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(CREATE\s+TABLE\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(ALTER\s+TABLE\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(DROP\s+TABLE\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))'
        ]
        
        for pattern in sql_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                # Clean up the SQL query
                clean_query = match.strip().replace('\n', ' ').replace('\t', ' ')
                clean_query = re.sub(r'\s+', ' ', clean_query)  # Normalize whitespace
                if len(clean_query) > 10:  # Filter out very short matches
                    sql_queries.append(clean_query)
        
        return sql_queries


def main():
    """
    Example usage of the Fabric Data Agent Client.
    """
    # Configuration - Update these with your actual values
    TENANT_ID = os.getenv("TENANT_ID", "your-tenant-id-here")
    DATA_AGENT_URL = os.getenv("DATA_AGENT_URL", "your-data-agent-url-here")
    AUTH_TOKEN = os.getenv("AUTH_TOKEN")  # Optional - if not provided, will use interactive auth
    
    # Validate configuration
    if TENANT_ID == "your-tenant-id-here" or DATA_AGENT_URL == "your-data-agent-url-here":
        print("❌ Please update TENANT_ID and DATA_AGENT_URL with your actual values")
        print("\nYou can either:")
        print("1. Edit this script and update the values directly")
        print("2. Set environment variables: TENANT_ID and DATA_AGENT_URL")
        print("3. Create a .env file with these variables")
        print("\nOptional: Set AUTH_TOKEN environment variable to use token-based authentication")
        print("If AUTH_TOKEN is not provided, interactive browser authentication will be used")
        return
    
    try:
        # Initialize the client with optional auth token
        # If auth_token is None, it will automatically fall back to InteractiveBrowserCredential
        client = FabricDataAgentClient(
            tenant_id=TENANT_ID,
            data_agent_url=DATA_AGENT_URL,
            auth_token=AUTH_TOKEN  # This can be None for interactive auth
        )
        
        # Example questions
        questions = [
            "What data is available in the lakehouse?",
            "Show me the top 5 records from any available table",
            "What are the column names and types in the main tables?"
        ]
        
        print("\n" + "="*60)
        print("🤖 Fabric Data Agent Client - Ready!")
        print("="*60)
        
        for i, question in enumerate(questions, 1):
            print(f"\n📋 Example {i}:")
            response = client.ask(question)
            
            print(f"\n💬 Response:")
            print("-" * 50)
            print(response)
            print("-" * 50)
            
            # Wait between requests
            if i < len(questions):
                n = 1
                print(f"\nWaiting {n} seconds before next question...")
                time.sleep(n)
        
        print("\n✅ All examples completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting tips:")
        print("- If using AUTH_TOKEN, ensure it's valid and not expired")
        print("- If using interactive auth, ensure you have browser access")
        print("- Check that your TENANT_ID and DATA_AGENT_URL are correct")
        print("- Verify your Azure account has the necessary permissions")


if __name__ == "__main__":
    main()
