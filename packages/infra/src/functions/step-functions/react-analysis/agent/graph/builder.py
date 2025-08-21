"""
LangGraph graph builder
Configuration for analysis workflow using LangGraph
"""

import logging
from typing import Literal, Dict, Any
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agent.state.agent_state import AgentState
from agent.nodes.model_node import ModelNode
from agent.nodes.tool_node import ToolNode
from agent.tools.registry import get_all_tools

logger = logging.getLogger(__name__)
memory = MemorySaver()


def create_analysis_graph(model):
    """
    Create LangGraph for analysis
    
    Args:
        model: LLM model instance
        
    Returns:
        Compiled LangGraph
    """
    logger.info("🏗️ Starting LangGraph analysis graph creation")
    
    # Load tools
    tools = get_all_tools()
    logger.info(f"🛠️ Loaded tools: {[tool.name for tool in tools]}")
    
    # Create nodes
    model_node = ModelNode(model, tools)
    tool_node = ToolNode(tools)
    
    # Configure graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("model", model_node)
    workflow.add_node("tools", tool_node)
    
    # Set entry point
    workflow.set_entry_point("model")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "model",
        _route_model_output,
        {
            "tools": "tools",
            "__end__": "__end__"
        }
    )
    
    # Connect tools → model
    workflow.add_edge("tools", "model")
    
    # Compile graph
    graph = workflow.compile(checkpointer=memory)
    
    logger.info("✅ LangGraph analysis graph creation complete")
    return graph


def _route_model_output(state: AgentState) -> Literal["__end__", "tools"]:
    """
    Determine next step based on model output
    
    Args:
        state: Current AgentState
        
    Returns:
        Next step: "__end__" or "tools"
    """
    # Check MAX_ITERATIONS flag (set in ModelNode)
    max_iterations_reached = state.get('max_iterations_reached', False)
    if max_iterations_reached:
        logger.info("🔄 MAX_ITERATIONS flag detected - forced termination")
        logger.info("🏁 Routing decision: __end__ (MAX_ITERATIONS handled in ModelNode)")
        return "__end__"
    
    # Check step limit
    current_step = state.get('current_step', 0)
    max_iterations = state.get('max_iterations', 10)
    
    # Debug logs
    logger.info("=" * 50)
    logger.info("🔍 _route_model_output called")
    logger.info(f"📊 Current step: {current_step}")
    logger.info(f"📊 Maximum iterations: {max_iterations}")
    logger.info(f"📊 Condition check: {current_step} >= {max_iterations} = {current_step >= max_iterations}")
    
    if current_step >= max_iterations:
        logger.info(f"🔄 Maximum iterations reached: {current_step}/{max_iterations}")
        logger.info("🏁 Routing decision: __end__ (iteration limit reached)")
        logger.info("=" * 50)
        return "__end__"
    
    # Check messages
    messages = state.get("messages", [])
    if not messages:
        logger.warning("❌ No messages - terminating")
        logger.info("🏁 Routing decision: __end__ (no messages)")
        logger.info("=" * 50)
        return "__end__"
    
    last_message = messages[-1]
    logger.info(f"📨 Last message type: {type(last_message).__name__}")
    
    # If AIMessage and tool_calls exist, execute tools
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        tool_names = [tc.get('name', 'Unknown') for tc in last_message.tool_calls]
        logger.info(f"🛠️ Moving to tool execution step: {tool_names}")
        logger.info("🏁 Routing decision: tools (tool calls required)")
        logger.info("=" * 50)
        return "tools"
    
    # If analysis is complete but content is insufficient, final summary creation is needed
    if isinstance(last_message, AIMessage):
        content = str(last_message.content) if last_message.content else ""
        
        # If analysis result is too short or meaningless, additional analysis is needed
        if len(content.strip()) < 100 or "analysis is complete" in content:
            analysis_history = state.get('analysis_history', [])
            combined_context = state.get('combined_analysis_context', '')
            
            # If there is actual analysis result, create final summary
            if analysis_history or combined_context:
                logger.info("🔄 Insufficient analysis result - re-sending to model for final summary")
                # Set special flag for final summary creation
                state['needs_final_summary'] = True
                logger.info("🏁 Routing decision: model (final summary needed)")
                logger.info("=" * 50)
                # Re-send to model, this time for final summary creation
                return "tools"  # Actually should go to model, but currently going through tools
    
    logger.info("🏁 Analysis complete - terminating")
    logger.info("🏁 Routing decision: __end__ (analysis complete)")
    logger.info("=" * 50)
    return "__end__"