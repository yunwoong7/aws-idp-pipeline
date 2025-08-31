"""
Vision ReAct Agent - ReAct pattern with direct image viewing capability
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

sys.path.append('/opt/python')
from common import OpenSearchService, DynamoDBService
from prompts import prompt_manager

from agent.state.agent_state import AgentState
from agent.nodes.reactor import ReactorNode
from agent.nodes.executor import ExecutorNode
from agent.nodes.responder import ResponderNode
from agent.llm import get_llm

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

class ReactAgent:
    """
    Vision-based ReAct Agent that can see images and iteratively think and act
    """
    
    def __init__(self):
        """Initialize Vision ReAct Agent"""
        # Initialize services
        self.opensearch = self._init_opensearch()
        self.dynamodb = self._init_dynamodb()
        
        # Initialize nodes
        self.reactor = ReactorNode()
        self.executor = ExecutorNode()
        self.responder = ResponderNode()
        
        # Build workflow
        self.workflow = self._build_workflow()
        self.app = self.workflow.compile()
        
        logger.info("✅ VisionReactAgent initialized")
    
    def _init_opensearch(self):
        """Initialize OpenSearch service"""
        endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
        if not endpoint:
            logger.warning("⚠️ OpenSearch endpoint not set")
            return None
            
        try:
            service = OpenSearchService(
                endpoint=endpoint,
                index_name=os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis'),
                region=os.environ.get('AWS_REGION', 'us-west-2')
            )
            logger.info("✅ OpenSearch service initialized")
            return service
        except Exception as e:
            logger.error(f"❌ OpenSearch init failed: {e}")
            return None
    
    def _init_dynamodb(self):
        """Initialize DynamoDB service"""
        try:
            service = DynamoDBService(region=os.environ.get('AWS_REGION', 'us-west-2'))
            logger.info("✅ DynamoDB service initialized")
            return service
        except Exception as e:
            logger.warning(f"❌ DynamoDB init failed: {e}")
            return None
    
    def _build_workflow(self) -> StateGraph:
        """Build the Vision ReAct workflow"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("reactor", self.reactor)
        workflow.add_node("executor", self.executor) 
        workflow.add_node("responder", self.responder)
        
        # Define flow
        workflow.set_entry_point("reactor")
        
        # Conditional edges from reactor
        workflow.add_conditional_edges(
            "reactor",
            self._should_continue,
            {
                "continue": "executor",
                "end": "responder"
            }
        )
        
        # After executor, go back to reactor for next iteration
        workflow.add_edge("executor", "reactor")
        
        # Responder ends the flow
        workflow.add_edge("responder", END)
        
        return workflow
    
    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to continue with tool execution or respond"""
        # Check if we should continue based on state
        if not state.get('should_continue', True):
            return "end"
            
        # Check if we have a next action to execute
        if state.get('next_action') and state.get('next_action', {}).get("tool_name"):
            # Check iteration limit
            if state.get('iteration_count', 0) >= state.get('max_iterations', 5):
                logger.info(f"🛑 Reached max iterations ({state.get('max_iterations', 5)})")
                return "end"
            return "continue"
        
        # No more actions, generate final response
        return "end"
    
    def invoke(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the Vision ReAct workflow"""
        try:
            # Build user_query from YAML if not provided
            user_query = input_data.get('user_query')
            if not user_query:
                try:
                    document_id = input_data.get('document_id')
                    segment_index = input_data.get('segment_index', 0)
                    user_query = prompt_manager.get_text(
                        'reactor',
                        'user_query',
                        document_id=document_id,
                        segment_index_plus_one=(segment_index + 1)
                    )
                except Exception as _e:
                    # Fallback to default inline template
                    document_id = input_data.get('document_id')
                    segment_index = input_data.get('segment_index', 0)
                    user_query = (f"'{document_id}' 세그먼트 {segment_index + 1}를 "
                                  f"다양한 각도와 시각에서 분석하여 "
                                  f"세그먼트에 있는 내용을 자세히 설명해주세요.")

            logger.info("=" * 80)
            logger.info("🚀 VISION REACT AGENT STARTED")
            logger.info(f"📄 Index: {input_data.get('index_id')}")
            logger.info(f"📄 Document: {input_data.get('document_id')}")
            logger.info(f"💬 Query: {user_query}")
            logger.info("=" * 80)
            
            # Get max iterations from environment variable
            max_iterations = int(os.environ.get('MAX_ITERATIONS', '5'))
            
            # Initialize state as dict (TypedDict)
            initial_state: AgentState = {
                'index_id': input_data.get('index_id'),
                'document_id': input_data.get('document_id'),
                'segment_id': input_data.get('segment_id'),
                'segment_index': input_data.get('segment_index', 0),
                'image_uri': input_data.get('image_uri'),
                'file_path': input_data.get('file_path'),
                'user_query': user_query,
                'media_type': input_data.get('media_type', 'IMAGE'),
                'previous_analysis_context': input_data.get('previous_analysis_context', ''),
                # ReAct specific fields
                'iteration_count': 0,
                'max_iterations': max_iterations,
                'thoughts': [],
                'actions': [],
                'observations': [],
                'next_action': None,
                'should_continue': True,
                # Results
                'final_response': None,
                'references': [],
                # Media type info
                'segment_type': input_data.get('segment_type'),
                'start_timecode_smpte': input_data.get('start_timecode_smpte'),
                'end_timecode_smpte': input_data.get('end_timecode_smpte'),
                'thread_id': input_data.get('thread_id')
            }
            
            # Execute workflow
            result = self.app.invoke(initial_state)
            
            logger.info("=" * 80)
            logger.info(f"✅ VISION REACT AGENT COMPLETED")
            logger.info(f"🔄 Total iterations: {result['iteration_count']}")
            logger.info("=" * 80)
            
            return {
                "success": True,
                "response": result['final_response'],
                "iterations": result['iteration_count'],
                "thoughts": result['thoughts'],
                "actions": result['actions']
            }
            
        except Exception as e:
            logger.error(f"❌ Agent execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }