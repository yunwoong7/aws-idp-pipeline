"""
Responder Node - Generates final response and saves to OpenSearch
"""

import os
import sys
import logging
from typing import Dict, Any
from datetime import datetime, timezone

sys.path.append('/opt/python')
from common import OpenSearchService, DynamoDBService

from agent.state.agent_state import AgentState
from agent.llm import get_llm
from prompts import prompt_manager

logger = logging.getLogger(__name__)

class ResponderNode:
    """
    Generates final response based on execution results
    """
    
    def __init__(self, model_id: str = None, max_tokens: int = 8192):
        """Initialize Responder"""
        self.llm = get_llm(model_id=model_id, max_tokens=max_tokens)
        self.opensearch = self._init_opensearch()
        self.dynamodb = self._init_dynamodb()
        
        logger.info("✅ ResponderNode initialized")
    
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
    
    def __call__(self, state: AgentState) -> AgentState:
        """Generate final response"""
        logger.info("=" * 80)
        logger.info("📝 RESPONDER NODE STARTED")
        logger.info("=" * 80)
        
        # Generate comprehensive response
        final_response = self._generate_response(state)
        state['final_response'] = final_response
        
        # Save to OpenSearch
        if self.opensearch:
            self._save_final_response_to_opensearch(state, final_response)
        
        # Save to DynamoDB Segments table
        if self.dynamodb:
            self._save_summary_to_segments(state, final_response)
        
        logger.info("✅ Response generation completed")
        return state
    
    def _generate_response(self, state: AgentState) -> str:
        """Generate final comprehensive response"""
        logger.info("\n📊 GENERATING FINAL RESPONSE")
        logger.info("-" * 40)
        
        # Build context from all results
        context = self._build_context(state)
        
        # Get current date
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get response prompts from YAML
        prompts = prompt_manager.get_prompt(
            'responder',
            'final_response',
            user_query=state.get('user_query'),
            react_results=context,
            previous_context=state.get('previous_analysis_context', 'None'),
            current_date=current_date
        )
        
        system_prompt = prompts['system_prompt']
        user_prompt = prompts['user_prompt']
        
        try:
            # Generate response
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self.llm.invoke(messages)
            final_response = response.content
            
            logger.info(f"✅ Response generated: {len(final_response)} chars")
            
            return final_response
            
        except Exception as e:
            logger.error(f"❌ Response generation failed: {str(e)}")
            return f"Failed to generate response: {str(e)}"
    
    def _build_context(self, state: AgentState) -> str:
        """Build context from ReAct iterations"""
        context_parts = []
        
        # Add previous analysis context
        previous_context = state.get('previous_analysis_context', '')
        if previous_context:
            context_parts.append("=== Previous Analysis Context ===")
            context_parts.append(previous_context)
            context_parts.append("")
        
        # Add ReAct iterations
        context_parts.append("=== ReAct Iterations ===")
        thoughts = state.get('thoughts', [])
        actions = state.get('actions', [])
        observations = state.get('observations', [])
        
        for i in range(len(thoughts)):
            context_parts.append(f"\n--- Iteration {i + 1} ---")
            
            # Add thought
            if i < len(thoughts):
                thought = thoughts[i]
                context_parts.append(f"Thought: {thought.get('content', '')}")
            
            # Add action
            if i < len(actions):
                action = actions[i]
                context_parts.append(f"Action: {action.get('tool_name', '')} - {action.get('rationale', '')}")
            
            # Add observation
            if i < len(observations):
                obs = observations[i]
                context_parts.append(f"Observation: {obs.get('result', '')}")
                context_parts.append(f"Success: {obs.get('success', False)}")
            
            context_parts.append("")
        
        # Summary
        context_parts.append(f"Total iterations: {state.get('iteration_count', 0)}")
        successful_actions = sum(1 for obs in observations if obs.get('success'))
        context_parts.append(f"Successful tool executions: {successful_actions}")
        
        return "\n".join(context_parts)
    
    def _save_final_response_to_opensearch(self, state: AgentState, response: str):
        """Save final response to OpenSearch"""
        try:
            logger.info("💾 Saving final response to OpenSearch...")
            
            success = self.opensearch.add_ai_analysis_tool(
                index_id=state.get('index_id'),
                document_id=state.get('document_id'),
                segment_id=state.get('segment_id'),
                segment_index=state.get('segment_index'),
                analysis_query=state.get('user_query'),
                content=response,
                analysis_steps="final_ai_response",
                analysis_type="final_response",
                media_type=state.get('media_type')
            )
            
            if success:
                logger.info("✅ Final response saved to OpenSearch")
                
                # Try to update embeddings
                try:
                    self.opensearch.update_segment_embeddings(state.get('index_id'), state.get('segment_id'))
                    logger.info("✅ Embeddings updated")
                except Exception as e:
                    logger.warning(f"⚠️ Embedding update failed: {e}")
            else:
                logger.warning("⚠️ Failed to save final response to OpenSearch")
                
        except Exception as e:
            logger.error(f"❌ OpenSearch save error: {str(e)}")
    
    def _save_summary_to_segments(self, state: AgentState, response: str):
        """Save summary to DynamoDB Segments table"""
        try:
            segment_id = state.get('segment_id')
            if not segment_id:
                logger.warning("No segment_id, skipping DynamoDB update")
                return
                
            logger.info("💾 Saving summary to Segments table...")
            
            # Limit summary length
            summary = response[:30000] + "..." if len(response) > 30000 else response
            
            updates = {
                'summary': summary,
                'analysis_completed_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            success = self.dynamodb.update_item(
                table_name='segments',
                key={'segment_id': segment_id},
                updates=updates
            )
            
            if success:
                logger.info("✅ Summary saved to Segments table")
            else:
                logger.warning("⚠️ Failed to save summary to Segments table")
                
        except Exception as e:
            logger.error(f"❌ DynamoDB save error: {str(e)}")