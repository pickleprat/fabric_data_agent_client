# Fabric Data Agent External Client

A standalone Python client for calling Microsoft Fabric Data Agents from outside of the Fabric environment using Azure AD client credentials (client ID + client secret).

## Overview

This client enables you to interact with your Microsoft Fabric Data Agents from external applications, scripts, or environments. It handles Azure authentication, token management, and provides a simple interface for asking questions to your data agents.

## Features

- 🔐 **Service-to-Service Authentication** - Uses Azure AD client credentials (client ID + client secret)
- 🔄 **Automatic Token Refresh** - Handles token expiration and refresh automatically
- 🧹 **Resource Cleanup** - Properly manages OpenAI threads and resources
- ⚡ **Simple API** - Easy-to-use interface for querying your data agents
- 📊 **Detailed Responses** - Get both simple answers and detailed run information
- ⏰ **Timeout Handling** - Configurable timeouts for long-running queries
- 🛡️ **Error Handling** - Comprehensive error handling and user-friendly messages

## Requirements

- Python 3.7+
- Azure tenant with Fabric Data Agent access
- Published Fabric Data Agent URL

## Installation

1. Clone or download this repository:

```bash
git clone <repository-url>
cd fabric_data_agent_client
```

2. Install required dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

You can configure the client in three ways:

### Option 1: Environment Variables

```bash
export TENANT_ID=<your-azure-tenant-id>
export CLIENT_ID=<your-entra-app-client-id>
export CLIENT_SECRET=<your-entra-app-client-secret>
export DATA_AGENT_URL=<your-fabric-data-agent-url>
```

### Option 2: .env File

Create a `.env` file in the project directory:

```env
TENANT_ID=<your-azure-tenant-id>
CLIENT_ID=<your-entra-app-client-id>
CLIENT_SECRET=<your-entra-app-client-secret>
DATA_AGENT_URL=<your-fabric-data-agent-url>
```

### Option 3: Direct Configuration

Edit the values directly in your script:

```python
TENANT_ID = "<your-azure-tenant-id>"
CLIENT_ID = "<your-entra-app-client-id>"
CLIENT_SECRET = "<your-entra-app-client-secret>"
DATA_AGENT_URL = "<your-fabric-data-agent-url>"
```

## Usage

### Basic Usage

```python
from fabric_data_agent_client import FabricDataAgentClient

# Initialize the client (client credentials authentication)
client = FabricDataAgentClient(
    tenant_id="your-tenant-id",
    client_id="your-client-id",
    client_secret="your-client-secret",
    data_agent_url="your-data-agent-url"
)

# Ask a simple question
response = client.ask("What data is available in the lakehouse?")
print(response)
```

### Getting Detailed Run Information with SQL Query Extraction

```python
# Get detailed run information including steps and SQL queries for lakehouse data sources
run_details = client.get_run_details("What are the top 5 records from any table?")

print(f"Run Status: {run_details['run_status']}")
print(f"Steps Count: {len(run_details['run_steps']['data'])}")

# Check if SQL queries were extracted (indicates lakehouse data source)
if "sql_queries" in run_details and run_details["sql_queries"]:
    print("Lakehouse Data Source Detected!")
    
    # Show which query retrieved the data and preview the results
    if "data_retrieval_query" in run_details:
        print(f"Data Retrieved By: {run_details['data_retrieval_query']}")
        
        # Show data preview
        if "sql_data_previews" in run_details:
            preview = run_details["sql_data_previews"][0]  # First preview
            if preview:
                print("Data Preview:")
                for line in preview[:5]:
                    print(f"  {line}")
    
    # Optional: Show all SQL queries executed
    # for i, query in enumerate(run_details['sql_queries'], 1):
    #     print(f"  {i}. {query}")
```

### Running the Examples

The project includes example scripts you can run:

```bash
# Run the main example
python fabric_data_agent_client.py

# Run the simple usage example
python example_usage.py
```

## API Reference

### FabricDataAgentClient

#### `__init__(tenant_id: str, client_id: str, client_secret: str, data_agent_url: str)`

Initialize the client with your Azure tenant ID, Entra ID application credentials, and Fabric Data Agent URL.

#### `ask(question: str, timeout: int = 120) -> str`

Ask a question to the data agent.

- **question**: The question to ask
- **timeout**: Maximum time to wait for response in seconds
- **Returns**: The response from the data agent

#### `get_run_details(question: str) -> dict`

Ask a question and return detailed run information including steps, SQL queries, and data previews if lakehouse data source is used.

- **question**: The question to ask
- **Returns**: Detailed response including:
  - `run_steps`: Execution steps and metadata  
  - `sql_queries`: List of SQL queries executed (if lakehouse data source)
  - `sql_data_previews`: Preview of data returned by queries
  - `data_retrieval_query`: The specific SQL query that retrieved the main data
  - `data_retrieval_query_index`: Index of the data retrieval query in the queries list

## Authentication Flow

1. Register an application in Microsoft Entra ID (Azure AD) and generate a client secret
2. Grant the application appropriate access to call Fabric Data Agents (scope: `https://api.fabric.microsoft.com/.default`)
3. Set `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, and `DATA_AGENT_URL`
4. The client obtains and manages the authentication token using client credentials
5. Tokens are automatically refreshed before expiration

## Error Handling

The client includes comprehensive error handling for common scenarios:

- Invalid configuration (missing tenant ID or data agent URL)
- Authentication failures
- Network timeouts
- API errors
- Token expiration and refresh issues

All errors are logged with helpful messages and troubleshooting tips.

## Troubleshooting

### Common Issues

#### Authentication Fails

- Ensure the Entra ID application (client) has access to call Fabric Data Agents
- Check that your tenant ID, client ID, and client secret are correct
- Verify the application has permissions for `https://api.fabric.microsoft.com/.default`

#### Data Agent Not Responding

- Verify the data agent URL is correct and published
- Check if the data agent is running and accessible
- Ensure your application has permissions to call the data agent

#### Dependency Issues

- Make sure all required packages are installed: `pip install -r requirements.txt`
- Update to the latest versions if you encounter compatibility issues

#### Timeout Issues

- Increase the timeout parameter for complex queries
- Check if your data agent has sufficient resources allocated

### Getting Help

1. Check the error messages - they include specific troubleshooting tips
2. Verify your configuration values are correct
3. Ensure your Entra ID application has the necessary permissions
4. Test with simple queries first before trying complex ones

## Dependencies

- **azure-identity**: Handles Azure AD authentication
- **openai**: Provides the API client for interacting with the data agent
- **python-dotenv**: Optional, for loading environment variables from .env files

## Security Notes

- Keep your client secret secure. Prefer environment variables or a secret manager (e.g., Azure Key Vault)
- Authentication tokens are handled securely and automatically refreshed
- No credentials are stored persistently by this client
- Bearer tokens are used for API authentication with the Fabric Data Agent
- Resources are properly cleaned up after each request

## License

This project is provided as-is for educational and development purposes. Please ensure you comply with Microsoft's terms of service when using Fabric Data Agents.

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve this client.

## Changelog

### v1.0.0

- Initial release
- Client credentials authentication
- Basic question/answer functionality
- Detailed run information
- Automatic token refresh
- Resource cleanup
- Comprehensive error handling

