"""
Configuration management for MCP server
"""
import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any

# Import the new path resolver
try:
    from ...utils.path_resolver import path_resolver
except ImportError:
    # Fallback for development
    import sys
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from utils.path_resolver import path_resolver

def get_app_config() -> Dict[str, Any]:
    """Get application configuration"""
    # Load environment variables using path resolver
    try:
        env_path = path_resolver.project_root / '.env'
        load_dotenv(env_path)
        print(f"Loaded environment from: {env_path}")
    except Exception as e:
        print(f"Error loading environment variables: {e}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Project root: {path_resolver.project_root}")
        print(f"Environment path: {path_resolver.project_root / '.env'}")
        raise e
    
    config = {
        'model_id': os.getenv("MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
        'port': os.getenv("MCP_PORT", "8765"),
        'api_base_url': os.getenv("API_BASE_URL", "http://localhost:8000"),
        'project_state_file': os.path.join(tempfile.gettempdir(), "mcp_project_state.json"),
        'opensearch_index_name': os.getenv("OPENSEARCH_INDEX_NAME", "construction-site-analysis"),
        'min_score': float(os.getenv("MIN_SCORE", "0.1")),
        'max_results': int(os.getenv("MAX_RESULTS", "5"))
    }
    
    return config