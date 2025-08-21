"""
MCP Tools Management API Router
"""
import json
import logging
import os
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from src.mcp_client.mcp_service import MCPService

# logging configuration
logger = logging.getLogger(__name__)

# MCP config file path using path resolver
try:
    from ..utils.path_resolver import path_resolver
    MCP_CONFIG_PATH = str(path_resolver.get_mcp_config_path())
    logger.info(f"Using MCP config path: {MCP_CONFIG_PATH}")
except ImportError:
    # Fallback to original logic
    BASE_DIR = Path(__file__).resolve().parent.parent
    MCP_CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", os.path.join(BASE_DIR, "../config/mcp_config.json"))
    logger.warning("Path resolver not available, using fallback path logic")

# create router
router = APIRouter(prefix="/api/mcp-tools", tags=["mcp-tools"])

# request and response models
class MCPToolConfig(BaseModel):
    """MCP tool config model"""
    name: str
    config: Dict[str, Any]

class MCPToolsResponse(BaseModel):
    """MCP tool list response model"""
    tools: Dict[str, Any]

class MCPToolInfo(BaseModel):
    """MCP tool info model"""
    name: str
    description: Optional[str] = None
    status: Optional[str] = "ready"

class MCPServerInfo(BaseModel):
    """MCP server info model"""
    name: str
    status: str
    config: Dict[str, Any]
    tools: List[MCPToolInfo]

class MCPCompleteInfoResponse(BaseModel):
    """MCP all server and tool info response model"""
    servers: List[MCPServerInfo]

class MCPRestartResponse(BaseModel):
    """MCP restart response model"""
    success: bool
    message: str

# add restart lock variable to prevent multiple restart requests
_restart_lock = asyncio.Lock()
_is_restarting = False

# get MCP service instance
def get_mcp_service():
    """get MCP service instance"""
    service = MCPService(MCP_CONFIG_PATH)
    return service

def load_mcp_config() -> Dict[str, Any]:
    """
    load MCP config file
    
    Returns:
        Dict: MCP config data
    """
    try:
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r") as f:
                config = json.load(f)
                
            # check structure and initialize
            if "mcpServers" not in config:
                config["mcpServers"] = {}
                
            return config
        else:
            # if file not exists, create default structure
            return {"mcpServers": {}}
    except Exception as e:
        logger.error(f"MCP config load error: {e}")
        return {"mcpServers": {}}

def save_mcp_config(config: Dict[str, Any]) -> bool:
    """
    save MCP config file
    
    Args:
        config: data to save
        
    Returns:
        bool: save success or not
    """
    try:
        # check directory and create
        os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
        
        # save config
        with open(MCP_CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
            
        return True
    except Exception as e:
        logger.error(f"MCP config save error: {e}")
        return False

async def restart_mcp_service(mcp_service: MCPService) -> Dict[str, Any]:
    """
    restart MCP service
    
    Args:
        mcp_service: MCP service instance
        
    Returns:
        Dict: restart result
    """
    global _is_restarting
    
    # prevent duplicate execution if already restarting
    async with _restart_lock:
        if _is_restarting:
            return {
                "success": False, 
                "message": "MCP service is already restarting due to another request. Please try again later."
            }
        _is_restarting = True
    
    try:
        logger.info("MCP service restart attempt")
        
        # actually restart the service by completely shutting down and restarting
        try:
            logger.info("MCP service shutdown in progress...")
            if hasattr(mcp_service, '_running') and mcp_service._running:
                await mcp_service.shutdown()
                logger.info("MCP service shutdown completed")
            else:
                logger.info("MCP service is not running, skipping shutdown process")
        except Exception as e:
            logger.error(f"MCP service shutdown error: {e}")
            # continue even if error occurs - try to start
        
        # wait for a moment (stabilization time after service shutdown)
        await asyncio.sleep(1.0)
        
        # restart the service
        logger.info("MCP service startup in progress...")
        await mcp_service.startup()
        
        server_count = len(mcp_service.server_names) if hasattr(mcp_service, 'server_names') else 0
        tool_count = len(mcp_service.tools) if hasattr(mcp_service, 'tools') and mcp_service.tools else 0
        
        logger.info(f"MCP service startup completed (servers: {server_count}, tools: {tool_count})")
        
        return {
            "success": True, 
            "message": f"MCP service restarted successfully. {server_count} servers and {tool_count} tools are activated."
        }
    except Exception as e:
        logger.error(f"MCP service restart error: {e}")
        return {"success": False, "message": f"MCP service restart failed: {str(e)}"}
    finally:
        # release restart state
        async with _restart_lock:
            _is_restarting = False

@router.get("", response_model=MCPCompleteInfoResponse)
async def get_mcp_tools(mcp_service: MCPService = Depends(get_mcp_service)):
    """
    get MCP server and tool list
    
    Returns:
        MCPCompleteInfoResponse: response with all server and tool info
    """
    try:
        logger.info("MCP tool list get API called")
        
        # get server list from config file
        config = load_mcp_config()
        mcpServers = config.get("mcpServers", {})
        
        # list to contain server info
        server_infos = []
        
        # check if MCP service is running
        is_service_running = hasattr(mcp_service, '_running') and mcp_service._running
        
        if not is_service_running:
            logger.warning("MCP service is not running. return offline info only.")
        
        # list of running servers (only if service is running)
        running_servers = mcp_service.get_servers() if is_service_running and hasattr(mcp_service, 'get_servers') else []
        
        # list of tools (only if service is running)
        all_tools = mcp_service.get_tools() if is_service_running else []
        
        # Try to get server-specific tool mapping like pace-mcp-client
        all_tools_dict = {}
        if is_service_running:
            client = mcp_service.get_client()
            if client:
                logger.debug(f"Client type: {type(client)}")
                logger.debug(f"Client attributes: {[attr for attr in dir(client) if not attr.startswith('_')]}")
                
                if hasattr(client, 'server_name_to_tools'):
                    all_tools_dict = client.server_name_to_tools
                    logger.debug(f"Found server_name_to_tools: {list(all_tools_dict.keys())}")
                elif hasattr(client, 'servers'):
                    logger.debug(f"Found client.servers: {list(client.servers.keys())}")
                    # Try to get tools from individual server connections
                    all_tools_dict = {}
                    servers_have_tools = False
                    
                    for server_name, server_conn in client.servers.items():
                        logger.debug(f"Server '{server_name}' connection type: {type(server_conn)}")
                        logger.debug(f"Server '{server_name}' attributes: {[attr for attr in dir(server_conn) if not attr.startswith('_')]}")
                        # Try to extract tools from server connection
                        server_tools = []
                        if hasattr(server_conn, 'list_tools'):
                            try:
                                server_tools = server_conn.list_tools()
                                logger.debug(f"Server '{server_name}' list_tools returned: {len(server_tools)} tools")
                                if server_tools:
                                    servers_have_tools = True
                            except Exception as e:
                                logger.debug(f"Server '{server_name}' list_tools failed: {e}")
                        
                        all_tools_dict[server_name] = server_tools
                    
                    # If no servers have tools, fall back to smart classification
                    if not servers_have_tools:
                        logger.debug("No tools found from individual servers, falling back to smart classification")
                        all_tools_dict = {}
                        
                        # Initialize all servers with empty lists
                        for server_name in running_servers:
                            all_tools_dict[server_name] = []
                        
                        # Define tool patterns for each server
                        server_patterns = {
                            "nova-canvas": [
                                "text_to_image", "show_image", "color_guided_generation", 
                                "background_removal", "image", "canvas", "generate", "visual"
                            ],
                            "filesystem": [
                                "read_file", "write_file", "edit_file", "create_directory", 
                                "list_directory", "move_file", "search_files", "get_file_info",
                                "list_allowed_directories", "directory_tree", "list_directory_with_sizes",
                                "read_multiple_files", "file", "directory", "path"
                            ],
                            "basic-server": [
                                "project_info", "get_document_info", "hybrid_search", 
                                "get_page_analysis_details", "get_documents_list", "add_user_content",
                                "remove_user_content", "add", "echo",
                                "document", "page", "project", "analysis", "search"
                            ]
                        }
                        
                        # Classify tools based on patterns
                        for tool in all_tools:
                            if not hasattr(tool, "name"):
                                continue
                            
                            tool_name = tool.name.lower()
                            assigned = False
                            
                            # Check each server's patterns
                            for server_name, patterns in server_patterns.items():
                                if server_name in running_servers:
                                    # Check if tool name matches any pattern
                                    if any(pattern in tool_name for pattern in patterns):
                                        all_tools_dict[server_name].append(tool)
                                        logger.debug(f"Assigned '{tool.name}' to '{server_name}' based on pattern matching")
                                        assigned = True
                                        break
                            
                            # If no pattern matched, assign to basic-server as fallback
                            if not assigned and "basic-server" in running_servers:
                                all_tools_dict["basic-server"].append(tool)
                                logger.debug(f"Assigned '{tool.name}' to 'basic-server' as fallback")
                        
                        # Log final distribution
                        for server_name, tools in all_tools_dict.items():
                            logger.debug(f"Server '{server_name}': {len(tools)} tools")
                else:
                    logger.debug(f"server_name_to_tools not available, using smart tool classification")
                    # Smart tool classification based on tool names and patterns
                    all_tools_dict = {}
                    
                    # Initialize all servers with empty lists
                    for server_name in running_servers:
                        all_tools_dict[server_name] = []
                    
                    # Define tool patterns for each server
                    server_patterns = {
                        "nova-canvas": [
                            "text_to_image", "show_image", "color_guided_generation", 
                            "background_removal", "image", "canvas", "generate", "visual"
                        ],
                        "filesystem": [
                            "read_file", "write_file", "edit_file", "create_directory", 
                            "list_directory", "move_file", "search_files", "get_file_info",
                            "list_allowed_directories", "directory_tree", "list_directory_with_sizes",
                            "read_multiple_files", "file", "directory", "path"
                        ],
                        "basic-server": [
                            "project_info", "get_document_info", "hybrid_search", 
                            "get_page_analysis_details", "get_documents_list", "add_user_content",
                            "remove_user_content", "add", "echo",
                            "document", "page", "project", "analysis", "search"
                        ]
                    }
                    
                    # Classify tools based on patterns
                    for tool in all_tools:
                        if not hasattr(tool, "name"):
                            continue
                        
                        tool_name = tool.name.lower()
                        assigned = False
                        
                        # Check each server's patterns
                        for server_name, patterns in server_patterns.items():
                            if server_name in running_servers:
                                # Check if tool name matches any pattern
                                if any(pattern in tool_name for pattern in patterns):
                                    all_tools_dict[server_name].append(tool)
                                    logger.debug(f"Assigned '{tool.name}' to '{server_name}' based on pattern matching")
                                    assigned = True
                                    break
                        
                        # If no pattern matched, assign to basic-server as fallback
                        if not assigned and "basic-server" in running_servers:
                            all_tools_dict["basic-server"].append(tool)
                            logger.debug(f"Assigned '{tool.name}' to 'basic-server' as fallback")
                    
                    # Log final distribution
                    for server_name, tools in all_tools_dict.items():
                        logger.debug(f"Server '{server_name}': {len(tools)} tools")
        
        # configure info for each server in config file
        for server_name, server_config in mcpServers.items():
            server_status = "offline"
            server_tools = []
            
            # check if server is running
            if is_service_running and server_name in running_servers:
                server_status = "online"
                
                # Get tools for this server from all_tools_dict
                if server_name in all_tools_dict:
                    tools_list = all_tools_dict.get(server_name, [])
                    logger.debug(f"Server '{server_name}' has {len(tools_list)} tools from mapping")
                    
                    # configure tool info
                    for tool in tools_list:
                        if not hasattr(tool, "name"):
                            continue
                            
                        # extract tool name and description
                        name = tool.name
                        description = ""
                        if hasattr(tool, "description"):
                            description = tool.description
                            
                        # add tool info
                        server_tools.append(MCPToolInfo(
                            name=name,
                            description=description,
                            status="ready"
                        ))
                else:
                    logger.debug(f"No tools found for server '{server_name}' in mapping")
                
                logger.debug(f"server '{server_name}' has {len(server_tools)} tools in response")
            
            # add server info
            server_infos.append(MCPServerInfo(
                name=server_name,
                status=server_status,
                config=server_config,
                tools=server_tools
            ))
        
        logger.info(f"MCP tool list get completed: {len(server_infos)} servers")
        return MCPCompleteInfoResponse(servers=server_infos)
    except Exception as e:
        logger.error(f"MCP tool list get error: {e}")
        raise HTTPException(status_code=500, detail=f"failed to get tool list: {str(e)}")

@router.post("")
async def add_mcp_tool(tool: MCPToolConfig, mcp_service: MCPService = Depends(get_mcp_service)):
    """
    add MCP tool
    
    Args:
        tool: tool info to add
        
    Returns:
        Dict: success message
    """
    try:
        config = load_mcp_config()
        
        # check if tool name already exists
        if tool.name in config["mcpServers"]:
            raise HTTPException(status_code=400, detail=f"tool name already exists: {tool.name}")
        
        # add tool
        config["mcpServers"][tool.name] = tool.config
        
        # save config
        if not save_mcp_config(config):
            raise HTTPException(status_code=500, detail="failed to save tool config")
        
        # restart the service
        restart_result = await restart_mcp_service(mcp_service)
        if restart_result["success"]:
            logger.info(f"MCP service restart success: {tool.name} added")
            return {"message": f"tool added successfully: {tool.name}", "restart": restart_result}
        else:
            logger.warning(f"MCP service restart failed: {restart_result['message']}")
            return {"message": f"tool added successfully: {tool.name}, but service restart failed", "restart": restart_result}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MCP tool add error: {e}")
        raise HTTPException(status_code=500, detail=f"failed to add tool: {str(e)}")

@router.delete("/{tool_name}")
async def delete_mcp_tool(tool_name: str, mcp_service: MCPService = Depends(get_mcp_service)):
    """
    delete MCP tool
    
    Args:
        tool_name: tool name to delete
        
    Returns:
        Dict: success message
    """
    try:
        config = load_mcp_config()
        
        # check if tool exists
        if tool_name not in config["mcpServers"]:
            raise HTTPException(status_code=404, detail=f"tool not found: {tool_name}")
        
        # delete tool
        del config["mcpServers"][tool_name]
        
        # save config
        if not save_mcp_config(config):
            raise HTTPException(status_code=500, detail="failed to save tool config")
        
        # restart the service
        restart_result = await restart_mcp_service(mcp_service)
        if restart_result["success"]:
            logger.info(f"MCP service restart success: {tool_name} deleted")
            return {"message": f"tool deleted successfully: {tool_name}", "restart": restart_result}
        else:
            logger.warning(f"MCP service restart failed: {restart_result['message']}")
            return {"message": f"tool deleted successfully: {tool_name}, but service restart failed", "restart": restart_result}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MCP tool delete error: {e}")
        raise HTTPException(status_code=500, detail=f"failed to delete tool: {str(e)}")

@router.put("/{tool_name}")
async def update_mcp_tool(tool_name: str, updated_tool: MCPToolConfig, mcp_service: MCPService = Depends(get_mcp_service)):
    """
    update MCP tool
    
    Args:
        tool_name: tool name to update
        updated_tool: updated tool info
        
    Returns:
        Dict: success message
    """
    try:
        logger.info(f"MCP tool update request: {tool_name}")
        config = load_mcp_config()
        
        # check if tool exists
        if tool_name not in config["mcpServers"]:
            raise HTTPException(status_code=404, detail=f"tool not found: {tool_name}")
            
        # if tool name is changed
        if tool_name != updated_tool.name:
            logger.info(f"tool name changed: {tool_name} -> {updated_tool.name}")
            
            # check if new name is already exists
            if updated_tool.name in config["mcpServers"]:
                raise HTTPException(status_code=400, detail=f"tool name already exists: {updated_tool.name}")
                
            # delete old item
            del config["mcpServers"][tool_name]
            
            # add new item
            config["mcpServers"][updated_tool.name] = updated_tool.config
        else:
            # update config
            config["mcpServers"][tool_name] = updated_tool.config
            
        # save config
        if not save_mcp_config(config):
            raise HTTPException(status_code=500, detail="failed to save tool config")
        
        # restart the service
        restart_result = await restart_mcp_service(mcp_service)
        if restart_result["success"]:
            logger.info(f"MCP service restart success: {updated_tool.name} updated")
            return {"message": f"tool updated successfully: {updated_tool.name}", "restart": restart_result}
        else:
            logger.warning(f"MCP service restart failed: {restart_result['message']}")
            return {"message": f"tool updated successfully: {updated_tool.name}, but service restart failed", "restart": restart_result}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MCP tool update error: {e}")
        raise HTTPException(status_code=500, detail=f"failed to update tool: {str(e)}")

@router.post("/restart", response_model=MCPRestartResponse)
async def restart_mcp(mcp_service: MCPService = Depends(get_mcp_service)):
    """
    restart MCP service manually
    
    Returns:
        MCPRestartResponse: restart result
    """
    try:
        logger.info("MCP service manual restart request")
        restart_result = await restart_mcp_service(mcp_service)
        
        return MCPRestartResponse(
            success=restart_result["success"],
            message=restart_result["message"]
        )
    except Exception as e:
        logger.error(f"MCP service manual restart error: {e}")
        return MCPRestartResponse(
            success=False,
            message=f"MCP service restart failed: {str(e)}"
        )