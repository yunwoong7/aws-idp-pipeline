"""
VerificationAgent - Main Class for Content Verification
"""

import logging
from typing import Dict, List, Any, AsyncGenerator, Optional, Tuple
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.common.llm import get_llm

from .state.model import VerificationState, InputState, VerificationClaim, VerificationSummary
from .node.verification_nodes import (
    initialization_node,
    document_loading_node,
    claim_extraction_node,
    claim_verification_node,
    summary_generation_node
)

logger = logging.getLogger(__name__)

def convert_input_to_verification_state(input_state: InputState) -> VerificationState:
    """Convert InputState to VerificationState"""
    return {
        "source_document_ids": input_state.source_document_ids,
        "target_document_id": input_state.target_document_id,
        "index_id": input_state.index_id,
        "model_id": input_state.model_id,
        "messages": input_state.messages,
        "current_phase": "init",
        "current_claim_index": 0,
        "summary": {}
    }

class VerificationAgent:
    """
    Content Verification Agent
    
    Verifies factual claims in a target document against multiple source documents.
    Uses a multi-step workflow: initialization -> document loading -> claim extraction -> 
    claim verification -> summary generation.
    """
    
    def __init__(
        self,
        model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        max_tokens: int = 4096
    ):
        """
        Initialize VerificationAgent
        
        Args:
            model_id: Model ID for LLM
            max_tokens: Maximum tokens for model responses
        """
        self.model_id = model_id
        self.max_tokens = max_tokens
        
        # Initialize LLM
        self.model = get_llm(model_id=model_id, max_tokens=max_tokens)
        
        # Build workflow graph
        self.graph = self._build_graph()
        
        logger.info(f"VerificationAgent initialized with model {model_id}")
    
    def _build_graph(self) -> StateGraph:
        """Build the verification workflow graph"""
        
        # Create state graph
        workflow = StateGraph(VerificationState)
        
        # Add nodes with async wrapper for nodes that need model
        async def extract_claims(state):
            return await claim_extraction_node(state, self.model)
        
        async def verify_claims(state):
            return await claim_verification_node(state, self.model)
        
        async def generate_summary(state):
            return await summary_generation_node(state, self.model)
        
        workflow.add_node("initialization", initialization_node)
        workflow.add_node("document_loading", document_loading_node)
        workflow.add_node("claim_extraction", extract_claims)
        workflow.add_node("claim_verification", verify_claims)
        workflow.add_node("summary_generation", generate_summary)
        
        # Add edges
        workflow.add_edge(START, "initialization")
        workflow.add_edge("initialization", "document_loading")
        workflow.add_edge("document_loading", "claim_extraction")
        workflow.add_edge("claim_extraction", "claim_verification")
        workflow.add_edge("claim_verification", "summary_generation")
        workflow.add_edge("summary_generation", END)
        
        # Compile with checkpointer
        checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer)
    
    def _create_phase_handler(self, current_state: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Create phase-specific event data"""
        phase = current_state.get("current_phase", "unknown")
        
        phase_handlers = {
            "init": lambda: ("phase", {
                "phase": "init",
                "message": "Initializing verification process...",
                "source_count": len(current_state.get("source_document_ids", [])),
                "target_document": current_state.get("target_document_id", ""),
                "progress": 0.1
            }),
            
            "loading": lambda: ("phase", {
                "phase": "loading", 
                "message": f"Loading {len(current_state.get('source_document_ids', []))} source documents and 1 target document...",
                "progress": 0.2
            }),
            
            "extraction": lambda: self._handle_extraction_phase(current_state),
            
            "verification": lambda: self._handle_verification_phase(current_state),
            
            "summary": lambda: self._handle_summary_phase(current_state)
        }
        
        handler = phase_handlers.get(phase)
        if handler:
            return handler()
        
        return ("phase", {"phase": phase, "message": f"Processing {phase} phase...", "progress": 0.5})
    
    def _handle_extraction_phase(self, current_state: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Handle extraction phase events"""
        extracted_claims = current_state.get("extracted_claims", [])
        if extracted_claims:
            return ("phase", {
                "phase": "extraction",
                "message": f"Extracted {len(extracted_claims)} claims for verification",
                "claims_count": len(extracted_claims),
                "progress": 0.4
            })
        else:
            return ("phase", {
                "phase": "extraction",
                "message": "Extracting verifiable claims from target document...",
                "progress": 0.3
            })
    
    def _handle_verification_phase(self, current_state: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Handle verification phase events"""
        current_claim_idx = current_state.get("current_claim_index", 0)
        total_claims = len(current_state.get("extracted_claims", []))
        
        if total_claims > 0:
            progress = 0.4 + (current_claim_idx / total_claims) * 0.4
            return ("phase", {
                "phase": "verification",
                "message": f"Verifying claim {current_claim_idx + 1}/{total_claims}...",
                "claim_index": current_claim_idx,
                "total_claims": total_claims,
                "progress": progress
            })
        
        return ("phase", {
            "phase": "verification",
            "message": "Verifying extracted claims...",
            "progress": 0.5
        })
    
    def _handle_summary_phase(self, current_state: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Handle summary phase events"""
        summary_dict = current_state.get("summary", {})
        if summary_dict:
            return ("phase", {
                "phase": "summary",
                "message": "Verification completed successfully",
                "summary": summary_dict,
                "progress": 1.0
            })
        else:
            return ("phase", {
                "phase": "summary",
                "message": "Generating verification summary...",
                "progress": 0.9
            })
    
    async def astream(
        self,
        input_state: InputState,
        config: Optional[RunnableConfig] = None,
        **kwargs
    ) -> AsyncGenerator[Tuple[str, Dict[str, Any]], None]:
        """
        Stream verification process with real-time updates
        
        Args:
            input_state: Input state with document IDs and configuration
            config: Runnable configuration
            **kwargs: Additional parameters
            
        Yields:
            Tuple of (event_type, event_data)
        """
        # Convert InputState to VerificationState
        verification_state = convert_input_to_verification_state(input_state)
        
        # Create config if not provided
        if config is None:
            config = RunnableConfig(configurable={"thread_id": f"verification_{datetime.now().timestamp()}"})
        
        try:
            # Stream through the workflow
            async for chunk in self.graph.astream(verification_state, config):
                node_name, state_update = list(chunk.items())[0]
                current_state = state_update
                
                # Emit phase-specific events
                event_type, event_data = self._create_phase_handler(current_state)
                yield (event_type, event_data)
                
                # Send individual claim results during verification
                verification_claims = current_state.get("verification_claims", [])
                if verification_claims and current_state.get("current_phase") == "verification":
                    for claim_dict in verification_claims[-1:]:  # Only latest claim
                        claim = VerificationClaim(**claim_dict)
                        yield ("claim_result", {"claim": claim.dict()})
                
                # Check for completion
                if current_state.get("completed_at"):
                    yield ("final_result", {
                        "success": True,
                        "claims": current_state.get("verification_claims", []),
                        "summary": current_state.get("summary", {}),
                        "message": "Document verification completed successfully",
                        "started_at": current_state.get("started_at"),
                        "completed_at": current_state.get("completed_at")
                    })
                    break
                
                # Check for errors
                if current_state.get("error"):
                    yield ("error", {
                        "error": current_state["error"],
                        "phase": current_state.get("current_phase", "unknown")
                    })
                    break
        
        except Exception as e:
            logger.error(f"Verification streaming error: {e}")
            yield ("error", {
                "error": str(e),
                "phase": "error"
            })
    
    async def ainvoke(
        self,
        input_state: InputState,
        config: Optional[RunnableConfig] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run complete verification process (non-streaming)
        
        Args:
            input_state: Input state with document IDs and configuration
            config: Runnable configuration
            **kwargs: Additional parameters
            
        Returns:
            Complete verification results
        """
        results = {
            "success": False,
            "claims": [],
            "summary": {},
            "message": "",
            "error": None
        }
        
        try:
            # Collect all streaming events
            final_result = None
            async for event_type, event_data in self.astream(input_state, config, **kwargs):
                if event_type == "final_result":
                    final_result = event_data
                    break
                elif event_type == "error":
                    results["error"] = event_data["error"]
                    results["message"] = f"Verification failed: {event_data['error']}"
                    return results
            
            if final_result:
                results.update(final_result)
            else:
                results["message"] = "Verification completed but no final result received"
            
        except Exception as e:
            logger.error(f"Verification invoke error: {e}")
            results["error"] = str(e)
            results["message"] = f"Verification failed: {str(e)}"
        
        return results
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the agent"""
        return {
            "agent": True,
            "model": self.model_id,
            "timestamp": datetime.now().isoformat()
        }