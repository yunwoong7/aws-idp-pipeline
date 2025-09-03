"""
Tool Executor Node - Executes the action decided by the reactor
"""

import os
import sys
import logging
import time
from typing import Dict, Any
from datetime import datetime

sys.path.append('/opt/python')
from common import OpenSearchService

from agent.state.agent_state import AgentState
from agent.tools import get_tool_by_name

logger = logging.getLogger(__name__)

class ExecutorNode:
    """
    Executes tools based on reactor decisions
    """
    
    def __init__(self):
        """Initialize Tool Executor"""
        # OpenSearch service
        self.opensearch = self._init_opensearch()
        
        logger.info("✅ ToolExecutorNode initialized")
    
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
    
    def __call__(self, state: AgentState) -> AgentState:
        """Execute the next action"""
        
        next_action = state.get('next_action')
        if not next_action:
            logger.info("No action to execute")
            return state
        
        action = next_action
        
        logger.info("=" * 60)
        logger.info(f"⚙️ TOOL EXECUTOR - Iteration {state.get('iteration_count', 0)}")
        logger.info(f"🔧 Executing: {action.get('tool_name')}")
        logger.info("=" * 60)
        
        try:
            start_time = time.time()
            
            # Get tool
            tool = get_tool_by_name(action.get('tool_name'))
            if not tool:
                raise Exception(f"Tool {action.get('tool_name')} not found")
            
            # Build context for tool
            context_kwargs = self._build_tool_context(state, action)
            
            # Merge action args with context
            final_kwargs = {**action.get('tool_args', {}), **context_kwargs}
            
            # Execute tool
            result = tool.execute(**final_kwargs)
            
            execution_time = time.time() - start_time
            
            # Create observation
            observation = {
                "iteration": state.get('iteration_count', 0),
                "tool_name": action.get('tool_name'),
                "result": self._format_result(result),
                "success": result.get("success", False),
                "execution_time": execution_time
            }
            
            # Add observation to state
            observations = state.get('observations', [])
            observations.append(observation)
            state['observations'] = observations
            
            # Add action to state (for record keeping)
            actions = state.get('actions', [])
            actions.append(action)
            state['actions'] = actions
            
            # Add references if any
            if result.get("references"):
                references = state.get('references', [])
                references.extend(result["references"])
                state['references'] = references
            
            # Save to OpenSearch if successful (skip only for ImageRotate)
            if self.opensearch and result.get("success"):
                tool_name = (action.get('tool_name') or '')
                if tool_name.lower() != 'imagerotate':
                    self._save_to_opensearch(state, action, result)
            
            logger.info(f"✅ Tool execution {'succeeded' if result.get('success') else 'failed'}")
            logger.info(f"⏱️ Execution time: {execution_time:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Tool execution failed: {str(e)}")
            
            # Add failed observation
            observation = {
                "iteration": state.get('iteration_count', 0),
                "tool_name": action.get('tool_name'),
                "result": f"Error: {str(e)}",
                "success": False,
                "execution_time": time.time() - start_time
            }
            
            observations = state.get('observations', [])
            observations.append(observation)
            state['observations'] = observations
            
            actions = state.get('actions', [])
            actions.append(action)
            state['actions'] = actions
        
        # Clear next_action as it's been executed
        state['next_action'] = None
        
        return state
    
    def _build_tool_context(self, state: AgentState, action: Dict[str, Any]) -> Dict[str, Any]:
        """Build context for tool execution"""
        
        # Build comprehensive context from observations
        observation_context = self._build_observation_context(state)
        
        context_kwargs = {
            'index_id': state.get('index_id'),
            'document_id': state.get('document_id'),
            'segment_id': state.get('segment_id'),
            'segment_index': state.get('segment_index'),
            'image_path': state.get('image_uri'),
            'file_path': state.get('file_path'),
            'user_query': state.get('user_query'),
            'media_type': state.get('media_type'),
            'previous_analysis_context': observation_context,
            # Add the specific query for this action
            'planned_query': action.get('rationale', state.get('user_query'))
        }
        
        # Add video-specific fields if applicable
        if state.get('segment_type'):
            context_kwargs['segment_type'] = state.get('segment_type')
        if state.get('start_timecode_smpte'):
            context_kwargs['start_timecode_smpte'] = state.get('start_timecode_smpte')
        if state.get('end_timecode_smpte'):
            context_kwargs['end_timecode_smpte'] = state.get('end_timecode_smpte')
        
        return context_kwargs
    
    def _build_observation_context(self, state: AgentState) -> str:
        """Build context from previous observations"""
        context_parts = []
        
        # Add original previous context
        previous_context = state.get('previous_analysis_context', '')
        if previous_context:
            context_parts.append("=== Previous Analysis Context ===")
            context_parts.append(previous_context)
            context_parts.append("")
        
        # Add observations from this session
        observations = state.get('observations', [])
        if observations:
            context_parts.append("=== Current Session Observations ===")
            for i, obs in enumerate(observations, 1):
                context_parts.append(f"Tool {i}: {obs.get('tool_name')}")
                context_parts.append(f"Success: {obs.get('success')}")
                if obs.get('success'):
                    result_text = obs.get('result', '')
                    # Limit length to avoid too long context
                    if len(result_text) > 2000:
                        result_text = result_text[:2000] + "..."
                    context_parts.append(f"Result: {result_text}")
                context_parts.append("")
        
        return "\n".join(context_parts)
    
    def _format_result(self, result: Dict[str, Any]) -> str:
        """Format tool result for observation"""
        if result.get("llm_text"):
            return result["llm_text"]
        elif result.get("results") and isinstance(result["results"], list):
            # Extract key information from results
            formatted_parts = []
            for item in result["results"][:3]:  # Limit to first 3 items
                if isinstance(item, dict):
                    if 'ai_response' in item:
                        formatted_parts.append(item['ai_response'])
                    elif 'content' in item:
                        formatted_parts.append(item['content'])
            return "\n".join(formatted_parts) if formatted_parts else str(result["results"])
        else:
            return str(result.get("data", result.get("message", "No result")))
    
    def _save_to_opensearch(self, state: AgentState, action: Dict[str, Any], result: Dict[str, Any]):
        """Save tool execution result to OpenSearch"""
        try:
            logger.info(f"💾 Saving {action.get('tool_name')} result to OpenSearch...")
            
            # Extract content
            content = result.get("llm_text", "") or result.get("message", "")
            
            # Use action rationale as the query
            query = action.get('rationale', state.get('user_query'))
            
            # Save to OpenSearch
            success = self.opensearch.add_ai_analysis_tool(
                index_id=state.get('index_id'),
                document_id=state.get('document_id'),
                segment_id=state.get('segment_id'),
                segment_index=state.get('segment_index'),
                analysis_query=query,
                content=content,
                analysis_steps=f"Vision ReAct - {action.get('tool_name')}",
                analysis_type="vision_react",
                media_type=state.get('media_type')
            )
            
            if success:
                logger.info(f"✅ {action.get('tool_name')} result saved to OpenSearch")
            else:
                logger.warning(f"⚠️ Failed to save {action.get('tool_name')} result")
                
        except Exception as e:
            logger.error(f"❌ OpenSearch save error: {str(e)}")