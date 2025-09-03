# src/agent/react_agent/tool_node.py
import logging
from typing import Dict, List, Any, Union
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from src.agent.react_agent.state.model import State

logger = logging.getLogger(__name__)

class CustomToolNode:
    """Custom tool node that executes tools and extracts results for state storage"""
    
    def __init__(self, tools):
        self.tool_node = ToolNode(tools)
    
    async def __call__(self, state: State, config: RunnableConfig) -> Dict[str, Any]:
        """Execute tools and extract results for state storage"""
        
        # Execute tools using standard ToolNode
        result = await self.tool_node.ainvoke(state, config)
        
        # Extract tool results from the messages
        tool_messages = result.get("messages", [])
        tool_references, tool_content, tool_attachments = self._extract_references_and_content(tool_messages)
        
        # Update state with extracted results
        updated_state = {
            **result,
            "tool_references": tool_references,
            "tool_content": tool_content,
            "tool_attachments": tool_attachments
        }
        
        logger.info(f"Tool execution complete - references: {len(tool_references)}, content length: {len(tool_content) if tool_content else 0}")
        
        return updated_state
    
    def _extract_references_and_content(self, tool_messages: List[ToolMessage]) -> tuple:
        """Extract references and content from tool execution results"""
        extracted_references = []
        extracted_content_parts = []
        extracted_attachments = []
        
        logger.info(f"Extracting references and content from {len(tool_messages)} tool messages")
        
        for message in tool_messages:
            if isinstance(message, ToolMessage):
                try:
                    content = message.content
                    
                    # Try to parse as structured data if it's a string representation of dict/list
                    if isinstance(content, str):
                        # Check if content looks like JSON
                        if content.strip().startswith('{') or content.strip().startswith('['):
                            try:
                                import json
                                parsed_content = json.loads(content)
                                content = parsed_content
                            except:
                                # If JSON parsing fails, treat as plain text
                                pass
                    
                    # If content is a dictionary, look for references, attachments and content fields
                    if isinstance(content, dict):
                        # Check if it has nested data structure (like hybrid_search result)
                        data = content.get("data", content)
                        # Harden against tools returning {"data": null}
                        if data is None:
                            data = {}
                        # Ensure dict before using membership checks
                        if not isinstance(data, dict):
                            data = {}
                        # Extract attachments if provided by tool (LLM-ready)
                        if "attachments" in data and isinstance(data["attachments"], list):
                            for att in data["attachments"]:
                                # Expecting process_attachments format item for image: {"type":"image","source":{"type":"base64","media_type":...,"data":...}}
                                if isinstance(att, dict) and att.get("type") == "image" and isinstance(att.get("source"), dict):
                                    extracted_attachments.append(att)
                        elif "attachments" in content and isinstance(content["attachments"], list):
                            for att in content["attachments"]:
                                if isinstance(att, dict) and att.get("type") == "image" and isinstance(att.get("source"), dict):
                                    extracted_attachments.append(att)
                        
                        # Extract references
                        if "references" in data:
                            references = data["references"]
                            if isinstance(references, list):
                                for ref in references:
                                    if isinstance(ref, str):
                                        # Determine type based on file extension or URL path
                                        ref_type = "document"
                                        # Check for image extensions in URL path (handles presigned URLs with query params)
                                        url_path = ref.split('?')[0]  # Remove query parameters
                                        if (url_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg')) or
                                            '.png' in url_path.lower() or '.jpg' in url_path.lower() or '.jpeg' in url_path.lower() or
                                            '.gif' in url_path.lower() or '.bmp' in url_path.lower() or '.webp' in url_path.lower() or '.svg' in url_path.lower()):
                                            ref_type = "image"
                                        
                                        # Parse reference format: "title : url" or just "url"
                                        if " : " in ref:
                                            title_part, url_part = ref.split(" : ", 1)
                                            actual_url = url_part.strip()
                                            actual_title = title_part.strip()
                                        else:
                                            actual_url = ref.strip()
                                            actual_title = ref.strip()
                                        
                                        # Re-check type with actual URL
                                        url_path = actual_url.split('?')[0]  # Remove query parameters
                                        if (url_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg')) or
                                            '.png' in url_path.lower() or '.jpg' in url_path.lower() or '.jpeg' in url_path.lower() or
                                            '.gif' in url_path.lower() or '.bmp' in url_path.lower() or '.webp' in url_path.lower() or '.svg' in url_path.lower()):
                                            ref_type = "image"
                                        
                                        ref_dict = {
                                            "type": ref_type,
                                            "title": actual_title,
                                            "value": actual_url,
                                            "metadata": {"tool": message.tool_call_id, "source": "tool_execution"}
                                        }
                                        extracted_references.append(ref_dict)
                                    elif isinstance(ref, dict):
                                        ref["metadata"] = ref.get("metadata", {})
                                        ref["metadata"]["tool"] = message.tool_call_id
                                        ref["metadata"]["source"] = "tool_execution"
                                        extracted_references.append(ref)
                        elif "references" in content:
                            references = content["references"]
                            if isinstance(references, list):
                                for ref in references:
                                    if isinstance(ref, str):
                                        # Determine type based on file extension or URL path
                                        ref_type = "document"
                                        # Check for image extensions in URL path (handles presigned URLs with query params)
                                        url_path = ref.split('?')[0]  # Remove query parameters
                                        if (url_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg')) or
                                            '.png' in url_path.lower() or '.jpg' in url_path.lower() or '.jpeg' in url_path.lower() or
                                            '.gif' in url_path.lower() or '.bmp' in url_path.lower() or '.webp' in url_path.lower() or '.svg' in url_path.lower()):
                                            ref_type = "image"
                                        
                                        # Parse reference format: "title : url" or just "url"
                                        if " : " in ref:
                                            title_part, url_part = ref.split(" : ", 1)
                                            actual_url = url_part.strip()
                                            actual_title = title_part.strip()
                                        else:
                                            actual_url = ref.strip()
                                            actual_title = ref.strip()
                                        
                                        # Re-check type with actual URL
                                        url_path = actual_url.split('?')[0]  # Remove query parameters
                                        if (url_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg')) or
                                            '.png' in url_path.lower() or '.jpg' in url_path.lower() or '.jpeg' in url_path.lower() or
                                            '.gif' in url_path.lower() or '.bmp' in url_path.lower() or '.webp' in url_path.lower() or '.svg' in url_path.lower()):
                                            ref_type = "image"
                                        
                                        ref_dict = {
                                            "type": ref_type,
                                            "title": actual_title,
                                            "value": actual_url,
                                            "metadata": {"tool": message.tool_call_id, "source": "tool_execution"}
                                        }
                                        extracted_references.append(ref_dict)
                                    elif isinstance(ref, dict):
                                        ref["metadata"] = ref.get("metadata", {})
                                        ref["metadata"]["tool"] = message.tool_call_id
                                        ref["metadata"]["source"] = "tool_execution"
                                        extracted_references.append(ref)
                        
                        # Extract textual content only (avoid dumping entire dict with base64)
                        if "content" in data:
                            content_data = data["content"]
                            if isinstance(content_data, list):
                                for item in content_data:
                                    if isinstance(item, str) and item.strip():
                                        extracted_content_parts.append(item)
                            elif isinstance(content_data, str) and content_data.strip():
                                extracted_content_parts.append(content_data)
                        elif "content" in content:
                            content_data = content["content"]
                            if isinstance(content_data, list):
                                for item in content_data:
                                    if isinstance(item, str) and item.strip():
                                        extracted_content_parts.append(item)
                            elif isinstance(content_data, str) and content_data.strip():
                                extracted_content_parts.append(content_data)
                    
                    # If content is plain text, add it to content parts
                    elif isinstance(content, str) and content.strip():
                        extracted_content_parts.append(content)
                
                except Exception as e:
                    logger.error(f"Error processing tool message: {str(e)}")
        
        # Combine content parts
        combined_content = "\n\n".join(extracted_content_parts) if extracted_content_parts else ""
        # Enforce length limit to prevent token overflow
        MAX_CONTENT_LEN = 32000
        if len(combined_content) > MAX_CONTENT_LEN:
            combined_content = combined_content[:MAX_CONTENT_LEN]
            logger.info(f"Tool content truncated to {MAX_CONTENT_LEN} characters to avoid overflow")
        
        logger.info(f"Extraction complete - references: {len(extracted_references)}, content: {len(combined_content)} chars")
        
        return extracted_references, combined_content, extracted_attachments