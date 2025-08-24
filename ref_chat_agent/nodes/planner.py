# src/agent/nodes/planner.py
import sys
import os
import time
from colorama import Fore, Style
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from typing import cast
from copy import deepcopy
from datetime import datetime, timezone
import asyncio

from langchain.prompts import ChatPromptTemplate
from langchain_core.prompt_values import PromptValue
from langchain_core.tools import StructuredTool
from src.chat_agent.service.llm import BedrockLLMService
from src.chat_agent.states.schemas import AgentState, Plan
from langchain_core.messages import HumanMessage, AIMessage
from src.chat_agent.prompts import prompt_manager

# ====== Define the Planner class ======
class PlannerNode:
    def __init__(self, llm: BedrockLLMService, tools: list[StructuredTool], verbose: bool = False) -> None:
        self.model = llm.model.with_structured_output(Plan)
        self.tools = tools
        self.verbose = verbose

    def _get_tool_descriptions(self):
        # Create tool descriptions
        tool_descriptions = []
        for tool in self.tools:
            description = f"{tool.name}: {tool.description}"
            tool_descriptions.append(description)
        
        return "\n".join(tool_descriptions)
    
    def _get_current_datetime(self):
        # 현재 날짜/시간 포맷팅
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _build_messages(self, state: AgentState):
        tool_descriptions = self._get_tool_descriptions()
        current_datetime = self._get_current_datetime()

        # 메시지 히스토리 처리
        conversation = []
        for msg in state.message_history:
            if msg["role"] == "user":
                conversation.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                conversation.append(AIMessage(content=msg["content"]))
        
        conversation.append(HumanMessage(content=state.input))
        
        # 프롬프트 매니저를 통해 메시지 생성
        return prompt_manager.get_messages("planner", 
            datetime=current_datetime,
            tool_desc=tool_descriptions,
            user_query=state.input,
            conversation=conversation
        )
    
    async def __call__(self, state: AgentState):
        """Async generator for planning tasks"""
        print(Fore.GREEN + "\n📝 Planning tasks" + Style.RESET_ALL)
        messages = self._build_messages(state)
        plan = None

        async for event in self.model.astream_events(messages, version='v2'):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content and chunk.content[0].get("type") == "tool_use":
                    input_text = chunk.content[0].get("input", "")
                    if input_text:
                        if self.verbose:
                            print(Fore.WHITE + input_text + Style.RESET_ALL, end='', flush=True)
                        yield input_text
                        yield {
                            **state.model_dump(),
                            "response": input_text,
                        }
            elif event["event"] == "on_chain_end":
                plan = event["data"]["output"]
                yield {
                    **state.model_dump(),
                    "plan": plan,
                }     
            
    async def acall(self, state: AgentState) -> AgentState:
        """Async execution with streaming events"""
        # Generate plan
        response = await self.model.ainvoke(self._build_messages(state))
        result = cast(Plan, response)
        
        # Return state with plan
        return {
            **state.model_dump(),
            "plan": result,
        }
    

# Test the Planner            
if __name__ == "__main__":
    import os, sys
    from pathlib import Path
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from src.agent.tools.hybrid_search import HybridSearchTool
    from src.agent.service.llm import BedrockLLMService
    from dotenv import load_dotenv

    root_dir = Path(__file__).resolve().parents[3]
    env_path = root_dir / '.env'

    # load environment variables
    load_dotenv(env_path)

    model_id = os.environ.get("AWS_PLANNER_MODEL")
    temperature = os.environ.get("AWS_PLANNER_TEMPERATURE")
    max_tokens = os.environ.get("AWS_PLANNER_MAX_TOKENS")

    planner_model = BedrockLLMService(model_id=model_id, temperature=temperature, max_tokens=max_tokens)
    hybrid_search_tool = HybridSearchTool()
    tools = [hybrid_search_tool.get_tool()]

    async def run_tests():
        planner = PlannerNode(planner_model, tools)
        test_queries = ["KNN이라는 글자가 있는 이미지 찾아줘"]

        print("=== Starting Planner Tests ===")
        
        for query in test_queries:
            state = AgentState.initial_state()
            state.input = query
            
            try:
                print(Fore.CYAN + f"❓ Test query: {query}" + Style.RESET_ALL)
                async for result in planner(state):
                    if isinstance(result, str):
                        print(Fore.WHITE + result + Style.RESET_ALL, end='', flush=True)
                print("\n=====================================")
                print(Fore.WHITE + f"\n✅ Plan generated: {result['plan']}" + Style.RESET_ALL)
            except Exception as e:
                print(f"\n❌ Error during test: {str(e)}")

        print("\n=====================================")

    # Run the tests
    asyncio.run(run_tests())