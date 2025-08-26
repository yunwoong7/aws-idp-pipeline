"""
LangGraph Model Node - AI model calling
"""

import logging
import time
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

# Common module imports
sys.path.append('/opt/python')

from agent.state.agent_state import AgentState
from prompts import prompt_manager

logger = logging.getLogger(__name__)
memory = MemorySaver()


class ModelNode:
    """
    LangGraph Model Node - AI 모델 호출을 담당하는 노드
    """
    
    def __init__(self, model, tools):
        """
        Args:
            model: LLM 모델 인스턴스
            tools: 사용 가능한 도구 리스트
        """
        self.model = model
        self.tools = tools
        logger.info(f"🤖 ModelNode 초기화 완료 - 도구: {len(tools)}개")
        
    
    def __call__(self, state: AgentState, config: RunnableConfig) -> AgentState:
        """
        모델 노드 실행
        
        Args:
            state: LangGraph AgentState
            config: 실행 구성
            
        Returns:
            업데이트된 AgentState
        """
        logger.info("=== 🤖 MODEL NODE 실행 ===")
        
        # 입력 상태 로깅
        self._log_input_state(state)
        
        # 사용자 쿼리 추출 및 업데이트
        user_query = self._extract_user_query(state)
        
        # 현재 단계 증가 - 상세 로깅 추가
        current_step_before = state.get('current_step', 0)
        current_step = current_step_before + 1
        max_iterations = state.get('max_iterations', 10)
        
        # 단계 증가 로깅
        logger.info("🔢 STEP INCREMENT 상세 정보:")
        logger.info(f"  - 이전 단계: {current_step_before}")
        logger.info(f"  - 현재 단계: {current_step}")
        logger.info(f"  - 최대 반복: {max_iterations}")
        logger.info(f"  - 제한 확인: {current_step} >= {max_iterations} = {current_step >= max_iterations}")
        
        state['current_step'] = current_step
        
        # MAX_ITERATIONS 체크
        if current_step >= max_iterations:
            logger.info("🔄 MAX_ITERATIONS 도달 - 종합 분석 결과 생성")
            
            # 종합 분석 결과 생성
            final_response = self._generate_comprehensive_final_analysis(state, current_step, max_iterations)
            
            # 강제 종료를 위한 AIMessage 생성 (tool_calls 없음)
            from langchain_core.messages import AIMessage
            final_message = AIMessage(content=final_response)
            
            updated_state = {
                **state,
                'current_step': current_step,
                'messages': state.get('messages', []) + [final_message],
                'max_iterations_reached': True
            }
            
            logger.info("✅ MAX_ITERATIONS 종합 분석 완료")
            return updated_state
        
        # 프롬프트 생성
        prompt_data = self._create_prompt(state, user_query)
        
        # 메시지 준비
        prompt_messages = self._prepare_messages(state, prompt_data)
        
        # 모델 호출
        response = self._invoke_model(prompt_messages, config, state)
        
        # 응답 로깅
        self._log_model_response(response, current_step)
        
        # 상태 업데이트 (ModelNode는 messages와 current_step만 업데이트)
        updated_state = {
            **state,
            "messages": response["messages"],
            "user_query": user_query,
            "current_step": current_step
        }
        
        # State 추적 정보 로깅
        logger.info(f"🤖 MODEL NODE 완료 - Step {current_step}")
        logger.info(f"📊 업데이트된 State의 current_step: {updated_state.get('current_step')}")
        logger.info(f"📊 업데이트된 State의 max_iterations: {updated_state.get('max_iterations')}")
        
        # 메시지 정보 로깅
        last_message = updated_state["messages"][-1] if updated_state["messages"] else None
        if last_message:
            has_tool_calls = hasattr(last_message, 'tool_calls') and last_message.tool_calls
            logger.info(f"📨 마지막 메시지: {type(last_message).__name__}, tool_calls={has_tool_calls}")
        
        return updated_state
    
    def _log_input_state(self, state: AgentState):
        """입력 상태 로깅"""
        logger.info(f"📥 입력 - Index: {state.get('index_id')}, Document: {state.get('document_id')}")
        logger.info(f"📥 입력 - Messages: {len(state.get('messages', []))}개")
        logger.info(f"📥 입력 - Step: {state.get('current_step', 0)}")
        logger.info(f"📥 입력 - Max Iterations: {state.get('max_iterations', 'Not Set')}")
        
        # 분석 이력 로깅
        analysis_history = state.get('analysis_history', [])
        if analysis_history:
            logger.info(f"📊 분석 이력: {len(analysis_history)}개")
            for i, entry in enumerate(analysis_history[-3:], 1):  # 최근 3개만
                tool_name = entry.get('tool_name', 'Unknown')
                success = '✅' if entry.get('success') else '❌'
                logger.info(f"  {i}. {success} {tool_name}")
    
    def _extract_user_query(self, state: AgentState) -> str:
        """사용자 쿼리 추출"""
        user_query = state.get('user_query', '')
        if not user_query:
            # messages에서 추출
            for msg in state.get('messages', []):
                if isinstance(msg, HumanMessage):
                    user_query = self._normalize_content(msg.content)
                    break
        
        logger.info(f"💬 사용자 쿼리: {user_query[:100]}...")
        return user_query
    
    def _create_prompt(self, state: AgentState, user_query: str) -> Dict[str, str]:
        """프롬프트 생성"""
        # State에서 현재 단계 및 분석 컨텍스트 정보 수집
        current_step = state.get('current_step', 0)
        combined_context = state.get('combined_analysis_context', '')
        previous_context = state.get('previous_analysis_context', '')
        analysis_history = state.get('analysis_history', [])
        index_id = state.get('index_id', 'unknown')
        
        # 새로 추가: 참조 정보 및 도구 컨텐츠 수집
        tool_references = state.get('tool_references', [])
        tool_content = state.get('tool_content', '')
        
        # 디버깅 로그
        logger.info(f"🔍 _create_prompt 디버깅:")
        logger.info(f"  - current_step: {current_step}")
        logger.info(f"  - combined_context 길이: {len(combined_context)}")
        logger.info(f"  - previous_context 길이: {len(previous_context)}")
        logger.info(f"  - analysis_history 개수: {len(analysis_history)}")
        logger.info(f"  - tool_references 개수: {len(tool_references)}")
        logger.info(f"  - tool_content 길이: {len(tool_content)}")
        
        # combined_context 설정 (ToolNode에서 업데이트된 결과 사용)
        if not combined_context or combined_context.strip() == "":
            combined_context = "이전 분석 결과 없음"
        
        # 참조 정보를 문자열로 변환
        references_text = ""
        if tool_references:
            ref_lines = []
            for i, ref in enumerate(tool_references, 1):
                title = ref.get('title', f'참조 {i}')
                value = ref.get('value', '')
                ref_lines.append(f"[{i}] {title}: {value}")
            references_text = "\n".join(ref_lines)
            logger.info(f"📋 참조 정보 생성: {len(references_text)}자, {len(tool_references)}개 항목")
        
        # 도구 컨텐츠가 있으면 combined_context에 추가
        if tool_content and tool_content.strip():
            if combined_context and combined_context != "이전 분석 결과 없음":
                combined_context = f"{combined_context}\n\n=== 최근 도구 실행 결과 ===\n{tool_content}"
            else:
                combined_context = f"=== 최근 도구 실행 결과 ===\n{tool_content}"
            logger.info(f"📝 도구 컨텐츠를 combined_context에 추가: {len(tool_content)}자")
        
        # 최종 분석 내용 로깅
        if combined_context:
            logger.info(f"📋 최종 PREVIOUS_ANALYSIS 길이: {len(combined_context)}")
            logger.info(f"📋 PREVIOUS_ANALYSIS 미리보기: {combined_context[:300]}...")
        else:
            logger.info("📋 PREVIOUS_ANALYSIS가 비어있음")
        
        prompt_data = prompt_manager.get_prompt(
            "agent_profile", 
            DATETIME=datetime.now(tz=timezone.utc).isoformat(),
            INDEX_ID=index_id,
            QUERY=user_query,
            PREVIOUS_ANALYSIS=combined_context if combined_context else "이전 분석 결과 없음",
            REFERENCES=references_text if references_text else "참조 정보 없음",
            MEDIA_TYPE=state.get('media_type', 'DOCUMENT')
        )
        
        logger.info(f">>>>>>>>> PROMPT 생성 (단계 {current_step}) >>>>>>>>>")
        logger.info(f"System Prompt 길이: {len(prompt_data.get('system_prompt', ''))}")
        logger.info(f"Instruction 길이: {len(prompt_data.get('instruction', ''))}")
        logger.info(f"전체 프롬프트 내용:")
        logger.info(prompt_data)
        logger.info(f"<<<<<<<<< PROMPT 완료 (단계 {current_step}) <<<<<<<<<<<")

        logger.info(f"📝 프롬프트 생성 완료")
        logger.info(f"  - 시스템 프롬프트: {len(prompt_data['system_prompt'])} 문자")
        logger.info(f"  - 인스트럭션: {len(prompt_data.get('instruction', ''))} 문자")
        logger.info(f"  - 분석 컨텍스트: {len(combined_context)} 문자")
        
        # 분석 컨텍스트 내용 요약 로깅 (개발용)
        if combined_context:
            preview = combined_context[:200] + "..." if len(combined_context) > 200 else combined_context
            logger.info(f"📋 분석 컨텍스트 미리보기: {preview}")
        
        return prompt_data
    
    def _prepare_messages(self, state: AgentState, prompt_data: Dict[str, str]) -> list:
        """메시지 준비"""
        messages = state.get('messages', [])
        non_system_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
        
        prompt_messages = [
            SystemMessage(content=prompt_data["system_prompt"])
        ]
        
        if "instruction" in prompt_data:
            prompt_messages.append(HumanMessage(content=prompt_data["instruction"]))
        
        prompt_messages.extend(non_system_messages)
        
        logger.info(f"📨 메시지 준비 완료: {len(prompt_messages)}개")
        return prompt_messages
    
    def _invoke_model(self, prompt_messages: list, config, state: 'AgentState' = None) -> Dict[str, Any]:
        """모델 호출 - 순수 LLM 호출만 담당"""
        current_step = state.get('current_step', 0) if state else 0
        logger.info(f"🔄 AI 모델 호출 시작 (단계 {current_step})...")
        
        # 도구를 바인딩한 모델 생성
        model_with_tools = self.model.bind_tools(self.tools)
        
        # 직접 LLM 호출
        response_message = model_with_tools.invoke(prompt_messages)
        
        logger.info(f"✅ AI 모델 응답 완료")
        
        # 응답 메시지 확인
        if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
            tool_names = [tc.get('name', 'Unknown') for tc in response_message.tool_calls]
            logger.info(f"🛠️ 도구 호출 예정: {tool_names}")
        else:
            logger.info("💬 최종 응답 생성 (도구 호출 없음)")
        
        # 기존 메시지에 새 응답 추가
        updated_messages = state.get('messages', []) + [response_message]
        
        # 응답 구조 생성 (기존 messages를 모두 포함)
        response = {
            "messages": updated_messages
        }
        
        return response
    
    def _log_model_response(self, response: Dict[str, Any], current_step: int):
        """모델 응답 로깅"""
        messages = response.get("messages", [])
        logger.info(f"📤 모델 응답 완료: {len(messages)}개 메시지")
        
        # 마지막 AI 메시지 내용 로깅
        ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
        if ai_messages:
            last_ai_msg = ai_messages[-1]
            content_preview = str(last_ai_msg.content)[:200] + "..." if len(str(last_ai_msg.content)) > 200 else str(last_ai_msg.content)
            logger.info(f"🤖 AI 응답: {content_preview}")
            
            # Tool calls 확인
            if hasattr(last_ai_msg, 'tool_calls') and last_ai_msg.tool_calls:
                tool_names = [tc.get('name', 'Unknown') for tc in last_ai_msg.tool_calls]
                logger.info(f"🛠️ 도구 호출 예정: {tool_names}")
    
    def _normalize_content(self, content: Any) -> str:
        """메시지 내용 정규화"""
        if content is None:
            return ""
        
        if isinstance(content, list):
            return "".join(str(item) for item in content)
        
        return str(content)
    
    def _generate_comprehensive_final_analysis(self, state: AgentState, current_step: int, max_iterations: int) -> str:
        """종합적인 최종 분석 결과 생성"""
        logger.info("📝 종합 분석 결과 생성 시작")
        
        # 기본 정보 수집
        index_id = state.get('index_id', 'Unknown')
        document_id = state.get('document_id', 'Unknown')
        user_query = state.get('user_query', '')
        
        # 분석 히스토리와 컨텍스트 수집
        analysis_history = state.get('analysis_history', [])
        combined_context = state.get('combined_analysis_context', '')
        
        # 사용된 도구들 요약
        tools_used = []
        successful_analyses = []
        
        for entry in analysis_history:
            tool_name = entry.get('tool_name', 'Unknown')
            success = entry.get('success', False)
            result = entry.get('result', '')
            
            if tool_name not in tools_used:
                tools_used.append(tool_name)
            
            if success and result:
                successful_analyses.append({
                    'tool': tool_name,
                    'result': result[:500] + "..." if len(result) > 500 else result
                })
        
        # 최종 분석 결과 구성
        final_analysis = f"""# 문서 분석 완료 보고서

## 🔍 분석 개요
- **프로젝트 ID**: {index_id}
- **문서 ID**: {document_id}
- **분석 요청**: {user_query[:200]}{"..." if len(user_query) > 200 else ""}
- **실행 단계**: {current_step}/{max_iterations}
- **상태**: 최대 반복 횟수 도달로 인한 분석 완료

## 🛠️ 사용된 분석 도구
"""
        
        if tools_used:
            for tool in tools_used:
                final_analysis += f"- {tool}\n"
        else:
            final_analysis += "- 사용된 도구 없음\n"
        
        final_analysis += f"""
## 📊 분석 결과 요약

### 성공적으로 완료된 분석 ({len(successful_analyses)}건)
"""
        
        if successful_analyses:
            for i, analysis in enumerate(successful_analyses, 1):
                final_analysis += f"""
#### {i}. {analysis['tool']} 분석 결과
{analysis['result']}
"""
        else:
            final_analysis += "- 완료된 분석 결과 없음\n"
        
        # 종합 분석 컨텍스트가 있는 경우 포함
        if combined_context and combined_context.strip():
            final_analysis += f"""
## 🔗 종합 분석 내용
{combined_context[:1000]}{"..." if len(combined_context) > 1000 else ""}
"""
        
        final_analysis += f"""
## ⚠️ 분석 완료 사유
최대 반복 횟수({max_iterations})에 도달하여 분석을 완료했습니다. 
위의 결과는 {current_step}단계에 걸쳐 수집된 모든 분석 정보를 종합한 것입니다.

---
*분석 완료 시간: {datetime.now(tz=timezone.utc).isoformat()}*
"""
        
        logger.info(f"📝 종합 분석 결과 생성 완료 - 길이: {len(final_analysis)} 문자")
        logger.info(f"📝 포함된 분석 결과: {len(successful_analyses)}건")
        logger.info(f"📝 사용된 도구: {len(tools_used)}개")
        
        return final_analysis
