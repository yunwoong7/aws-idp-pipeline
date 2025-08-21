"""
Cross-platform path resolver utility for AWS IDP
Replaces hardcoded path patterns with environment variable-based resolution
"""

import os
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Try to get root path, handle Docker environment gracefully
try:
    root_path = Path(__file__).parents[4]
    env_path = root_path / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except IndexError:
    # In Docker container, the path structure is different
    # Try to load from /app/.env if it exists
    docker_env_path = Path('/app/.env')
    if docker_env_path.exists():
        load_dotenv(docker_env_path)
    else:
        # Load from environment variables only
        load_dotenv()

class PathResolver:
    """Resolves paths using environment variables instead of hardcoded relative paths"""
    
    def __init__(self):
        self._project_root: Optional[Path] = None
        self._mcp_workspace: Optional[Path] = None
    
    @property
    def project_root(self) -> Path:
        """Get the project root directory from environment variable or detect it"""
        if self._project_root is None:
            # Try environment variable first
            env_root = os.getenv('PROJECT_ROOT')
            if env_root:
                self._project_root = Path(env_root).resolve()
            else:
                # Fallback: detect from current file location
                # This assumes the file is in packages/backend/src/utils/
                current_file = Path(__file__).resolve()
                
                # Check if we're in a devcontainer environment
                if str(current_file).startswith('/workspaces/'):
                    # In devcontainer, use workspaces path
                    parts = current_file.parts
                    workspace_idx = parts.index('workspaces')
                    if workspace_idx + 1 < len(parts):
                        self._project_root = Path('/').joinpath(*parts[:workspace_idx + 2])
                    else:
                        self._project_root = current_file.parents[4]
                else:
                    # Regular environment or Docker
                    try:
                        self._project_root = current_file.parents[4]  # Go up 4 levels
                    except IndexError:
                        # In Docker container, use /app as project root
                        self._project_root = Path('/app')
        
        return self._project_root
    
    @property
    def mcp_workspace(self) -> Path:
        """Get the MCP workspace directory (system-level for cross-platform access)"""
        if self._mcp_workspace is None:
            # Try environment variable first
            env_workspace = os.getenv('MCP_WORKSPACE_DIR')
            if env_workspace:
                self._mcp_workspace = Path(env_workspace)
            else:
                # Fallback: use system-level directory based on OS
                import platform
                system = platform.system().lower()
                if system == 'windows':
                    self._mcp_workspace = Path('C:/aws-idp-pipeline/MCP')
                else:
                    self._mcp_workspace = Path('/aws-idp-pipeline/MCP')
        
        return self._mcp_workspace
    
    def get_backend_root(self) -> Path:
        """Get the backend package root directory"""
        return self.project_root / 'packages' / 'backend'
    
    def get_mcp_server_root(self) -> Path:
        """Get the MCP server root directory"""
        return self.get_backend_root() / 'src' / 'mcp_client' / 'server'
    
    def get_config_path(self, config_name: str) -> Path:
        """Get path to a configuration file in the backend"""
        return self.get_backend_root() / 'config' / config_name
    
    def _update_mcp_config_paths(self, config_path: Path) -> None:
        """Update hardcoded paths in mcp_config.json to match current environment"""
        if not config_path.exists():
            return
            
        try:
            # Read current config
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Get current project root
            current_root = str(self.project_root)
            
            # Update paths in the config
            updated = False
            if 'mcpServers' in config:
                for server_name, server_config in config['mcpServers'].items():
                    if 'args' in server_config:
                        for i, arg in enumerate(server_config['args']):
                            # Check if this arg contains a hardcoded path that needs updating
                            if isinstance(arg, str):
                                # Handle basic-server path (packages/backend/src/mcp_client/server)
                                if '/packages/backend/src/mcp_client/server' in arg and not arg.startswith(current_root):
                                    new_path = str(self.get_mcp_server_root())
                                    server_config['args'][i] = new_path
                                    updated = True
                                # Handle filesystem server path (mcp-workspace)
                                elif '/mcp-workspace' in arg and not arg.startswith(current_root):
                                    new_path = str(self.project_root / 'mcp-workspace')
                                    server_config['args'][i] = new_path
                                    updated = True
                                # Handle any other hardcoded project paths
                                elif arg.count('/') > 2 and not arg.startswith(current_root) and ('aws-idp-pipeline' in arg or 'PersonalProjects' in arg):
                                    # This looks like a hardcoded absolute path that should be updated
                                    if '/mcp-workspace' in arg:
                                        new_path = str(self.project_root / 'mcp-workspace')
                                        server_config['args'][i] = new_path
                                        updated = True
                                    elif '/packages/backend' in arg:
                                        # Try to extract the relative part and rebuild
                                        parts = arg.split('/packages/backend')
                                        if len(parts) > 1:
                                            relative_part = 'packages/backend' + parts[1]
                                            new_path = str(self.project_root / relative_part)
                                            server_config['args'][i] = new_path
                                            updated = True
            
            # Write back if updated
            if updated:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)
                    
        except (json.JSONDecodeError, IOError) as e:
            # If we can't read/write the config, just continue
            print(f"Warning: Could not update MCP config paths: {e}")
    
    def get_mcp_config_path(self) -> Path:
        """Get path to MCP configuration file (ECS vs local)"""
        # Check if we're in ECS environment
        if os.getenv('AWS_EXECUTION_ENV'):
            # ECS environment - use Docker-specific config
            docker_config = os.path.join('/app', 'config', 'mcp_config_docker.json')
            return docker_config
        
        # Default to regular config (local development)
        config_path = self.get_config_path('mcp_config.json')
        
        # Update paths in the config file to match current environment
        self._update_mcp_config_paths(config_path)
        
        return config_path
    
    def ensure_mcp_workspace(self) -> bool:
        """Ensure MCP workspace directory exists"""
        try:
            self.mcp_workspace.mkdir(parents=True, exist_ok=True)
            return True
        except (PermissionError, OSError):
            return False
    
    def get_relative_to_project(self, absolute_path: Path) -> Path:
        """Convert absolute path to relative path from project root"""
        try:
            return absolute_path.relative_to(self.project_root)
        except ValueError:
            # Path is not relative to project root
            return absolute_path


# Global instance for easy import
path_resolver = PathResolver()


def get_project_root() -> Path:
    """Convenience function to get project root"""
    return path_resolver.project_root


def get_mcp_workspace() -> Path:
    """Convenience function to get MCP workspace"""
    return path_resolver.mcp_workspace


def get_backend_root() -> Path:
    """Convenience function to get backend root"""
    return path_resolver.get_backend_root()


def get_mcp_server_root() -> Path:
    """Convenience function to get MCP server root"""
    return path_resolver.get_mcp_server_root()