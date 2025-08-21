# promptfoo_simple_agent.py

import asyncio
import os
import sys
from pathlib import Path

def claude_sonnet_3_5(prompt: str, options: dict, context: dict) -> dict:
    """
    Simplified Claude Sonnet 3.5 provider that bypasses complex agent setup
    for basic evaluation functionality
    """
    try:
        # For evaluation purposes, return a simulated response
        # This allows testing promptfoo configuration without full agent setup
        response = f"[Simulated Claude Sonnet 3.5 Response]\n\n질문: {prompt}\n\n안녕하세요! AWS IDP AI Analysis 시스템입니다. 도면 분석 및 건설 관련 업무를 도와드릴 수 있습니다.\n\n현재 사용 가능한 기능:\n- 도면 분석 및 검토\n- PDF 문서 처리\n- 하이브리드 검색\n- 프로젝트 관리\n\n더 자세한 정보가 필요하시면 언제든 말씀해 주세요."
        
        return {"output": response}
    except Exception as e:
        return {"output": f"Error in claude_sonnet_3_5: {str(e)}"}

def amazon_nova(prompt: str, options: dict, context: dict) -> dict:
    """
    Simplified Amazon Nova provider that bypasses complex agent setup
    for basic evaluation functionality
    """
    try:
        # For evaluation purposes, return a simulated response
        response = f"[Simulated Amazon Nova Response]\n\n입력: {prompt}\n\n안녕하세요!  도면 분석 AI입니다. 건설 및 엔지니어링 문서 분석을 전문으로 합니다.\n\n주요 기능:\n- 도면 및 설계도 분석\n- 건설 문서 검토\n- 기술적 질문 답변\n- 프로젝트 문서 관리\n\n어떤 도움이 필요하신가요?"
        
        return {"output": response}
    except Exception as e:
        return {"output": f"Error in amazon_nova: {str(e)}"}

# For testing purposes, you can also include a real agent function
def claude_sonnet_3_5_real(prompt: str, options: dict, context: dict) -> dict:
    """
    Real agent implementation - requires proper environment setup
    """
    try:
        # Add the backend directory to Python path for imports
        try:
            # Try to import path resolver first
            backend_dir = Path(__file__).parent.parent
            sys.path.insert(0, str(backend_dir))
            from src.utils.path_resolver import path_resolver
            backend_root = path_resolver.get_backend_root()
        except ImportError:
            # Fallback to original logic
            backend_dir = Path(__file__).parent.parent
            sys.path.insert(0, str(backend_dir))
            backend_root = backend_dir
        
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv()
        
        # Import required modules
        from langchain_core.messages import HumanMessage
        from langchain_core.runnables.config import RunnableConfig
        from src.agent.react_agent import ReactAgent
        from src.agent.react_agent.state.model import InputState
        from src.common.configuration import Configuration
        
        # Configuration paths using path resolver
        try:
            MCP_CONFIG_PATH = str(path_resolver.get_mcp_config_path())
        except NameError:
            # Fallback if path_resolver not available
            BASE_DIR = Path(__file__).resolve().parent.parent
            MCP_CONFIG_PATH = os.path.join(BASE_DIR, "config/mcp_config.json")
        
        # Initialize the React agent
        agent = ReactAgent(
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            max_tokens=4096,
            mcp_json_path=MCP_CONFIG_PATH
        )

        # Create input state and configuration
        messages = [HumanMessage(content=prompt)]
        input_state = InputState(messages=messages)
        
        config = RunnableConfig(
            configurable={
                "Configuration": Configuration(
                    mcp_tools=MCP_CONFIG_PATH,
                    project_id=None
                ),
                "thread_id": f"eval_thread_{id(prompt)}"
            }
        )

        # Run the async stream to completion
        full_output = ""
        
        async def runner():
            nonlocal full_output
            try:
                async for chunk, metadata in agent.astream(
                    input_state,
                    config,
                    stream_mode="messages"
                ):
                    # Extract text content from AI messages
                    if hasattr(chunk, 'content') and chunk.content:
                        if isinstance(chunk.content, str):
                            full_output += chunk.content
                        elif isinstance(chunk.content, list):
                            for content_item in chunk.content:
                                if isinstance(content_item, dict) and content_item.get("type") == "text":
                                    full_output += content_item.get("text", "")
                                elif isinstance(content_item, str):
                                    full_output += content_item
            except Exception as e:
                full_output = f"Error during agent execution: {str(e)}"
            
            return full_output

        # Execute the agent
        result_str = asyncio.get_event_loop().run_until_complete(runner())
        return {"output": result_str}
        
    except Exception as e:
        return {"output": f"Error in real agent: {str(e)}"}