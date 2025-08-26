"""
Executor Node - Executes tasks using MCP tools
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, AsyncIterator, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_aws import ChatBedrock
from langgraph.prebuilt import ToolNode

from ..state.model import SearchState, Task, TaskStatus, Reference
from src.mcp_client.mcp_service import MCPService

logger = logging.getLogger(__name__)

class ExecutorNode:
    """
    Executor node that runs tasks using MCP tools with streaming support
    """
    
    def __init__(self, mcp_service: MCPService, model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0", verbose: bool = False):
        """
        Initialize the executor node
        
        Args:
            mcp_service: MCP service for tool execution
            model_id: Bedrock model ID for tool execution
            verbose: Enable verbose logging
        """
        self.mcp_service = mcp_service
        self.verbose = verbose
        self.model_id = model_id
        
        # Create a model for formatting tool calls
        self.model = ChatBedrock(
            model_id=model_id,
            model_kwargs={
                "max_tokens": 4096,
                "temperature": 0.1,
                "top_p": 0.9,
            }
        )
        
        # Setup ToolNode with MCP tools
        self._setup_tool_node()

    def _setup_tool_node(self):
        """Setup ToolNode with MCP tools"""
        try:
            if not self.mcp_service:
                logger.warning("MCP service not available")
                self.tool_node = None
                self.tools_available = False
                return
                
            tools = self.mcp_service.get_tools()
            if tools and len(tools) > 0:
                self.tool_node = ToolNode(tools)
                self.tools_available = True
                logger.info(f"Executor initialized with {len(tools)} MCP tools")
                
                # Log tool names for debugging
                tool_names = [getattr(tool, 'name', 'unknown') for tool in tools]
                logger.debug(f"Available tools: {', '.join(tool_names)}")
            else:
                self.tool_node = None
                self.tools_available = False
                logger.warning("No MCP tools available for executor - tools list empty")
        except Exception as e:
            logger.error(f"Failed to setup ToolNode: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.tool_node = None
            self.tools_available = False

    async def refresh_tools(self):
        """Refresh tools from MCP service - useful for runtime updates"""
        if not self.mcp_service:
            logger.warning("Cannot refresh tools - MCP service not available")
            return False
            
        try:
            tools = self.mcp_service.get_tools()
            if tools and len(tools) > 0:
                self.tool_node = ToolNode(tools)
                self.tools_available = True
                logger.info(f"Tools refreshed - {len(tools)} tools available")
                return True
            else:
                logger.warning("No tools available after refresh")
                return False
        except Exception as e:
            logger.error(f"Failed to refresh tools: {e}")
            return False

    def _create_tool_call_messages(self, task: Task, state: SearchState) -> List:
        """Create messages with tool calls for ToolNode execution"""
        # Add context to tool arguments
        enhanced_args = task.tool_args.copy() if task.tool_args else {}
        
        # Always include index_id if available
        if state.index_id and "index_id" not in enhanced_args:
            enhanced_args["index_id"] = state.index_id
        
        if state.document_id and "document_id" not in enhanced_args:
            enhanced_args["document_id"] = state.document_id
            
        if state.segment_id and "segment_id" not in enhanced_args:
            enhanced_args["segment_id"] = state.segment_id
        
        # Create an AIMessage with tool_calls
        ai_message = AIMessage(
            content=f"I'll execute the task: {task.title}",
            tool_calls=[{
                "name": task.tool_name,
                "args": enhanced_args,
                "id": f"tool_call_{task.tool_name}_{int(time.time())}"
            }]
        )
        
        return [ai_message]

    def _extract_tool_results(self, tool_messages: List[ToolMessage]) -> Dict[str, Any]:
        """Extract results from tool execution messages"""
        result = {
            "text": "",
            "references": [],
            "raw_results": []
        }
        
        for message in tool_messages:
            if isinstance(message, ToolMessage):
                try:
                    content = message.content
                    
                    # Handle None content
                    if content is None:
                        logger.warning("Tool message content is None")
                        result["text"] = "Tool returned no data"
                        continue
                    
                    # Try to parse as JSON if it's a string
                    if isinstance(content, str):
                        if content.strip() and (content.strip().startswith('{') or content.strip().startswith('[')):
                            try:
                                content = json.loads(content)
                            except:
                                pass
                    
                    # Extract from structured response
                    if isinstance(content, dict):
                        # Check for nested data structure - handle both direct and double-nested
                        data = content.get("data", content) if content else {}
                        # Handle double-nested structure from hybrid_search
                        if isinstance(data, dict) and "data" in data:
                            data = data["data"]
                        
                        # Extract references
                        if data and "references" in data and isinstance(data.get("references"), list):
                            for ref in data["references"]:
                                if isinstance(ref, str):
                                    # Parse "title : url" format
                                    if " : " in ref:
                                        title, url = ref.split(" : ", 1)
                                        result["references"].append({
                                            "id": f"ref_{len(result['references'])}",
                                            "type": "document",
                                            "title": title.strip(),
                                            "value": url.strip()
                                        })
                                    else:
                                        result["references"].append({
                                            "id": f"ref_{len(result['references'])}",
                                            "type": "document", 
                                            "title": ref.strip(),
                                            "value": ref.strip()
                                        })
                                elif isinstance(ref, dict):
                                    # Already structured reference
                                    if "id" not in ref:
                                        ref["id"] = f"ref_{len(result['references'])}"
                                    result["references"].append(ref)
                        
                        # Extract results array (for hybrid_search)
                        if data and "results" in data and isinstance(data.get("results"), list):
                            for item in data["results"]:
                                if isinstance(item, dict):
                                    # Debug: Log the actual item structure
                                    print(f"🔍 DEBUG - Search result item keys: {list(item.keys())}")
                                    print(f"🔍 DEBUG - file_name in item: {'file_name' in item}")
                                    if 'file_name' in item:
                                        print(f"🔍 DEBUG - file_name value: '{item['file_name']}'")
                                    else:
                                        print(f"🔍 DEBUG - Available keys: {item.keys()}")
                                    # Extract document information
                                    doc_info = []
                                    if "document_id" in item:
                                        doc_info.append(f"Document: {item['document_id']}")
                                    if "page_index" in item:
                                        doc_info.append(f"Page: {item['page_index']}")
                                    if "score" in item:
                                        doc_info.append(f"Score: {item['score']:.3f}")
                                    
                                    # Extract content
                                    content_text = item.get("content", "")
                                    if content_text:
                                        result_text = " | ".join(doc_info) + "\n" + content_text
                                        result["text"] += result_text + "\n\n"
                                    
                                    # Create structured reference from search result
                                    # Similar to response_formatter.py's _create_search_image_reference
                                    if "document_id" in item:
                                        ref_data = {
                                            "id": f"ref_{len(result['references'])}",
                                            "type": "image",  # Search results are page images
                                            "title": f"Page {item.get('page_index', 0)}",
                                            "display_name": f"{item.get('file_name', '') or item.get('filename', '') or item.get('name', '') or item.get('document_name', '') or 'Unknown File'} - Segment {item.get('segment_index', item.get('page_index', 0)) + 1}",
                                            "value": content_text[:200] if content_text else "",
                                            "document_id": item.get('document_id', ''),
                                            "page_index": item.get('page_index', 0),
                                            "page_id": item.get('page_id', ''),
                                            "score": item.get('score', 0),
                                            "file_name": item.get('file_name', '') or item.get('filename', '') or item.get('name', '') or item.get('document_name', ''),
                                            "segment_index": item.get('segment_index', item.get('page_index', 0))
                                        }
                                        
                                        # Add image_uri and file_uri if available
                                        if "image_uri" in item or "image_presigned_url" in item:
                                            ref_data["image_uri"] = item.get("image_uri") or item.get("image_presigned_url")
                                            
                                        if "file_uri" in item or "file_presigned_url" in item:
                                            ref_data["file_uri"] = item.get("file_uri") or item.get("file_presigned_url")
                                            
                                        result["references"].append(ref_data)
                        
                        # Extract content field
                        if data and "content" in data:
                            content_data = data["content"]
                            if isinstance(content_data, list):
                                for item in content_data:
                                    if isinstance(item, str):
                                        result["text"] += item + "\n"
                            elif isinstance(content_data, str):
                                result["text"] += content_data + "\n"
                        
                        # Store raw result
                        result["raw_results"].append(content)
                    
                    # Plain text result
                    elif isinstance(content, str) and content.strip():
                        result["text"] += content + "\n"
                        result["raw_results"].append(content)
                
                except Exception as e:
                    logger.error(f"Error processing tool message: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    result["text"] += f"Error processing result: {str(e)}\n"
        
        # Clean up text
        result["text"] = result["text"].strip()
        if not result["text"] and result["raw_results"]:
            # Fallback to raw results if no text extracted
            result["text"] = json.dumps(result["raw_results"], indent=2)
        
        return result

    async def astream(self, state: SearchState) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream task execution with real-time updates
        
        Args:
            state: Current chat state with plan
            
        Yields:
            Execution updates and results
        """
        if not state.plan or not state.plan.tasks:
            logger.warning("No tasks to execute")
            yield {
                "type": "execution_skip",
                "message": "No tasks to execute",
                "timestamp": time.time()
            }
            return
        
        # Try to refresh tools if not available
        if not self.tools_available or not self.tool_node:
            logger.warning("Tools not available, attempting to refresh...")
            refresh_success = await self.refresh_tools()
            
            if not refresh_success:
                logger.error("Tools not available for execution after refresh attempt")
                yield {
                    "type": "execution_error",
                    "error": "MCP tools not available - servers may not be running or configured properly",
                    "timestamp": time.time()
                }
                return
        
        logger.info(f"Executing {len(state.plan.tasks)} tasks...")
        
        executed_tasks = []
        all_references = []
        
        for i, task in enumerate(state.plan.tasks):
            task_start_time = time.time()
            
            # Update task status
            task.status = TaskStatus.EXECUTING
            
            yield {
                "type": "task_start",
                "task_index": i,
                "task": task.model_dump(),
                "message": f"Executing: {task.title}",
                "timestamp": time.time()
            }

            try:
                # Create messages with tool calls
                logger.info(f"Executing task: {task.title} with tool: {task.tool_name}")
                messages = self._create_tool_call_messages(task, state)
                
                # Execute tool using ToolNode
                tool_result = await self.tool_node.ainvoke({"messages": messages})
                
                # Extract results from tool messages
                tool_messages = tool_result.get("messages", [])
                processed_result = self._extract_tool_results(tool_messages)
                
                # Update task
                task.status = TaskStatus.COMPLETED
                task.result = processed_result.get("text", "Task completed")
                task.execution_time = time.time() - task_start_time

                # Extract references
                references = processed_result.get("references", [])
                if references:
                    all_references.extend(references)
                    logger.info(f"Extracted {len(references)} references from task")

                # Store execution info
                executed_task_info = {
                    "task": task,
                    "result": processed_result,
                    "success": True,
                    "execution_time": task.execution_time
                }
                executed_tasks.append(executed_task_info)

                logger.info(f"Task completed in {task.execution_time:.2f}s")
                
                yield {
                    "type": "task_complete",
                    "task_index": i,
                    "task": task.model_dump(),
                    "result": processed_result,
                    "references": references,
                    "execution_time": task.execution_time,
                    "message": f"Completed: {task.title}",
                    "timestamp": time.time()
                }
                
            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                
                task.status = TaskStatus.FAILED
                task.result = str(e)
                task.execution_time = time.time() - task_start_time
                
                executed_task_info = {
                    "task": task,
                    "result": {"text": str(e), "references": []},
                    "success": False,
                    "execution_time": task.execution_time,
                    "error": str(e)
                }
                executed_tasks.append(executed_task_info)
                
                yield {
                    "type": "task_failed",
                    "task_index": i,
                    "task": task.model_dump(),
                    "error": str(e),
                    "execution_time": task.execution_time,
                    "message": f"Failed: {task.title}",
                    "timestamp": time.time()
                }
        
        # Summary
        successful_count = sum(1 for task_info in executed_tasks if task_info["success"])
        logger.info(f"Execution complete: {successful_count}/{len(executed_tasks)} successful")
        
        yield {
            "type": "execution_complete",
            "total_tasks": len(executed_tasks),
            "successful_tasks": successful_count,
            "failed_tasks": len(executed_tasks) - successful_count,
            "executed_tasks": executed_tasks,
            "all_references": all_references,
            "message": f"Execution complete: {successful_count}/{len(executed_tasks)} successful",
            "timestamp": time.time()
        }

    async def ainvoke(self, state: SearchState) -> Dict[str, Any]:
        """
        Execute tasks without streaming (for testing/fallback)
        
        Args:
            state: Current chat state with plan
            
        Returns:
            Execution results
        """
        results = []
        async for event in self.astream(state):
            results.append(event)
        
        # Return the final execution_complete event
        for event in reversed(results):
            if event.get("type") == "execution_complete":
                return event
        
        return {
            "type": "execution_complete",
            "executed_tasks": [],
            "all_references": [],
            "message": "No execution results"
        }