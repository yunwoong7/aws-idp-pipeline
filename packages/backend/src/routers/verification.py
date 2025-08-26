"""
Content Verification API router
"""
import json
import logging
import os
from typing import Dict, Any, Optional, List, Union, Annotated

from fastapi import APIRouter, HTTPException, Request, Form, File, UploadFile, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import RunnableConfig

from src.agent.verification_agent import VerificationAgent
from src.agent.verification_agent.state import InputState

# logging configuration
logger = logging.getLogger(__name__)

# Global VerificationAgent instance
verification_agent: Optional[VerificationAgent] = None

async def get_verification_agent() -> VerificationAgent:
    """Get or create VerificationAgent instance"""
    global verification_agent
    if verification_agent is None:
        try:
            verification_agent = VerificationAgent()
            logger.info("VerificationAgent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize VerificationAgent: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize VerificationAgent: {str(e)}")
    
    return verification_agent

# create router
router = APIRouter(prefix="/api", tags=["verification"])

# Request and response models
class VerificationRequest(BaseModel):
    """Verification request model"""
    source_document_ids: List[str]
    target_document_id: str
    index_id: Optional[str] = None
    model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

class VerificationClaim(BaseModel):
    """Verification claim model"""
    id: str
    claim: str
    status: str  # VERIFIED, CONTRADICTED, NOT_FOUND
    evidence: Optional[str] = None
    source_document_id: Optional[str] = None
    confidence: Optional[float] = None

class VerificationResponse(BaseModel):
    """Verification response model"""
    success: bool
    claims: List[VerificationClaim]
    summary: Dict[str, Any]
    message: str

@router.post("/verification/stream")
async def verify_content_stream(
    request: Request,
    source_document_ids: str = Form(...),
    target_document_id: str = Form(...),
    index_id: Optional[str] = Form(None),
    model_id: str = Form("us.anthropic.claude-3-7-sonnet-20250219-v1:0")
):
    """
    Content verification streaming API endpoint
    
    Args:
        request: HTTP request
        source_document_ids: Comma-separated list of source document IDs
        target_document_id: Target document ID to verify
        index_id: Index ID for context
        model_id: Model ID to use
        
    Returns:
        streaming response with verification results
    """
    try:
        # Parse source document IDs
        source_ids = [doc_id.strip() for doc_id in source_document_ids.split(',') if doc_id.strip()]
        
        if not source_ids:
            raise HTTPException(status_code=400, detail="At least one source document ID is required")
        
        if not target_document_id:
            raise HTTPException(status_code=400, detail="Target document ID is required")
        
        logger.info(f"Starting verification: source_ids={source_ids}, target_id={target_document_id}, index_id={index_id}")
        
        async def stream_verification():
            """Verification streaming response generator using VerificationAgent"""
            try:
                # Get verification agent
                agent = await get_verification_agent()
                
                # Create input state
                input_state = InputState(
                    source_document_ids=source_ids,
                    target_document_id=target_document_id,
                    index_id=index_id,
                    model_id=model_id
                )
                
                # Stream through verification agent
                async for event_type, event_data in agent.astream(input_state):
                    # Transform agent events to API format
                    if event_type == "phase":
                        yield f"data: {json.dumps(event_data)}\n\n"
                    
                    elif event_type == "claim_result":
                        api_data = {
                            "type": "claim_result",
                            "claim": event_data["claim"]
                        }
                        yield f"data: {json.dumps(api_data)}\n\n"
                    
                    elif event_type == "final_result":
                        api_data = {
                            "type": "final_result",
                            **event_data
                        }
                        yield f"data: {json.dumps(api_data)}\n\n"
                        break
                    
                    elif event_type == "error":
                        api_data = {
                            "type": "error",
                            **event_data
                        }
                        yield f"data: {json.dumps(api_data)}\n\n"
                        break
                
                # End stream
                yield "data: [DONE]\n\n"
                logger.info("Verification streaming completed successfully")
                
            except Exception as e:
                logger.error(f"Verification streaming error: {e}")
                error_data = {
                    "type": "error",
                    "error": str(e),
                    "phase": "error"
                }
                yield f"data: {json.dumps(error_data)}\n\n"
        
        return StreamingResponse(
            stream_verification(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except Exception as e:
        logger.error(f"Verification request error: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@router.post("/verification")
async def verify_content(request: VerificationRequest):
    """
    Content verification API endpoint (non-streaming)
    
    Args:
        request: Verification request data
        
    Returns:
        verification results
    """
    try:
        logger.info(f"Non-streaming verification: source_ids={request.source_document_ids}, target_id={request.target_document_id}")
        
        # Get verification agent
        agent = await get_verification_agent()
        
        # Create input state
        input_state = InputState(
            source_document_ids=request.source_document_ids,
            target_document_id=request.target_document_id,
            index_id=request.index_id,
            model_id=request.model_id
        )
        
        # Run verification
        result = await agent.ainvoke(input_state)
        
        # Convert to API response format
        api_claims = []
        for claim_dict in result.get("claims", []):
            api_claims.append(VerificationClaim(**claim_dict))
        
        return VerificationResponse(
            success=result.get("success", False),
            claims=api_claims,
            summary=result.get("summary", {}),
            message=result.get("message", "")
        )
        
    except Exception as e:
        logger.error(f"Verification error: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@router.get("/verification/health")
async def verification_health():
    """
    Verification service health check
    
    Returns:
        health status information
    """
    try:
        # Try to get agent and check health
        try:
            agent = await get_verification_agent()
            agent_status = agent.get_health_status()
            return {
                "status": "healthy",
                "service": "content_verification",
                "version": "1.0.0",
                **agent_status
            }
        except Exception as agent_error:
            logger.warning(f"Agent health check failed: {agent_error}")
            return {
                "status": "degraded",
                "service": "content_verification", 
                "version": "1.0.0",
                "error": str(agent_error),
                "timestamp": "2024-01-01T00:00:00Z"
            }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")