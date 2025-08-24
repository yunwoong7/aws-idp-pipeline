"""Search Agent Synthesizer

Synthesizes execution results into comprehensive answers with citations.
"""

import yaml
import json
import re
import logging
import asyncio
from typing import Dict, Any, List, AsyncGenerator, Optional
from pathlib import Path
from datetime import datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from .state import (
    ExecutionResult, 
    SearchState,
    SynthesizingStartEvent,
    TextChunkEvent,
    CitationEvent,
    StreamEndEvent
)
from src.agent.react_agent.config import ConfigManager

logger = logging.getLogger(__name__)


class SearchSynthesizer:
    """Synthesizes search results into comprehensive answers."""
    
    def __init__(self, model: BaseChatModel, config: ConfigManager):
        self.model = model
        self.config = config
        self.prompt_path = Path(__file__).parent / "prompt" / "synthesizer_prompt.yaml"
        self._load_prompt_template()
        
        # Citation parsing regex
        self.citation_pattern = re.compile(r'\[cite:\s*(\d+(?:,\s*\d+)*)\]')
    
    def _load_prompt_template(self):
        """Load the synthesizer prompt template."""
        try:
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                self.prompt_config = yaml.safe_load(f)
            logger.info("Synthesizer prompt template loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load synthesizer prompt template: {e}")
            # Fallback minimal template
            self.prompt_config = {
                "system_prompt": "Synthesize the results with proper citations using [cite: X] format.",
                "user_prompt_template": "Query: {query}\nResults: {execution_results}"
            }
    
    async def synthesize_answer_stream(
        self,
        search_state: SearchState
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Synthesize execution results into a comprehensive answer with streaming.
        
        Args:
            search_state: Current search state with execution results
            
        Yields:
            Dictionary events for streaming synthesis
        """
        logger.info("Starting answer synthesis")
        
        # Emit synthesis start event
        yield {
            "type": "synthesizing_start",
            "message": "Starting to synthesize final answer...",
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Prepare the prompt
            system_prompt, user_prompt = self._prepare_synthesis_prompt(search_state)
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            logger.debug("Sending synthesis request to model")
            
            # Stream the response
            current_text_id = str(uuid4())
            full_text = ""
            accumulated_delta = ""
            word_buffer = []
            
            async for chunk in self.model.astream(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    incoming_text = chunk.content
                    delta_text = ""
                    
                    # Handle providers that send cumulative text vs token deltas
                    if len(incoming_text) >= len(full_text) and incoming_text.startswith(full_text):
                        # Cumulative case: emit only the new suffix
                        delta_text = incoming_text[len(full_text):]
                        full_text = incoming_text
                    else:
                        # Delta case: append and emit as-is
                        delta_text = incoming_text
                        full_text += incoming_text
                    
                    if not delta_text:
                        continue
                    
                    # Buffer text until we have meaningful chunks (words or punctuation)
                    accumulated_delta += delta_text
                    
                    # Check if we have complete words or sentence endings
                    should_emit = (
                        len(accumulated_delta) >= 50 or  # Emit every 50+ characters for better chunks
                        any(end in accumulated_delta for end in ['.', '!', '?', '\n\n', '##']) or  # Sentence/section endings
                        accumulated_delta.count(' ') >= 8 or  # Multiple words (8+ spaces)
                        len(accumulated_delta) >= 100  # Force emit for long text
                    )
                    
                    if should_emit:
                        # Process citations using accumulated text
                        processed_text, citations = self._process_citations_in_chunk(
                            accumulated_delta, full_text, current_text_id
                        )
                        
                        if processed_text:
                            # Emit text chunk event (accumulated delta)
                            yield {
                                "type": "text_chunk",
                                "text_id": current_text_id,
                                "text": processed_text,
                                "timestamp": datetime.now().isoformat()
                            }
                        
                        # Emit citation events
                        for citation in citations:
                            yield {
                                "type": "citation_data",
                                "target_text_id": citation["target_text_id"],
                                "source_ids": citation["source_ids"],
                                "timestamp": datetime.now().isoformat()
                            }
                        
                        # Reset accumulated delta
                        accumulated_delta = ""
                    
                    # Small delay for better streaming experience
                    await asyncio.sleep(0.01)
            
            # Emit any remaining accumulated text
            if accumulated_delta:
                processed_text, citations = self._process_citations_in_chunk(
                    accumulated_delta, full_text, current_text_id
                )
                
                if processed_text:
                    yield {
                        "type": "text_chunk",
                        "text_id": current_text_id,
                        "text": processed_text,
                        "timestamp": datetime.now().isoformat()
                    }
                
                for citation in citations:
                    yield {
                        "type": "citation_data",
                        "target_text_id": citation["target_text_id"],
                        "source_ids": citation["source_ids"],
                        "timestamp": datetime.now().isoformat()
                    }
            
            # Final processing for any remaining citations
            final_citations = self._extract_final_citations(full_text, current_text_id)
            for citation in final_citations:
                yield {
                    "type": "citation_data",
                    "target_text_id": citation["target_text_id"],
                    "source_ids": citation["source_ids"],
                    "timestamp": datetime.now().isoformat()
                }
            
            # Update search state
            search_state.mark_completed()
            
            # Emit stream end event
            yield {
                "type": "stream_end",
                "message": "Search completed successfully",
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info("Answer synthesis completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to synthesize answer: {e}")
            
            # Update search state with error
            search_state.mark_error(str(e))
            
            # Emit error event
            yield {
                "type": "error",
                "error_message": f"Failed to synthesize answer: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _prepare_synthesis_prompt(self, search_state: SearchState) -> tuple[str, str]:
        """Prepare the synthesis prompt with execution results."""
        
        # Format execution results for the prompt
        execution_results_text = self._format_execution_results(search_state.execution_results)
        
        # Create system prompt
        system_prompt = self.prompt_config["system_prompt"].format(
            index_id=search_state.index_id or "Not specified",
            document_id=search_state.document_id or "Not specified",
            segment_id=search_state.segment_id or "Not specified",
            datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Create user prompt
        user_prompt = self.prompt_config["user_prompt_template"].format(
            query=search_state.query,
            execution_results=execution_results_text
        )
        
        return system_prompt, user_prompt
    
    def _format_execution_results(self, execution_results: List[ExecutionResult]) -> str:
        """Format execution results for the prompt."""
        if not execution_results:
            return "No execution results available."
        
        formatted_results = []
        
        for result in execution_results:
            # Only include successful results
            if not result.success:
                continue
            
            result_text = self.prompt_config.get("execution_results_template", """
### Source ID {source_id} - {tool_name}
**Result Summary**: {result_summary}
**Result Data**:
{result_data}

---
            """).format(
                source_id=result.source_id,
                tool_name=result.tool_name,
                result_summary=result.result_summary,
                result_data=self._format_result_data(result.result_data)
            )
            
            formatted_results.append(result_text)
        
        return "\n".join(formatted_results) if formatted_results else "No successful results to synthesize."
    
    def _format_result_data(self, result_data: Dict[str, Any]) -> str:
        """Format result data for display in prompt."""
        try:
            if not result_data:
                return "No data"
            
            # Handle different result data structures
            if isinstance(result_data, dict):
                if "results" in result_data and isinstance(result_data["results"], list):
                    # Search results - show top items
                    results = result_data["results"][:5]  # Limit to top 5
                    formatted = []
                    for i, item in enumerate(results, 1):
                        if isinstance(item, dict):
                            title = item.get("title", item.get("file_name", f"Result {i}"))
                            content = item.get("content", item.get("summary", ""))
                            formatted.append(f"{i}. {title}: {content[:200]}...")
                        else:
                            formatted.append(f"{i}. {str(item)[:200]}...")
                    return "\n".join(formatted)
                
                elif "content" in result_data:
                    # Content data
                    content = str(result_data["content"])
                    return content[:1000] + ("..." if len(content) > 1000 else "")
                
                else:
                    # Generic dict - format as JSON (truncated)
                    json_str = json.dumps(result_data, indent=2, ensure_ascii=False)
                    return json_str[:1000] + ("..." if len(json_str) > 1000 else "")
            
            elif isinstance(result_data, list):
                # List data
                return json.dumps(result_data[:5], indent=2, ensure_ascii=False)[:1000]
            
            else:
                # Other types
                return str(result_data)[:1000]
                
        except Exception as e:
            logger.warning(f"Failed to format result data: {e}")
            return "Error formatting result data"
    
    def _process_citations_in_chunk(
        self, 
        chunk_text: str, 
        accumulated_text: str, 
        text_id: str
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Process citations in a text chunk."""
        citations = []
        processed_text = chunk_text
        
        # Find citations in the current chunk
        matches = list(self.citation_pattern.finditer(chunk_text))
        
        for match in matches:
            citation_text = match.group(0)  # Full citation like [cite: 1,2]
            source_ids_str = match.group(1)  # Just the numbers like "1,2"
            
            # Parse source IDs
            try:
                source_ids = [int(id.strip()) for id in source_ids_str.split(",")]
                
                citations.append({
                    "target_text_id": text_id,
                    "source_ids": source_ids
                })
                
                # Remove citation from text for cleaner display
                processed_text = processed_text.replace(citation_text, "")
                
            except ValueError as e:
                logger.warning(f"Failed to parse citation {citation_text}: {e}")
        
        return processed_text, citations
    
    def _extract_final_citations(self, full_text: str, text_id: str) -> List[Dict[str, Any]]:
        """Extract any remaining citations from the full text."""
        citations = []
        
        matches = list(self.citation_pattern.finditer(full_text))
        
        for match in matches:
            source_ids_str = match.group(1)
            
            try:
                source_ids = [int(id.strip()) for id in source_ids_str.split(",")]
                
                citations.append({
                    "target_text_id": text_id,
                    "source_ids": source_ids
                })
                
            except ValueError as e:
                logger.warning(f"Failed to parse final citation: {e}")
        
        return citations