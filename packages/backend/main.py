"""
AWS IDP AI Analysis API server main module (MCP Client support)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from src.init import app, tracer
from src.routers import mcp_tools_router
from src.routers.branding import router as branding_router
from src.routers.analysis_agent import router as analysis_agent_router
from src.routers.search_agent import router as search_agent_router
from src.routers.verification import router as verification_router
from src.routers.auth import router as auth_router
from src.routers.document_upload import router as document_upload_router
from src.mcp_client.server.config import get_app_config

conf = get_app_config()
print(conf)


# logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import path resolver for dynamic path handling
try:
    from src.utils.path_resolver import path_resolver
    # Use dynamic path resolution
    MCP_CONFIG_PATH = str(path_resolver.get_mcp_config_path())
    logger.info(f"Using MCP config path: {MCP_CONFIG_PATH}")
    
    # Generate MCP config if it doesn't exist
    if not os.path.exists(MCP_CONFIG_PATH):
        logger.warning(f"MCP config not found at {MCP_CONFIG_PATH}, generating...")
        try:
            from src.utils.mcp_config_generator import save_mcp_config
            save_mcp_config()
            logger.info("MCP configuration generated successfully at startup")
        except Exception as e:
            logger.error(f"Failed to generate MCP config: {e}")
            
except ImportError:
    # Fallback to original logic if path resolver not available
    BASE_DIR = Path(__file__).resolve().parent
    MCP_CONFIG_PATH = os.path.join(BASE_DIR, "config/mcp_config.json")
    logger.warning("Path resolver not available, using fallback path logic")

# MCP service import
try:
    from src.mcp_client.mcp_service import MCPService
    # MCP service instance creation
    mcp_service = MCPService(MCP_CONFIG_PATH)
    MCP_AVAILABLE = True
    logger.info("MCP service loaded successfully")
except ImportError as e:
    logger.warning(f"MCP service not available: {str(e)}")
    mcp_service = None
    MCP_AVAILABLE = False

# Lifespan event handler definition
@asynccontextmanager
async def lifespan(app: FastAPI):
    """async context manager for application lifecycle management"""
    # startup event
    logger.info("AWS IDP AI Analysis API server starting...")
    if MCP_AVAILABLE and mcp_service:
        try:
            await mcp_service.startup()
            logger.info("MCP service startup complete")
        except Exception as e:
            logger.error(f"MCP service startup error: {str(e)}")
            # server will start but run without MCP service
    
    # Initialize Analysis agent on startup for better performance
    try:
        from src.routers.analysis_agent import initialize_agent_on_startup
        await initialize_agent_on_startup()
        logger.info("Analysis agent pre-initialization triggered")
    except Exception as e:
        logger.error(f"Failed to trigger Analysis agent initialization: {str(e)}")
    
    yield  # this point, the application will run
    
    # shutdown event
    logger.info("AWS IDP AI Analysis API server shutting down...")
    if MCP_AVAILABLE and mcp_service:   
        try:
            await mcp_service.shutdown()
            logger.info("MCP service shutdown complete")
        except Exception as e:
            logger.error(f"MCP service shutdown error: {str(e)}")

# add lifespan event handler to existing app for MCP support
# recreate existing app object to apply lifespan event handler
app_with_lifespan = FastAPI(
    title="AWS IDP AI Analysis API Server (MCP Enabled)",
    lifespan=lifespan
)

# copy settings from existing app to new app
for route in app.routes:
    app_with_lifespan.routes.append(route)

# replace app object with new one
app = app_with_lifespan

# add CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # limit to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# register routers
app.include_router(mcp_tools_router)  # MCP tools API router
app.include_router(analysis_agent_router)  # analysis agent API router
app.include_router(verification_router)  # content verification API router
app.include_router(search_agent_router)  # search agent API router
app.include_router(branding_router, prefix="/api/branding")  # branding API router
app.include_router(auth_router)  # authentication API router
app.include_router(document_upload_router)  # document upload API router

# default root path
@app.get("/")
async def root():
    return {"message": "AWS IDP AI Analysis API Server"}

# Debug endpoint to check MCP logs (accessible via /api path to bypass auth)
@app.get("/api/debug/mcp-logs")
async def get_mcp_debug_logs():
    """Get MCP debug logs from /tmp/mcp_debug.log"""
    try:
        with open('/tmp/mcp_debug.log', 'r') as f:
            logs = f.read()
        return {"logs": logs, "status": "success"}
    except FileNotFoundError:
        return {"logs": "No debug log file found", "status": "not_found"}
    except Exception as e:
        return {"logs": f"Error reading log: {str(e)}", "status": "error"}

# Echo endpoint
class EchoOutput(BaseModel):
    message: str

@app.get("/echo")
@tracer.capture_method
def echo(message: str) -> EchoOutput:
    return EchoOutput(message=f"Echo: {message}")

if __name__ == "__main__":
    import uvicorn
    # read port from environment variable
    port = int(os.getenv("NEXT_PUBLIC_BACKEND_PORT", "8000"))
    logger.info(f"AWS IDP AI Analysis API server (MCP Enabled) starting on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)