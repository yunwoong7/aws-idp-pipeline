"""
Responder Node - Generates final responses with streaming support
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, Any, AsyncIterator, List, Optional

from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from ..state.model import ChatState, Reference
from ..prompt import prompt_manager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class ResponderNode:
    """
    Responder node that generates final responses with streaming and reference filtering
    """
    
    def __init__(
        self, 
        model: ChatBedrock,
        show_thought_process: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the responder node
        
        Args:
            model: Language model for response generation
            show_thought_process: Whether to show reasoning process
            verbose: Enable verbose logging
        """
        self.model = model
        self.show_thought_process = show_thought_process
        self.verbose = verbose
        
        # Will load system prompt from YAML

    async def astream(self, state: ChatState) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream response generation with real-time updates
        
        Args:
            state: Current chat state with plan and execution results
            
        Yields:
            Response tokens and final result with filtered references
        """
        logger.info("Starting response generation...")
        start_time = time.time()
        
        yield {
            "type": "response_start",
            "message": "Generating comprehensive response...",
            "timestamp": time.time()
        }

        try:
            # Build context and references
            context, references_text, original_references = self._build_context(state)
            
            # Handle direct response with streaming
            if state.plan and state.plan.direct_response:
                logger.info("Streaming direct response")
                
                response_text = state.plan.direct_response
                
                # Stream direct response in chunks
                chunk_size = 50  # Smaller chunks for better streaming experience
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    yield {
                        "type": "response_token",
                        "token": chunk,
                        "timestamp": time.time()
                    }
                    await asyncio.sleep(0.01)  # Small delay for better UX
                
                # Direct responses typically don't have references
                filtered_references = []
                
            else:
                # Generate response using LLM with streaming
                logger.info("Streaming LLM response")
                
                # Build messages using YAML prompt
                messages = self._build_messages_from_yaml(state, context, references_text)
                
                # Stream response
                full_response = ""
                async for chunk in self.model.astream(messages):
                    if hasattr(chunk, 'content'):
                        if isinstance(chunk.content, list):
                            # Handle Claude 3 format
                            for content_item in chunk.content:
                                if content_item.get('type') == 'text':
                                    token = content_item.get('text', '')
                                    if token:
                                        full_response += token
                                        yield {
                                            "type": "response_token",
                                            "token": token,
                                            "timestamp": time.time()
                                        }
                        elif isinstance(chunk.content, str):
                            # Handle simple string content
                            full_response += chunk.content
                            yield {
                                "type": "response_token",
                                "token": chunk.content,
                                "timestamp": time.time()
                            }
                
                # Process response (remove thought process if needed)
                response_text = self._process_response(full_response)
                
                # Filter references based on actual usage
                filtered_references = self._filter_references_from_response(
                    response_text, original_references
                )
            
            # Calculate response time
            response_time = time.time() - start_time
            logger.info(f"Response generated in {response_time:.2f}s")
            
            # Update message history
            updated_history = state.message_history + [
                {"role": "user", "content": state.input},
                {"role": "assistant", "content": response_text}
            ]
            
            # Yield final response
            yield {
                "type": "response_complete",
                "response": response_text,
                "references": [ref.model_dump() if hasattr(ref, 'model_dump') else ref 
                             for ref in filtered_references],
                "message_history": updated_history,
                "response_time": response_time,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            yield {
                "type": "response_error",
                "error": str(e),
                "timestamp": time.time()
            }

    def _build_context(self, state: ChatState) -> tuple[str, str, List[Any]]:
        """
        Build context from execution results
        
        Args:
            state: Current chat state
            
        Returns:
            Tuple of (context_text, references_text, original_references)
        """
        if state.plan and state.plan.direct_response:
            return f"Direct response: {state.plan.direct_response}", "", []
        
        # Build context from executed tasks
        context_parts = []
        references = []
        original_references = []
        ref_index = 1
        
        if state.plan and state.plan.overview:
            context_parts.append(f"Plan overview: {state.plan.overview}\n")
        
        context_parts.append("Executed tasks and their results:\n")
        
        for task_info in state.executed_tasks:
            task = task_info.get('task')
            result = task_info.get('result', {})
            success = task_info.get('success', False)
            
            if not success:
                context_parts.append(f"Task failed: {result.get('error', 'Unknown error')}")
                continue
            
            # Add task result to context
            if isinstance(result, dict):
                # Add result text
                if 'text' in result and result['text']:
                    context_parts.append(result['text'])
                
                # Process references
                if 'references' in result and isinstance(result['references'], list):
                    original_references.extend(result['references'])
                    
                    for ref_data in result['references']:
                        ref_text = f"[{ref_index}] {ref_data.get('type', 'reference')}: {ref_data.get('value', '')}"
                        if ref_data.get('title'):
                            ref_text += f" - {ref_data.get('title')}"
                        references.append(ref_text)
                        ref_index += 1
                
                # Fallback for other formats
                if 'text' not in result or not result['text']:
                    context_parts.append(str(result.get('raw_result', result)))
            else:
                context_parts.append(str(result))
        
        context_text = "\n".join(context_parts)
        references_text = "\n".join(references) if references else ""
        
        return context_text, references_text, original_references

    def _build_messages_from_yaml(self, state: ChatState, context: str, references: str) -> List:
        """Build messages for LLM response generation using YAML prompt"""
        
        # Format conversation history
        conversation_text = ""
        for msg in state.message_history:
            conversation_text += f"{msg['role']}: {msg['content']}\n"
        
        # Format plan information
        plan_text = ""
        if state.plan:
            plan_data = {
                "requires_tool": state.plan.requires_tool,
                "overview": state.plan.overview,
                "tasks": [{
                    "title": task.title,
                    "description": task.description,
                    "tool_name": task.tool_name,
                    "status": task.status.value
                } for task in state.plan.tasks] if state.plan.tasks else []
            }
            plan_text = str(plan_data)
        
        # Format execution results
        results_text = context or "No execution results available"
        
        # Get formatted prompt from YAML
        prompt = prompt_manager.get_prompt(
            "responder",
            DATETIME=datetime.now(tz=timezone.utc).isoformat(),
            INDEX_ID=state.index_id or "",
            DOCUMENT_ID=state.document_id or "",
            SEGMENT_ID=state.segment_id or "",
            QUERY=state.input,
            PLAN=plan_text,
            RESULTS=results_text,
            CONVERSATION_HISTORY=conversation_text.strip()
        )
        
        # Create messages from prompt
        return [
            SystemMessage(content=prompt["system_prompt"]),
            HumanMessage(content=prompt["instruction"])
        ]

    def _process_response(self, response: str) -> str:
        """Process the response (remove thought process if needed)"""
        if not self.show_thought_process:
            # Remove thought process tags
            response = re.sub(r'<thought_process>.*?</thought_process>', '', response, flags=re.DOTALL)
            # Clean up excessive newlines
            response = re.sub(r'\n{3,}', '\n\n', response)
        
        return response.strip()

    def _filter_references_from_response(self, response: str, original_references: List[Any]) -> List[Reference]:
        """
        Filter references that are actually used in the response
        
        Args:
            response: Generated response text
            original_references: All available references
            
        Returns:
            List of references that appear in the response
        """
        if not original_references:
            logger.info("No references to filter")
            return []
        
        logger.info(f"Filtering {len(original_references)} references based on response content")
        
        # Find citation patterns in response
        citation_pattern = r'\[(\d+)\]'
        citations = re.findall(citation_pattern, response)
        
        if not citations:
            logger.info("No citations found in response")
            return []
        
        # Convert to indices (citations are 1-based)
        cited_indices = set()
        for citation in citations:
            try:
                index = int(citation) - 1  # Convert to 0-based index
                if 0 <= index < len(original_references):
                    cited_indices.add(index)
            except ValueError:
                continue
        
        # Create filtered references
        filtered_references = []
        for index in sorted(cited_indices):
            ref_data = original_references[index]
            
            if isinstance(ref_data, dict):
                # Convert to Reference object
                ref = Reference(
                    id=ref_data.get("id", str(index)),
                    type=ref_data.get("type", "unknown"),
                    value=ref_data.get("value", ""),
                    title=ref_data.get("title"),
                    description=ref_data.get("description")
                )
                filtered_references.append(ref)
            elif hasattr(ref_data, 'model_dump'):
                # Already a Reference object
                filtered_references.append(ref_data)
        
        logger.info(f"Filtered to {len(filtered_references)} referenced items")
        return filtered_references

    async def ainvoke(self, state: ChatState) -> Dict[str, Any]:
        """
        Generate response without streaming (for testing/fallback)
        
        Args:
            state: Current chat state
            
        Returns:
            Response with references and updated history
        """
        result = {}
        async for event in self.astream(state):
            if event["type"] == "response_complete":
                return {
                    "response": event["response"],
                    "references": event["references"],
                    "message_history": event["message_history"]
                }
        
        return {"response": "Failed to generate response", "references": [], "message_history": state.message_history}