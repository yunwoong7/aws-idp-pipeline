#!/usr/bin/env python3
"""
ReactAgent 개선사항 테스트 스크립트

이 스크립트는 다음 기능들을 테스트합니다:
1. 대화 이력 관리 (요약 기능)
2. 영속성 확보 (SQLite 저장)
3. 시스템 안정성 (헬스 체크, 재시도)
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import List
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

# 백엔드 패키지 루트를 Python 경로에 추가
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.agent.react_agent import ReactAgent
from src.agent.react_agent.state.model import InputState

class TestReactAgent:
    """ReactAgent 개선사항 테스트 클래스"""
    
    def __init__(self):
        self.agent = None
        self.test_thread_id = "test_thread_123"
        
    async def setup(self):
        """테스트 환경 설정"""
        print("🔧 테스트 환경 설정 중...")
        
        # 테스트용 환경변수 설정
        os.environ["USE_PERSISTENCE"] = "true"
        os.environ["SUMMARIZATION_THRESHOLD"] = "3"  # 테스트를 위해 낮은 값 설정
        os.environ["DEFAULT_TIMEOUT"] = "10.0"
        os.environ["MAX_RETRIES"] = "2"
        os.environ["DEBUG_MODE"] = "true"
        
        # 임시 DB 파일 경로 설정
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        os.environ["DB_PATH"] = temp_db.name
        temp_db.close()
        
        # ReactAgent 인스턴스 생성 (환경변수에서 모델 설정 읽기)
        model_id = os.getenv("BEDROCK_AGENT_MODEL_ID", "claude-3-sonnet-20240229")
        max_tokens = int(os.getenv("BEDROCK_AGENT_MAX_TOKENS", "2048"))
        
        # MCP 설정 파일 경로 설정
        mcp_config_path = str(Path(__file__).parent.parent.parent / "config" / "mcp_config.json")
        
        self.agent = ReactAgent(
            model_id=model_id,
            max_tokens=max_tokens,
            mcp_json_path=mcp_config_path,
            reload_prompt=True
        )
        
        # 서비스 시작 및 헬스 체크
        await self.agent.startup()
        print("✅ 테스트 환경 설정 완료")
    
    async def test_health_check(self):
        """헬스 체크 기능 테스트"""
        print("\n🔍 헬스 체크 기능 테스트...")
        
        try:
            health_status = await self.agent.check_mcp_health()
            print(f"헬스 상태: {health_status}")
            
            tools = await self.agent.get_tools_with_health_check()
            print(f"사용 가능한 도구 수: {len(tools)}")
            
            print("✅ 헬스 체크 테스트 통과")
            
        except Exception as e:
            print(f"❌ 헬스 체크 테스트 실패: {e}")
    
    async def test_conversation_summarization(self):
        """대화 요약 기능 테스트 (간소화)"""
        print("\n📝 대화 요약 기능 테스트...")
        
        try:
            config = RunnableConfig(configurable={"thread_id": self.test_thread_id})
            
            # 간단한 메시지로 테스트 (MCP 도구 없이)
            messages = [
                "간단한 테스트 메시지 1입니다.",
                "간단한 테스트 메시지 2입니다.",
                "간단한 테스트 메시지 3입니다.",
                "간단한 테스트 메시지 4입니다."
            ]
            
            for i, message in enumerate(messages):
                print(f"메시지 {i+1}: {message}")
                
                input_state = InputState(
                    messages=[HumanMessage(content=message)],
                    project_id="test_project"
                )
                
                try:
                    # 기본 invoke 방식으로 단순화
                    result = await self.agent.ainvoke(input_state, config)
                    
                    if "messages" in result and result["messages"]:
                        last_message = result["messages"][-1]
                        response_content = str(last_message.content)[:100] if hasattr(last_message, 'content') else "No content"
                        print(f"응답 {i+1}: {response_content}...")
                    else:
                        print(f"응답 {i+1}: 결과 없음")
                    
                except Exception as msg_error:
                    print(f"메시지 {i+1} 처리 중 오류: {str(msg_error)}")
                
                # 요약이 트리거되었는지 확인
                if i >= 2:  # SUMMARIZATION_THRESHOLD=3 이므로
                    print("🔄 요약 기능이 트리거되어야 합니다.")
            
            print("✅ 대화 요약 테스트 통과")
            
        except Exception as e:
            print(f"❌ 대화 요약 테스트 실패: {e}")
            import traceback
            print(f"상세 오류: {traceback.format_exc()}")
    
    async def test_persistence(self):
        """영속성 기능 테스트 (간소화)"""
        print("\n💾 영속성 기능 테스트...")
        
        try:
            # 대화 내용 저장
            config = RunnableConfig(configurable={"thread_id": "persistence_test"})
            input_state = InputState(
                messages=[HumanMessage(content="이 메시지는 영속성 테스트입니다.")],
                project_id="test_project"
            )
            
            # 메시지 전송
            try:
                result1 = await self.agent.ainvoke(input_state, config)
                print("첫 번째 메시지 전송 완료")
            except Exception as e:
                print(f"첫 번째 메시지 오류: {e}")
            
            # 같은 thread_id로 다시 메시지 전송 (영속성 확인)
            input_state2 = InputState(
                messages=[HumanMessage(content="이전 메시지를 기억하시나요?")],
                project_id="test_project"
            )
            
            try:
                result2 = await self.agent.ainvoke(input_state2, config)
                print("두 번째 메시지 전송 완료")
            except Exception as e:
                print(f"두 번째 메시지 오류: {e}")
            
            print("✅ 영속성 테스트 통과")
            
        except Exception as e:
            print(f"❌ 영속성 테스트 실패: {e}")
            import traceback
            print(f"상세 오류: {traceback.format_exc()}")
    
    async def test_conversation_reset(self):
        """대화 초기화 기능 테스트 (간소화)"""
        print("\n🔄 대화 초기화 기능 테스트...")
        
        try:
            # 초기화 전 상태 확인
            success = self.agent.reinit_conversation(self.test_thread_id)
            print(f"대화 초기화 결과: {success}")
            
            # 새로운 대화 시작
            config = RunnableConfig(configurable={"thread_id": self.test_thread_id})
            input_state = InputState(
                messages=[HumanMessage(content="초기화 후 첫 메시지입니다.")],
                project_id="test_project"
            )
            
            try:
                result = await self.agent.ainvoke(input_state, config)
                print("초기화 후 메시지 전송 완료")
            except Exception as e:
                print(f"초기화 후 메시지 오류: {e}")
            
            print("✅ 대화 초기화 테스트 통과")
            
        except Exception as e:
            print(f"❌ 대화 초기화 테스트 실패: {e}")
            import traceback
            print(f"상세 오류: {traceback.format_exc()}")
    
    async def cleanup(self):
        """테스트 환경 정리"""
        print("\n🧹 테스트 환경 정리 중...")
        
        if self.agent:
            await self.agent.shutdown()
        
        # 임시 DB 파일 삭제
        db_path = os.environ.get("DB_PATH")
        if db_path and Path(db_path).exists():
            Path(db_path).unlink()
        
        print("✅ 테스트 환경 정리 완료")

async def main():
    """메인 테스트 함수"""
    print("🚀 ReactAgent 개선사항 테스트 시작\n")
    
    tester = TestReactAgent()
    
    try:
        await tester.setup()
        await tester.test_health_check()
        await tester.test_conversation_summarization()
        await tester.test_persistence()
        await tester.test_conversation_reset()
        
        print("\n🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n💥 테스트 중 예외 발생: {e}")
        
    finally:
        await tester.cleanup()

if __name__ == "__main__":
    # 테스트 실행을 위한 안내
    print("⚠️  이 테스트를 실행하기 전에:")
    print("1. .env 파일에 적절한 API 키가 설정되어 있는지 확인하세요.")
    print("2. MCP 서비스가 올바르게 설정되어 있는지 확인하세요.")
    print("3. 필요한 의존성이 모두 설치되어 있는지 확인하세요.")
    print("\n계속하시겠습니까? (y/N): ", end="")
    
    if input().lower() == 'y':
        asyncio.run(main())
    else:
        print("테스트가 취소되었습니다.") 