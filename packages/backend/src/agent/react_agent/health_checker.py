"""
MCPHealthChecker - MCP service health check management class
"""
import asyncio
import logging
import os
from typing import Dict, List, Any
from datetime import datetime, timezone

from .utils import retry_with_backoff

logger = logging.getLogger(__name__)


class MCPHealthChecker:
    """
    MCP service health check management class
    """
    
    def __init__(self, mcp_service):
        """
        MCPHealthChecker initialization
        
        Args:
            mcp_service: MCP service instance
        """
        self.mcp_service = mcp_service
        self.mcp_health_status = {
            "healthy": False, 
            "last_check": None, 
            "tools_count": 0,
            "error": None
        }

    async def check_mcp_health(self) -> Dict[str, Any]:
        """
        MCP service health check
        
        Returns:
            health status information
        """
        try:
            logger.info("MCP service health check started")
            
            # get tool list from MCP service (with timeout)
            async def get_tools():
                return self.mcp_service.get_tools()
            
            health_check_timeout = float(os.getenv("MCP_HEALTH_CHECK_TIMEOUT", "10.0"))
            tools = await asyncio.wait_for(get_tools(), timeout=health_check_timeout)
            
            tools_count = len(tools) if tools else 0
            is_healthy = tools_count > 0
            
            self.mcp_health_status = {
                "healthy": is_healthy,
                "last_check": datetime.now(tz=timezone.utc).isoformat(),
                "tools_count": tools_count,
                "error": None
            }
            
            if is_healthy:
                logger.info(f"MCP service healthy - {tools_count} tools available")
            else:
                logger.warning("MCP service unhealthy - no tools available")
                
            return self.mcp_health_status
            
        except asyncio.TimeoutError:
            error_msg = "MCP service health check timeout"
            logger.error(error_msg)
            self.mcp_health_status = {
                "healthy": False,
                "last_check": datetime.now(tz=timezone.utc).isoformat(),
                "tools_count": 0,
                "error": error_msg
            }
            return self.mcp_health_status
            
        except Exception as e:
            error_msg = f"MCP service health check failed: {str(e)}"
            logger.error(error_msg)
            self.mcp_health_status = {
                "healthy": False,
                "last_check": datetime.now(tz=timezone.utc).isoformat(),
                "tools_count": 0,
                "error": error_msg
            }
            return self.mcp_health_status

    async def get_tools_with_health_check(self) -> List[Any]:
        """
        Get tool list with health check
        
        Returns:
            available tool list
        """
        # if health check is too old or failed, re-check
        if (not self.mcp_health_status.get("healthy", False) or 
            not self.mcp_health_status.get("last_check")):
            await self.check_mcp_health()
        
        if not self.mcp_health_status.get("healthy", False):
            logger.warning("MCP service unhealthy - empty tool list")
            return []
        
        try:
            # get tool list with retry logic
            async def get_tools():
                return self.mcp_service.get_tools()
            
            tools = await retry_with_backoff(get_tools, max_retries=2, timeout=15.0)
            return tools if tools else []
            
        except Exception as e:
            logger.error(f"Failed to get tool list: {str(e)}")
            # update health status
            self.mcp_health_status["healthy"] = False
            self.mcp_health_status["error"] = str(e)
            return []

    def get_health_status(self) -> Dict[str, Any]:
        """
        Return current health status
        
        Returns:
            health status information
        """
        return self.mcp_health_status.copy()

    def is_healthy(self) -> bool:
        """
        Check health status
        
        Returns:
            health status (True: healthy, False: unhealthy)
        """
        return self.mcp_health_status.get("healthy", False)

    def get_tools_count(self) -> int:
        """
        Return number of available tools
        
        Returns:
            number of tools
        """
        return self.mcp_health_status.get("tools_count", 0)

    def get_last_check_time(self) -> str:
        """
        Return last check time
        
        Returns:
            last check time (ISO format)
        """
        return self.mcp_health_status.get("last_check", "")

    def get_error_message(self) -> str:
        """
        Return error message
        
        Returns:
            error message (empty string if no error)
        """
        return self.mcp_health_status.get("error", "") or ""

    def reset_health_status(self) -> None:
        """
        Reset health status
        """
        self.mcp_health_status = {
            "healthy": False,
            "last_check": None,
            "tools_count": 0,
            "error": None
        }
        logger.info("MCP health status reset")

    def set_unhealthy(self, error_message: str) -> None:
        """
        Set health status to unhealthy
        
        Args:
            error_message: error message
        """
        self.mcp_health_status = {
            "healthy": False,
            "last_check": datetime.now(tz=timezone.utc).isoformat(),
            "tools_count": 0,
            "error": error_message
        }
        logger.warning(f"MCP health status set to unhealthy: {error_message}")

    async def force_health_check(self) -> Dict[str, Any]:
        """
        Force health check
        
        Returns:
            health status information
        """
        logger.info("Force MCP health check")
        return await self.check_mcp_health()

    def should_check_health(self, check_interval_seconds: int = 300) -> bool:
        """
        Check if health check is needed
        
        Args:
            check_interval_seconds: check interval (seconds)
            
        Returns:
            health check needed (True: needed, False: not needed)
        """
        if not self.mcp_health_status.get("last_check"):
            return True
            
        try:
            last_check = datetime.fromisoformat(self.mcp_health_status["last_check"].replace('Z', '+00:00'))
            now = datetime.now(tz=timezone.utc)
            elapsed = (now - last_check).total_seconds()
            
            return elapsed >= check_interval_seconds
            
        except Exception as e:
            logger.error(f"Error checking health: {e}")
            return True