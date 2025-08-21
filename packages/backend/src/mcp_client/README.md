# MCP (Model Context Protocol) Client

The MCP Client provides tools and services for interacting with AI models through the Model Context Protocol framework. This implementation includes custom tools for blueprint analysis and document management.

## Overview

This MCP implementation includes two main servers:

### 1. Basic Server (Custom Tools)
Our custom MCP server that provides specialized tools for blueprint analysis and document management:

- **Project Management**: Get project information and metadata
- **Document Analysis**: Analyze construction blueprints using AI
- **Search Tools**: Hybrid search across documents and pages
- **Content Management**: Add/remove user annotations and content
- **Document Operations**: List and retrieve document information

### 2. Filesystem Server (MCP Provided)
A standard MCP server for local file system operations:
- Read and write files in the local workspace
- Added to demonstrate MCP extensibility
- Operates in the `/mcp-workspace` directory

## Registered Tools

### Custom Tools (basic-server)

| Tool | Description | Source File |
|------|-------------|-------------|
| `get_project_info` | Retrieve project information and metadata | `project_manager.py` |
| `get_document_info` | Get detailed document information | `document_analyzer.py` |
| `hybrid_search` | Search across documents and pages | `search_tools.py` |
| `get_document_analysis` | Get AI analysis results for documents | `document_analyzer.py` |
| `get_page_analysis_details` | Get detailed analysis for specific pages | `document_analyzer.py` |
| `get_documents_list` | List all documents in a project | `document_list.py` |
| `add_user_content_to_page` | Add user annotations to pages | `user_content_manager.py` |
| `remove_user_content_from_page` | Remove user annotations from pages | `user_content_manager.py` |
| `add` | Basic addition tool (demo) | `basic_tools.py` |
| `echo` | Basic echo tool (demo) | `basic_tools.py` |

### Filesystem Tools
Standard file operations provided by the MCP filesystem server.

## Project Structure

```
src/mcp_client/
├── README.md                 # This documentation
├── server/
│   ├── basic_server.py      # Main MCP server implementation
│   ├── config.py           # Server configuration
│   └── tools/              # Custom tool implementations
│       ├── __init__.py
│       ├── basic_tools.py          # Demo tools (add, echo)
│       ├── document_analyzer.py    # Document analysis tools
│       ├── document_list.py        # Document listing tools
│       ├── project_manager.py      # Project management tools
│       ├── response_formatter.py   # Response formatting utilities
│       ├── search_tools.py         # Search functionality
│       └── user_content_manager.py # User content management
└── mcp_service.py           # MCP service integration
```

## Configuration

### MCP Server Configuration
Server configuration is managed in `config/mcp_config.json`:

```json
{
  "mcpServers": {
    "basic-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/packages/backend/src/mcp_client/server",
        "run",
        "basic_server.py"
      ]
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/path/to/mcp-workspace"
      ]
    }
  }
}
```

## Adding New Tools

### Creating Custom Tools

1. **Create a new tool file** in `server/tools/`:
   ```python
   # server/tools/my_new_tool.py
   from mcp.server.fastmcp import FastMCP
   
   def my_custom_tool(param1: str, param2: int) -> str:
       """Tool description for MCP"""
       # Tool implementation
       return f"Result: {param1} - {param2}"
   ```

2. **Register the tool** in `server/basic_server.py`:
   ```python
   from tools.my_new_tool import my_custom_tool
   
   # Add to the server
   mcp.add_tool(my_custom_tool)
   ```

### Adding Existing MCP Servers

To add an existing MCP server (like the filesystem server), update `config/mcp_config.json`:

```json
{
  "mcpServers": {
    "existing-servers": "...",
    "new-server": {
      "command": "command-to-start-server",
      "args": ["arg1", "arg2", "..."]
    }
  }
}
```

## Usage Examples

### Basic Server Usage

```python
from mcp.server.fastmcp import FastMCP

# Create MCP server
mcp = FastMCP("AWS IDP AI Analysis Server")

# Tool registration example
@mcp.tool()
def analyze_document(document_id: str) -> str:
    """Analyze a construction blueprint document"""
    # Implementation here
    return f"Analysis result for {document_id}"

# Start server
if __name__ == "__main__":
    mcp.run(host="localhost", port=5000)
```

### Tool Implementation Pattern

```python
def tool_function(param1: str, param2: int = 10) -> dict:
    """
    Tool description that will be shown to the AI model.
    
    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2 (optional)
    
    Returns:
        Dictionary with results
    """
    try:
        # Tool implementation
        result = process_data(param1, param2)
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
```

## Development

### Starting the MCP Server

```bash
cd packages/backend/src/mcp_client/server
uv run basic_server.py
```

### Testing Tools

The server includes basic test tools (`add`, `echo`) for development and testing purposes.

### Configuration Management

Server configuration is loaded from the application config, including:
- Model ID for AI operations
- API base URL
- Server port
- Database connections

## Integration

This MCP client integrates with:
- **FastAPI**: Main application server
- **ReAct Agents**: AI agent framework
- **OpenSearch**: Document search and indexing
- **DynamoDB**: Data storage
- **AWS Bedrock**: AI model access

The MCP tools provide a standardized interface for AI agents to interact with the blueprint analysis system. 