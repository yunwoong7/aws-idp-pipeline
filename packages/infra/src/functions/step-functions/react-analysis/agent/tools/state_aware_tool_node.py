"""
State-aware ToolNode for LangGraph integration
Automatically passes LangGraph State to tools that support it
"""

import logging
import time
from typing import Dict, Any, List
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, AIMessage
from langgraph.prebuilt import ToolNode
from agent.tools.state_aware_base import StateAwareBaseTool

logger = logging.getLogger(__name__)


def _update_combined_analysis_context(state: Dict[str, Any], analysis_history: List[Dict[str, Any]]) -> str:
    """
    이전 분석 내용과 현재 세션 분석 이력을 결합해서 combined_analysis_context 생성
    
    Args:
        state: LangGraph State
        analysis_history: 현재 세션 분석 이력
        
    Returns:
        결합된 분석 컨텍스트 문자열
    """
    previous_context = state.get("previous_analysis_context", "")
    
    # 이전 분석 내용
    context_parts = []
    if previous_context and "이전 분석 결과 없음" not in previous_context:
        context_parts.append("### 🗂️ 이전 세션 분석 내용")
        context_parts.append(previous_context)
    
    # 현재 세션 분석 이력
    if analysis_history:
        context_parts.append(f"\n### 🔄 현재 세션 분석 결과 ({len(analysis_history)}개):")
        
        for i, entry in enumerate(analysis_history, 1):
            tool_name = entry.get("tool_name", "Unknown")
            content = entry.get("content", "")
            success = entry.get("success", False)
            step = entry.get("step", 0)
            
            status = "✅" if success else "❌"
            
            # 내용이 너무 길면 요약
            if len(content) > 1200:
                content_preview = content[:1200] + "...[요약됨]"
            else:
                content_preview = content
            
            context_parts.append(f"\n{i}. **{status} {tool_name}** (Step {step}):")
            context_parts.append(f"   {content_preview}")
    
    combined_context = "\n".join(context_parts) if context_parts else "**분석 내용**: 분석 결과 없음"
    
    logger.info(f"📊 결합 컨텍스트 업데이트: 이전({len(previous_context)}) + 현재({len(analysis_history)}) = 총 {len(combined_context)} 문자")
    
    return combined_context


class StateAwareToolNode:
    """
    Custom ToolNode that passes LangGraph State to StateAware tools
    """
    
    def __init__(self, tools: List[BaseTool]):
        """
        Initialize with tools
        
        Args:
            tools: List of tools (mix of regular and StateAware tools)
        """
        self.tools = {tool.name: tool for tool in tools}
        self.base_tool_node = ToolNode(tools)
        
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute tools with State context
        
        Args:
            state: LangGraph State dictionary
            
        Returns:
            Updated state with tool results
        """
        logger.info("🔧 StateAwareToolNode: 도구 실행 시작")
        
        # Get messages to find tool calls
        messages = state.get("messages", [])
        if not messages:
            logger.warning("No messages in state")
            return state
            
        last_message = messages[-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            logger.warning("No tool calls found in last message")
            return state
            
        # Process each tool call
        tool_messages = []
        tools_used = state.get("tools_used", [])
        tool_results = state.get("tool_results", [])
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            logger.info(f"🔧 도구 실행: {tool_name}")
            
            # Get the tool
            tool = self.tools.get(tool_name)
            if not tool:
                error_msg = f"Unknown tool: {tool_name}"
                logger.error(error_msg)
                tool_message = ToolMessage(
                    content=error_msg,
                    tool_call_id=tool_call_id
                )
                tool_messages.append(tool_message)
                continue
                
            try:
                # Check if tool is StateAware
                if isinstance(tool, StateAwareBaseTool):
                    logger.info(f"🔧 StateAware 도구: {tool_name} - State 전달")
                    
                    # Execute with state context
                    result = tool.execute_with_state(state, **tool_args)
                    
                    # Create tool message
                    tool_message = ToolMessage(
                        content=result.message,
                        tool_call_id=tool_call_id
                    )
                    
                    # Track tool usage
                    if tool_name not in tools_used:
                        tools_used.append(tool_name)
                    
                    tool_result_entry = {
                        "tool_name": tool_name,
                        "success": result.success,
                        "message": result.message,
                        "data": result.data,
                        "execution_time": getattr(result, 'execution_time', 0),
                        "timestamp": time.time()
                    }
                    
                    tool_results.append(tool_result_entry)
                    
                    # analysis_history에도 추가
                    analysis_history = state.get("analysis_history", [])
                    analysis_entry = {
                        "tool_name": tool_name,
                        "content": result.message,
                        "success": result.success,
                        "timestamp": time.time(),
                        "execution_time": getattr(result, 'execution_time', 0),
                        "step": state.get("current_step", 0)
                    }
                    analysis_history.append(analysis_entry)
                    
                    logger.info(f"📊 분석 이력에 추가: {tool_name} -> 총 {len(analysis_history)}개 항목")
                    
                else:
                    logger.info(f"🔧 일반 도구: {tool_name} - 기본 실행")
                    
                    # Use base ToolNode for non-StateAware tools
                    # Create a temporary state with only this tool call
                    temp_last_message = AIMessage(
                        content=last_message.content,
                        tool_calls=[tool_call]
                    )
                    temp_state = {
                        **state,
                        "messages": messages[:-1] + [temp_last_message]
                    }
                    
                    # Execute with base ToolNode
                    temp_result = self.base_tool_node(temp_state)
                    
                    # Extract the tool message
                    if temp_result.get("messages"):
                        new_messages = temp_result["messages"]
                        if new_messages and isinstance(new_messages[-1], ToolMessage):
                            tool_message = new_messages[-1]
                        else:
                            tool_message = ToolMessage(
                                content="Tool execution completed",
                                tool_call_id=tool_call_id
                            )
                    else:
                        tool_message = ToolMessage(
                            content="Tool execution completed",
                            tool_call_id=tool_call_id
                        )
                    
                    # Track tool usage
                    if tool_name not in tools_used:
                        tools_used.append(tool_name)
                
                tool_messages.append(tool_message)
                logger.info(f"✅ 도구 실행 완료: {tool_name}")
                
            except Exception as e:
                error_msg = f"Tool execution failed: {str(e)}"
                logger.error(f"❌ 도구 실행 실패 {tool_name}: {str(e)}")
                
                tool_message = ToolMessage(
                    content=error_msg,
                    tool_call_id=tool_call_id
                )
                tool_messages.append(tool_message)
        
        # Update analysis_history and combined_analysis_context
        analysis_history = state.get("analysis_history", [])
        combined_analysis_context = _update_combined_analysis_context(state, analysis_history)
        
        # Update state with tool results
        updated_state = {
            **state,
            "messages": messages + tool_messages,
            "tools_used": tools_used,
            "tool_results": tool_results,
            "analysis_history": analysis_history,
            "combined_analysis_context": combined_analysis_context
        }
        
        logger.info(f"🔧 StateAwareToolNode: {len(tool_messages)}개 도구 실행 완료")
        logger.info(f"📊 분석 이력: {len(analysis_history)}개, 결합 컨텍스트: {len(combined_analysis_context)} 문자")
        return updated_state