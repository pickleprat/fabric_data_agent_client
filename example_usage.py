#!/usr/bin/env python3
"""
Simple usage example for the Fabric Data Agent Client

This script demonstrates how to use the FabricDataAgentClient to call
a Fabric Data Agent from outside of the Fabric environment.
"""

from fabric_data_agent_client import FabricDataAgentClient
import os
import dotenv 

dotenv.load_dotenv(override=True)

def main():
    """
    Example usage of the Fabric Data Agent Client
    """
    TENANT_ID = os.getenv("TENANT_ID", "your-tenant-id-here")
    DATA_AGENT_URL = os.getenv("DATA_AGENT_URL", "your-data-agent-url-here")
    ENABLE_CACHE = os.getenv("ENABLE_CACHE", "false").strip().lower() in ("1", "true", "yes", "on")
    try:
        CACHE_TTL = int(os.getenv("CACHE_TTL", "0")) or None  # seconds; None means no expiry during process lifetime
    except ValueError:
        CACHE_TTL = None
    
    if TENANT_ID == "your-tenant-id-here" or DATA_AGENT_URL == "your-data-agent-url-here":
        print("❌ Please set your TENANT_ID and DATA_AGENT_URL")
        print("\nOptions:")
        print("1. Set environment variables:")
        print("   export TENANT_ID='your-actual-tenant-id'")
        print("   export DATA_AGENT_URL='your-actual-data-agent-url'")
        print("   export AUTH_TOKEN='your-auth-token'  # Optional")
        print("\n2. Edit this script and replace the placeholder values")
        print("\n3. Create a .env file with these variables")
        print("\nAuthentication Methods:")
        print("- If AUTH_TOKEN is provided: Uses token-based authentication")
        print("- If AUTH_TOKEN is not provided: Uses interactive browser authentication")
        print("- If AUTH_TOKEN is invalid: Automatically falls back to interactive browser")
        return
    
    try:
        print("🚀 Starting Fabric Data Agent Client Example")
        print("=" * 60)
        
        # Initialize the client with optional auth token
        # The client will automatically handle fallback authentication
        client = FabricDataAgentClient(
            tenant_id=TENANT_ID,
            data_agent_url=DATA_AGENT_URL,
            auth_token=None,  # Can be None for interactive auth
            enable_cache=ENABLE_CACHE,
            cache_ttl=CACHE_TTL,
        )
        
        print("\n🤖 Fabric Data Agent Client - Interactive Mode")
        print("=" * 60)
        print("You can now ask questions to your Fabric Data Agent!")
        print("Type 'quit', 'exit', or 'q' to stop.")
        print("Type 'help' for example queries.")
        print("Type 'detailed <query>' to get detailed run analysis with SQL extraction.")
        print("-" * 60)
        
        while True:
            try:
                # Get user input
                user_query = input("\n💭 Enter your question: ").strip()
                
                # Handle special commands
                if user_query.lower() in ['quit', 'exit', 'q']:
                    print("\n👋 Goodbye!")
                    break
                
                if user_query.lower() == 'help':
                    print("\n📚 Example queries you can try:")
                    print("- What data is available in the lakehouse?")
                    print("- Show me the top 5 records from any available table")
                    print("- Show top 10 ace inhibitors by total cost prescribed by internists in texas in 2022")
                    print("- What are the column names and types in the main tables?")
                    print("- Show me information about the tables in the database")
                    print("- detailed <your query>  (for SQL extraction and detailed analysis)")
                    continue
                
                if not user_query:
                    print("⚠️ Please enter a question or type 'help' for examples.")
                    continue
                
                # Check if user wants detailed analysis
                if user_query.lower().startswith('detailed '):
                    actual_query = user_query[9:].strip()  # Remove 'detailed ' prefix
                    if not actual_query:
                        print("⚠️ Please provide a query after 'detailed'. Example: detailed Show me top 5 records")
                        continue
                    
                    print(f"\n🔍 Getting detailed analysis for: {actual_query}")
                    run_details = client.get_run_details(actual_query)
                    
                    if "error" not in run_details:
                        print(f"✅ Run Status: {run_details['run_status']}")
                        print(f"📊 Steps Count: {len(run_details['run_steps']['data'])}")
                        print(f"📝 Messages Count: {len(run_details['messages']['data'])}")
                        
                        # Show the assistant's final response
                        messages = run_details.get('messages', {}).get('data', [])
                        assistant_messages = [msg for msg in messages if msg.get('role') == 'assistant']
                        if assistant_messages:
                            print(f"\n💬 Agent Response:")
                            latest_message = assistant_messages[-1]
                            content = latest_message.get('content', [])
                            if content and len(content) > 0:
                                # Handle different content types
                                if hasattr(content[0], 'text'):
                                    print(f"   {content[0].text.value}")
                                elif isinstance(content[0], dict) and 'text' in content[0]:
                                    if isinstance(content[0]['text'], dict) and 'value' in content[0]['text']:
                                        print(f"   {content[0]['text']['value']}")
                                    else:
                                        print(f"   {content[0]['text']}")
                                else:
                                    print(f"   {str(content[0])}")
                        
                        # Show SQL queries and data previews
                        if "data_retrieval_query" in run_details and run_details["data_retrieval_query"]:
                            print(f"\n🎯 SQL Query Used:")
                            print(f"   {run_details['data_retrieval_query']}")
                            
                            # Show data preview if available
                            if "sql_data_previews" in run_details and run_details["sql_data_previews"]:
                                data_retrieval_index = run_details.get("data_retrieval_query_index", 1) - 1
                                if 0 <= data_retrieval_index < len(run_details["sql_data_previews"]):
                                    preview = run_details["sql_data_previews"][data_retrieval_index]
                                    if preview:
                                        print(f"\n📊 Data Preview:")
                                        # Check if this is a raw markdown table
                                        if len(preview) == 1 and '\n' in preview[0] and '|' in preview[0]:
                                            table_lines = preview[0].split('\n')
                                            for line in table_lines:
                                                if line.strip():
                                                    print(f"   {line}")
                                        else:
                                            for line in preview[:10]:
                                                print(f"   {line}")
                                            if len(preview) > 10:
                                                print(f"   ... and {len(preview) - 10} more lines")
                        elif "sql_queries" in run_details and run_details["sql_queries"]:
                            print(f"\n🗃️ Lakehouse data source detected")
                            print(f"\n🎯 SQL Query Used:")
                            print(f"   {run_details['sql_queries'][0]}")
                        else:
                            print(f"\n📄 No lakehouse data source detected")
                    else:
                        print(f"❌ Error in detailed run: {run_details.get('error')}")
                        if "error_details" in run_details and run_details["error_details"]:
                            print("\n🧰 Error details for debugging:")
                            print(run_details["error_details"])
                else:
                    # Regular query (not detailed)
                    print(f"\n❓ Asking: {user_query}")
                    response = client.ask(user_query)
                    print(f"\n💬 Response:")
                    print("-" * 50)
                    print(response)
                    print("-" * 50)
                    if isinstance(response, str) and response.startswith("Error while calling data agent:"):
                        print("\n🧰 Error details for debugging detected in response above.")
                    
            except KeyboardInterrupt:
                print("\n⏹️ Operation cancelled by user")
                break
            except Exception as e:
                print(f"\n❌ Error processing query: {e}")
                continue
        
    except KeyboardInterrupt:
        print("\n⏹️ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting tips:")
        print("- Ensure you have the required packages installed: pip install -r requirements.txt")
        print("- Check that your TENANT_ID and DATA_AGENT_URL are correct")
        print("- If using AUTH_TOKEN, ensure it's valid and not expired")
        print("- If using interactive auth, ensure you have browser access")
        print("- Make sure you have access to the Fabric Data Agent")
        print("- Verify your Azure account has the necessary permissions")
        print("- The client will automatically fall back to interactive auth if token fails")
        print("- Set ENABLE_CACHE=true to enable in-memory response caching. Optionally set CACHE_TTL (seconds)")

if __name__ == "__main__":
    main()
