<h2 align="center">
 AWS IDP AI Analysis Backend
</h2>

<div align="center">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/MCP-Tools-121D33?logo=langchain&logoColor=white"/>
  <img src="https://img.shields.io/badge/ReAct-Pattern-FF6B6B?logo=react&logoColor=white"/>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Promptfoo-Eval-4B32C3?logo=python&logoColor=white"/>
</div>

## Overview

** AWS IDP AI Analysis Backend** is an AI chat API server for construction blueprint analysis. 
It provides natural language Q&A through a ReAct pattern-based AI agent utilizing MCP (Model Context Protocol) tools.

## Core Features

### AI Chat API
- **ReAct Pattern**: AI agent architecture combining Reasoning and Acting
- **MCP Tool Integration**: Tool calling and interaction through Model Context Protocol
- **Natural Language Q&A**: Accurate answers to complex construction blueprint-related questions
- **Context Awareness**: Consistent responses utilizing conversation history and document context

### MCP Tool Ecosystem
- **Document Analysis Tools**: Image analysis, text extraction, structured data generation
- **Search Tools**: OpenSearch-based semantic search and vector search

## Architecture

### Project Structure
```
packages/backend/
├── main.py                        # Server entry point
├── src/
│   ├── __init__.py                # Package initialization
│   ├── init.py                    # FastAPI app initialization
│   ├── common/                    # Common configurations and utilities
│   │   ├── configuration.py       # Agent configuration
│   │   ├── llm.py                 # LLM configuration
│   │   ├── opensearch_client.py   # OpenSearch client
│   │   └── monitoring.py          # Monitoring utilities
│   ├── agent/                     # AI agent implementation
│   │   └── react_agent/           # ReAct pattern agent
│   │       ├── agent.py           # Main agent logic
│   │       ├── checkpoint.py      # Agent state checkpointing
│   │       ├── prompt/            # Agent prompts
│   │       │   └── agent_profile.yaml # Agent configuration
│   │       ├── state/             # Agent state management
│   │       │   └── model.py       # State models
│   │       ├── node/              # Agent nodes
│   │       │   └── tool_node.py   # Tool execution node
│   │       └── utils/             # Agent utilities
│   ├── mcp_client/                # MCP client service
│   │   ├── mcp_service.py         # MCP service management
│   │   └── server/                # MCP server implementation
│   │       ├── basic_server.py    # Basic MCP server
│   │       ├── config.py          # MCP server configuration
│   │       └── tools/             # MCP tools
│   │           ├── basic_tools.py       # Basic tools
│   │           └── document_analyzer.py # Document analysis
│   ├── routers/                   # API routers
│   │   ├── chat.py                # Chat API router
│   │   └── mcp_tools.py           # MCP tools router
│   ├── monitoring/                # Monitoring and observability
│   │   └── phoenix.py             # Phoenix monitoring
│   └── utils/                     # Utility functions
│       ├── mcp_config_generator.py # MCP config generator
│       └── path_resolver.py       # Path resolution utilities
├── config/                        # Configuration files
│   ├── mcp_config.json            # MCP tools configuration
│   └── models.yaml                # AI model settings
├── eval/                          # AI performance evaluation
│   ├── promptfoo_simple_agent.py  # Promptfoo evaluation script
│   ├── promptfooconfig.yaml       # Evaluation configuration
│   └── run_eval.sh                # Evaluation execution script
└── local_dev/                     # Local development utilities
    ├── notebooks/                 # Jupyter notebooks for testing
    ├── scripts/                   # Development scripts
    └── tests/                     # Test files
```

### ReAct Pattern AI Agent Flow
```python
# ReAct pattern processing flow
1. Receive user query
2. Reasoning: Query analysis and tool selection
3. Acting: MCP tool calling and information gathering
4. Observation: Tool execution result analysis
5. Response generation and return
```

## Getting Started

### Prerequisites
- **Python** 3.12 or higher
- **uv** package manager
- **AWS Account** (for cloud resource access)

### Installation & Setup

**Important**: All setup commands should be run from the **project root directory** (`aws-idp-pipline/`).

1. **Create Virtual Environment & Install Dependencies**
```bash
# From project root directory
uv venv
uv sync
```

2. **Environment Variables Setup**
The backend uses the `.env` file located in the **project root directory**.

**If .env file doesn't exist:**
```bash
# Generate .env file using infrastructure deployment
cd packages/infra
./destroy-and-deploy.sh <your-aws-profile> --env-only
```

**If .env file exists:**
Verify that it contains the necessary environment variables for the backend services.

3. **MCP Configuration**
MCP tools are configured in:
```bash
packages/backend/config/mcp_config.json
```
Review and modify this file to configure the MCP tools you want to use.

4. **Activate Virtual Environment & Start Server**
```bash
# Activate virtual environment (from project root)
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Navigate to backend and start server
cd packages/backend
python main.py
```

5. **API Access**
- **Server**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Chat API**: http://localhost:8000/chat

## AI Performance Evaluation

### Promptfoo Evaluation System
Automated evaluation tool to assess AI agent performance and identify improvement areas.

```bash
# Run evaluation
cd packages/backend/eval/
./run_eval.sh

# Or run directly
python promptfoo_simple_agent.py
```

### Evaluation Metrics
- **Accuracy**: Correctness of answers to queries
- **Relevance**: How relevant answers are to the queries
- **Completeness**: Completeness and sufficient information in answers
- **Response Time**: Answer generation speed
- **Tool Utilization**: Appropriate use of MCP tools

## API Endpoints

### Chat API
```http
POST /chat/stream
Content-Type: application/json

{
  "message": "Please find structural issues in this blueprint",
  "index_id": "my-first-index",
  "conversation_id": "conv-456"
}
```

**Response (Server-Sent Events)**
```javascript
data: {"type": "thinking", "content": "Analyzing the blueprint..."}
data: {"type": "tool_call", "tool": "image_analyzer", "status": "executing"}
data: {"type": "content", "content": "Analysis result: Found 3 structural issues"}
data: {"type": "references", "documents": [...]}
```

### MCP Tools API
```http
GET /mcp-tools/list
# Returns available MCP tools

POST /mcp-tools/call
Content-Type: application/json

{
  "tool_name": "image_analyzer",
  "arguments": {...}
}
```

## Security & Authentication

- **CORS Configuration**: Secure communication with frontend
- **API Key Management**: Protection of sensitive information through environment variables
- **Request Limiting**: Prevention of excessive API calls

## Monitoring & Observability

- **Structured Logging**: Detailed logs for debugging and performance analysis
- **Error Tracking**: Exception monitoring and alerting
- **Performance Metrics**: Response time, tool usage, success rate tracking
- **Phoenix Integration**: Advanced monitoring and tracing

## MCP Tools Extension

To add new tools:

1. Create new tool file in `src/mcp_client/server/tools/`
2. Add tool configuration to `config/mcp_config.json`
3. Update agent prompts with tool usage instructions

### Available MCP Tools
- **document_analyzer**: Document structure and content analysis
- **image_analyzer**: Construction blueprint image analysis
- **text_extractor**: Text extraction from documents
- **opensearch_tools**: Semantic and vector search capabilities
- **basic_tools**: Utility functions and basic operations

## Environment Variables

The backend requires the following environment variables (managed in project root `.env`):

```env
# AWS Configuration
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=your-account-id

# API Gateway URLs (auto-generated by infrastructure)
API_GATEWAY_URL=https://your-api-gateway.amazonaws.com
WEBSOCKET_API_URL=wss://your-websocket-api.amazonaws.com

# OpenSearch Configuration
OPENSEARCH_ENDPOINT=https://your-opensearch-domain.amazonaws.com

# AI Model Configuration
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

# Local Development
MCP_WORKSPACE_DIR=/path/to/workspace
```

## Development & Testing

### Local Development
```bash
# Start
cd packages/backend
python main.py
```

### Configuration Management
- **Agent Configuration**: `src/agent/react_agent/prompt/agent_profile.yaml`
- **Model Settings**: `config/models.yaml`
- **MCP Tools**: `config/mcp_config.json`

## Contributing

1. **New MCP Tool Development**
2. **ReAct Pattern Improvements**
3. **Evaluation Metrics Addition**
4. **Performance Optimization**

### Development Guidelines
- Follow ReAct pattern principles
- Ensure MCP tool integration
- Add comprehensive logging
- Include evaluation metrics
- Maintain backward compatibility

---

**Note**: This backend provides **only AI chat API** and does not include other REST API endpoints. All functionality is handled by the AI agent through MCP tools. The MCP server implementation is located in `src/mcp_client/server/` and tool configurations are managed through `config/mcp_config.json`.