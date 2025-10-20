"""
Configuration management for Strands Analysis Agent
"""
import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

class Config:
    """Configuration manager for Strands Analysis Agent"""
    
    def __init__(self):
        # Base directory paths
        self.base_dir = Path(__file__).resolve().parent
        self.backend_dir = self.base_dir.parent.parent.parent
        
        # Configuration paths
        self.models_config_path = self.backend_dir / "config" / "models.yaml"
        self.mcp_config_path = self.backend_dir / "config" / "mcp_config.json"
        
        # User settings
        self.user_settings_dir = Path.home() / ".mcp-client"
        self.user_model_file = self.user_settings_dir / "aws_idp_mcp_client.json"
        
        # API configuration
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        # self.api_base_url = "https://k19cn9zp70.execute-api.us-west-2.amazonaws.com"
        
        # MCP server configuration
        self.mcp_server_host = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
        self.mcp_server_port = int(os.getenv("MCP_SERVER_PORT", "9001"))
        
        # Default model
        self.default_model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        
    def get_user_model(self) -> str:
        """Load user model preference"""
        try:
            if self.user_model_file.exists():
                with open(self.user_model_file, "r") as f:
                    data = json.load(f)
                    return data.get("model_id", self.default_model_id)
        except Exception:
            pass
        return self.default_model_id
    
    def load_model_config(self, model_id: str) -> Dict[str, Any]:
        """Load model configuration"""
        try:
            if self.models_config_path.exists():
                with open(self.models_config_path, "r") as f:
                    models_config = yaml.safe_load(f)
                
                # Search for model configuration
                for provider_id, provider_data in models_config.get("providers", {}).items():
                    for model_config_id, model_data in provider_data.get("models", {}).items():
                        if model_data.get("id") == model_id:
                            return model_data
        except Exception:
            pass
        
        return {"max_output_tokens": 4096}
    
    def get_app_config(self) -> Dict[str, Any]:
        """Get application configuration for MCP tools"""
        return {
            "api_base_url": self.api_base_url
        }

# Global config instance
config = Config()