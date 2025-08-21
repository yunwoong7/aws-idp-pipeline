"""
Dynamic MCP configuration generator
Replaces hardcoded paths in mcp_config.json with environment-based paths
"""

import json
import os
from pathlib import Path
from typing import Dict, Any
from .path_resolver import path_resolver


def generate_mcp_config() -> Dict[str, Any]:
    """Generate MCP configuration with dynamic paths"""
    
    # Get dynamic paths
    mcp_server_path = path_resolver.get_mcp_server_root()
    mcp_workspace = path_resolver.mcp_workspace
    
    # Ensure MCP workspace exists
    path_resolver.ensure_mcp_workspace()
    
    config = {
        "mcpServers": {
            "basic-server": {
                "command": "uv",
                "args": [
                    "--directory",
                    str(mcp_server_path),
                    "run",
                    "basic_server.py"
                ]
            },
            "filesystem": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    str(mcp_workspace)
                ]
            }
        }
    }
    
    return config


def save_mcp_config(config_path: Path = None) -> Path:
    """Save generated MCP config to file"""
    if config_path is None:
        config_path = path_resolver.get_mcp_config_path()
    
    config = generate_mcp_config()
    
    # Ensure config directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    print(f"Generated MCP config at: {config_path}")
    print(f"MCP server path: {path_resolver.get_mcp_server_root()}")
    print(f"MCP workspace: {path_resolver.mcp_workspace}")
    
    return config_path


def update_mcp_config_if_needed() -> bool:
    """Update MCP config if it contains hardcoded paths"""
    config_path = path_resolver.get_mcp_config_path()
    
    if not config_path.exists():
        save_mcp_config(config_path)
        return True
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            current_config = json.load(f)
        
        # Check if config contains hardcoded paths (indicators)
        config_str = json.dumps(current_config)
        hardcoded_indicators = [
            '/Users/',  # macOS specific paths
            'C:\\',     # Windows specific paths
            '/home/',   # Linux specific paths
        ]
        
        has_hardcoded = any(indicator in config_str for indicator in hardcoded_indicators)
        
        if has_hardcoded:
            print("Detected hardcoded paths in MCP config, regenerating...")
            save_mcp_config(config_path)
            return True
        else:
            print("MCP config appears to be dynamic already")
            return False
            
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error reading MCP config, regenerating: {e}")
        save_mcp_config(config_path)
        return True


if __name__ == "__main__":
    """CLI usage for generating MCP config"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate dynamic MCP configuration")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--force", "-f", action="store_true", help="Force regeneration")
    
    args = parser.parse_args()
    
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = path_resolver.get_mcp_config_path()
    
    if args.force or not output_path.exists():
        save_mcp_config(output_path)
    else:
        update_mcp_config_if_needed()