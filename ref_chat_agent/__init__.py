# src/agent/workflow.py
import sys
import os
from pathlib import Path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from colorama import Fore, Style
from langgraph.graph import END, StateGraph
from src.chat_agent.states.schemas import AgentState
from src.chat_agent.nodes.planner import PlannerNode
from src.chat_agent.nodes.executor import ExecutorNode
from src.chat_agent.nodes.responder import ResponderNode
from src.chat_agent.tools.hybrid_search import HybridSearchTool
from src.chat_agent.tools import registry
from src.chat_agent.service.llm import BedrockLLMService
from typing import Dict
import time
from src.monitoring.phoenix import setup_phoenix
from dotenv import load_dotenv

root_dir = Path(__file__).resolve().parents[2]
env_path = root_dir / '.env'

# load environment variables
load_dotenv(env_path)

planner_model_id = os.environ.get("AWS_PLANNER_MODEL")
planner_temperature = os.environ.get("AWS_PLANNER_TEMPERATURE")
planner_max_tokens = os.environ.get("AWS_PLANNER_MAX_TOKENS")
responder_model_id = os.environ.get("AWS_RESPONDER_MODEL")
responder_temperature = os.environ.get("AWS_RESPONDER_TEMPERATURE")
responder_max_tokens = os.environ.get("AWS_RESPONDER_MAX_TOKENS")

# ===== Define the Search Agent Workflow class =====
class ChatAgentWorkflow:
    def __init__(self, tracer_provider=None, **model_configs):
        # Initialize LLM models
        self.planner_model = BedrockLLMService(
            model_id=model_configs.get('planner_model_id') or os.environ.get("AWS_PLANNER_MODEL"), 
            temperature=model_configs.get('planner_temperature') or os.environ.get("AWS_PLANNER_TEMPERATURE"), 
            max_tokens=model_configs.get('planner_max_tokens') or os.environ.get("AWS_PLANNER_MAX_TOKENS"),
            tracer_provider=tracer_provider
        )
        self.responder_model = BedrockLLMService(
            model_id=model_configs.get('responder_model_id') or os.environ.get("AWS_RESPONDER_MODEL"), 
            temperature=model_configs.get('responder_temperature') or os.environ.get("AWS_RESPONDER_TEMPERATURE"), 
            max_tokens=model_configs.get('responder_max_tokens') or os.environ.get("AWS_RESPONDER_MAX_TOKENS"),
            tracer_provider=tracer_provider
        )
        
         # Setup tools and register them
        self._setup_tools()

        # Create workflow
        self.workflow = self._create_workflow()

    def _setup_tools(self):
        """Setup tools and register them in the registry"""
        
        # Create hybrid search tool
        hybrid_search_tool = HybridSearchTool()
        registry.register_tool("hybrid_search", hybrid_search_tool)
        
        # Additional tools can be registered here
        # weather_tool = WeatherTool(api_key="...")
        # registry.register_tool("weather", weather_tool)
        
        # Get the list of LangChain-formatted tools for the workflow
        self.tools = registry.get_all_langchain_tools()

    def check_execution_needed(self, state: AgentState) -> str:
        """Check if we need to execute tasks"""
        start_time = time.time()
        # check if we need to execute tasks
        next_step = "execute" if state.plan.requires_tool and len(state.plan.tasks) > 0 else "respond"
        
        elapsed_time = time.time() - start_time
        print(Fore.GREEN + "\n🔍 Checking Execution State" + Fore.WHITE + "(Next step:" + next_step + ")" + Style.RESET_ALL)
        print(Fore.YELLOW + f"⏱️ Check took: {elapsed_time:.2f} seconds" + Style.RESET_ALL)
        return next_step

    def check_next_step(self, state: AgentState) -> str:
        """Check if we need more planning or can proceed to response"""
        print("\n🔄 Checking remaining tasks...")
        start_time = time.time()
        
        # Check if we have more tasks to execute
        next_step = "plan" if state.remaining_tasks else "respond"
        
        elapsed_time = time.time() - start_time
        print(f"Next step: {next_step}")
        print(f"⏱️ Check took: {elapsed_time:.2f} seconds")
        return next_step

    def _create_workflow(self) -> StateGraph:
        """Create workflow"""
        workflow = StateGraph(AgentState)
        # ========== Add nodes to the workflow graph ==========
        # show thought process
        show_thought_process = False
        # Add the plan node
        workflow.add_node("planner", PlannerNode(self.planner_model, self.tools, verbose=True))
        # Add the executor node
        workflow.add_node("executor", ExecutorNode(self.tools))
        # Add the responder node
        workflow.add_node("responder", ResponderNode(self.responder_model, show_thought_process))   

        # ========== Add edges to the workflow graph ==========
        # From start to planner
        workflow.set_entry_point("planner")
        # From responder to end
        workflow.add_edge("responder", END)
        
        # ========== Add conditional edges to the workflow graph ==========
        workflow.add_conditional_edges(
            "planner",
            # Check if we need to execute tasks
            self.check_execution_needed,
            {
                "execute": "executor",
                "respond": "responder"
            }
        )
        
        workflow.add_conditional_edges(
            "executor",
            # Check if we need more planning
            self.check_next_step,
            {
                "plan": "planner",
                "respond": "responder"
            }
        )
        
        return workflow.compile()
    
    async def astream(self, state: AgentState):
        """Async stream of the workflow execution"""
        async for event in self.workflow.astream(state, stream_mode=["messages", "updates"]):
            # print(event)
            if isinstance(event, tuple):
                mode = event[0] # messages or updates
                if mode == "messages":
                    msg_chunk = event[1][0]
                    node = event[1][1].get("langgraph_node")
                    if (hasattr(msg_chunk, 'content') and 
                        msg_chunk.content and 
                        isinstance(msg_chunk.content, list) and 
                        len(msg_chunk.content) > 0):
                        content = msg_chunk.content[0]
                        if isinstance(content, dict) and content.get("type") == "tool_use":
                            token = content.get("input", "")
                            if token:
                                # yield token
                                # case for tool_use response
                                yield {
                                    node: {"token": token},
                                    "status": "in_progress"
                                }
                        elif isinstance(content, dict) and content.get("type") == "text":
                            token = content.get("text", "")
                            if token:
                                # yield token
                                # case for text response
                                yield {
                                    node: {"token": token},
                                    "status": "in_progress"
                                }
                elif mode == "updates":
                    updates = event[1]  # updates
                    yield updates


if __name__ == "__main__":
    # Test the Search Agent
    # python src/agent/workflow.py test
    import argparse
    import asyncio
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', default='default')
    args = parser.parse_args()

    try:
        print("🚀 Starting Search Agent test...")
        # Phoenix 설정
        tracer_provider = setup_phoenix()
        # Create agent
        agent = ChatAgentWorkflow(tracer_provider=tracer_provider)

        if args.mode == 'test':
            # Get user input
            test_query = input("\n❓ Enter your query: ")
        else:
            # Use default test query
            test_query = "2022년 11월 데이터에서 MAGA이라는 글자가 있는 이미지 찾아줘"
            # test_query = "Hi, how are you?"
        
        initial_state = AgentState.initial_state()
        initial_state.input = test_query

        # Run agent
        async def test_streaming():
            streaming_response = False
            async for event in agent.astream(initial_state):
                if "planner" in event:
                    if "in_progress" in event.get("status", ""):
                        token = event.get("planner", {}).get("token")
                        print(Fore.WHITE + token + Style.RESET_ALL, end='', flush=True)
                    else:
                        plan = event["planner"].get("plan")
                        print (Fore.WHITE + f"\n✅ Plan generated: {plan}" + Style.RESET_ALL)
                elif "executor" in event:
                    pass
                elif "responder" in event:
                    if "in_progress" in event.get("status", ""):
                        token = event.get("responder", {}).get("token")
                        print(Fore.WHITE + token + Style.RESET_ALL, end='', flush=True)
                        streaming_response = True
                    else:
                        if not streaming_response:
                            print(Fore.WHITE + event["responder"].get("response", "") + Style.RESET_ALL)
        asyncio.run(test_streaming())
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")

# 싱글톤 인스턴스 생성
chat_agent = ChatAgentWorkflow()

# 내보내기
__all__ = ['ChatAgentWorkflow', 'chat_agent']