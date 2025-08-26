"""
LangGraph Tool Node - 도구 실행 담당
"""

import logging
import time
import os
import sys
from typing import Dict, Any, List, Optional
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, AIMessage
from langgraph.prebuilt import ToolNode as BaseToolNode

# Common module imports
sys.path.append('/opt/python')
from common import OpenSearchService

from agent.state.agent_state import AgentState
from agent.tools.state_aware_base import StateAwareBaseTool

logger = logging.getLogger(__name__)

BEDROCK_AGENT_MODEL_ID = os.environ.get('BEDROCK_AGENT_MODEL_ID')

def _update_combined_analysis_context(state: AgentState, analysis_history: List[Dict[str, Any]]) -> str:
    """
    이전 분석 내용과 현재 세션 분석 이력을 결합해서 combined_analysis_context 생성
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
    
    logger.info(f"📊 결합 컨텍스트 업데이트 완료: {len(combined_context)} 문자")
    
    return combined_context


class ToolNode:
    """
    LangGraph Tool Node - 도구 실행을 담당하는 노드
    StateAware 도구와 일반 도구를 모두 지원, OpenSearch 저장 포함
    """
    
    def __init__(self, tools: List[BaseTool]):
        """
        Args:
            tools: 사용 가능한 도구 리스트
        """
        self.tools = {tool.name: tool for tool in tools}
        self.base_tool_node = BaseToolNode(tools)
        logger.info(f"🔧 ToolNode 초기화 완료 - 도구: {len(tools)}개")
        
        # OpenSearch 서비스 초기화
        self.opensearch_service = None
        self.enable_opensearch = True
        
        try:
            opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
            if opensearch_endpoint:
                self.opensearch_service = OpenSearchService(
                    endpoint=opensearch_endpoint,
                    index_name=os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis'),
                    region=os.environ.get('OPENSEARCH_REGION') or os.environ.get('AWS_REGION', 'us-west-2')
                )
                logger.info("✅ ToolNode OpenSearch 서비스 초기화 완료")
            else:
                logger.warning("❌ OPENSEARCH_ENDPOINT 환경 변수가 설정되지 않음")
                self.enable_opensearch = False
        except Exception as e:
            logger.warning(f"❌ ToolNode OpenSearch 서비스 초기화 실패: {str(e)}")
            self.enable_opensearch = False
        
        # StateAware 도구 목록 로깅
        state_aware_tools = [name for name, tool in self.tools.items() 
                           if isinstance(tool, StateAwareBaseTool)]
        if state_aware_tools:
            logger.info(f"📊 StateAware 도구: {state_aware_tools}")
    
    def __call__(self, state: AgentState) -> AgentState:
        """
        도구 노드 실행
        
        Args:
            state: LangGraph AgentState
            
        Returns:
            업데이트된 AgentState
        """
        logger.info("=== 🔧 TOOL NODE 실행 ===")
        
        # StateAware 도구들에 현재 상태 설정
        for tool_name, tool in self.tools.items():
            if isinstance(tool, StateAwareBaseTool):
                object.__setattr__(tool, '_current_state', state)
        
        # 입력 상태 로깅
        self._log_input_state(state)
        
        # Tool calls 추출
        tool_calls = self._extract_tool_calls(state)
        if not tool_calls:
            logger.warning("❌ 실행할 도구 호출이 없음")
            return state
        
        # 도구 실행
        tool_messages, tools_used, tool_results, analysis_history = self._execute_tools(state, tool_calls)
        
        # 참조와 컨텐츠 추출
        tool_references, tool_content = self._extract_references_and_content(tool_results)
        
        # 분석 이력 및 컨텍스트 업데이트
        combined_analysis_context = _update_combined_analysis_context(state, analysis_history)
        
        # 실행 결과 로깅
        self._log_execution_results(tool_messages, tools_used, analysis_history)
        
        # 상태 업데이트 (ToolNode는 tool_results, tools_used, analysis_history, combined_analysis_context 담당)
        messages = state.get("messages", [])
        updated_state = {
            **state,
            "messages": messages + tool_messages,
            "tools_used": tools_used,
            "tool_results": tool_results,
            "tool_references": tool_references,  # 새로 추가
            "tool_content": tool_content,  # 새로 추가
            "analysis_history": analysis_history,
            "combined_analysis_context": combined_analysis_context
        }
        
        logger.info(f"🔧 TOOL NODE 완료 - {len(tool_messages)}개 도구 실행")
        return updated_state
    
    def _log_input_state(self, state: AgentState):
        """입력 상태 로깅"""
        messages = state.get("messages", [])
        logger.info(f"📥 입력 - Messages: {len(messages)}개")
        logger.info(f"📥 입력 - 기존 분석 이력: {len(state.get('analysis_history', []))}개")
    
    def _extract_tool_calls(self, state: AgentState) -> List[Dict[str, Any]]:
        """Tool calls 추출"""
        messages = state.get("messages", [])
        if not messages:
            return []
            
        last_message = messages[-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return []
        
        tool_calls = last_message.tool_calls
        logger.info(f"🛠️ 실행할 도구: {[tc['name'] for tc in tool_calls]}")
        return tool_calls
    
    def _execute_tools(self, state: AgentState, tool_calls: List[Dict[str, Any]]) -> tuple:
        """도구들을 실행하고 결과 반환"""
        tool_messages = []
        tools_used = state.get("tools_used", []).copy()
        tool_results = state.get("tool_results", []).copy()
        analysis_history = state.get("analysis_history", []).copy()
        
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            logger.info(f"⚡ 도구 실행 시작: {tool_name}")
            logger.info(f"📋 입력 인자: {self._format_args_for_log(tool_args)}")
            
            # 도구 실행
            tool_message, success, result_data = self._execute_single_tool(
                state, tool_name, tool_args, tool_call_id
            )
            
            tool_messages.append(tool_message)
            
            # 도구 사용 추적
            if tool_name not in tools_used:
                tools_used.append(tool_name)
            
            # 결과 저장 (성공한 경우만)
            if success and result_data:
                # tool_results 업데이트
                tool_result_entry = {
                    "tool_name": tool_name,
                    "success": success,
                    "message": tool_message.content,
                    "data": result_data,
                    "execution_time": result_data.get('execution_time', 0),
                    "timestamp": time.time()
                }
                tool_results.append(tool_result_entry)
                
                # analysis_history 업데이트
                analysis_entry = {
                    "tool_name": tool_name,
                    "content": tool_message.content,
                    "success": success,
                    "timestamp": time.time(),
                    "execution_time": result_data.get('execution_time', 0),
                    "step": state.get("current_step", 0)
                }
                analysis_history.append(analysis_entry)
                
                # OpenSearch에 결과 저장 (성공한 경우만)
                if self.enable_opensearch and self.opensearch_service and success:
                    try:
                        self._save_to_opensearch(state, tool_name, tool_message.content, result_data, tool_args)
                        logger.info(f"💾 {tool_name} OpenSearch 저장 완료")
                    except Exception as e:
                        logger.error(f"❌ {tool_name} OpenSearch 저장 실패: {str(e)}")
                elif success:
                    if not self.enable_opensearch:
                        logger.info(f"⚠️ {tool_name} OpenSearch 비활성화로 저장 건너뜀")
                    elif not self.opensearch_service:
                        logger.info(f"⚠️ {tool_name} OpenSearch 서비스 없음으로 저장 건너뜀")
                    else:
                        logger.info(f"⚠️ {tool_name} 조건 불만족으로 OpenSearch 저장 건너뜀")
                
                logger.info(f"✅ {tool_name} 실행 완료 - 이력에 추가됨")
            else:
                logger.error(f"❌ {tool_name} 실행 실패")
        
        return tool_messages, tools_used, tool_results, analysis_history
    
    def _execute_single_tool(self, state: AgentState, tool_name: str, tool_args: Dict[str, Any], tool_call_id: str) -> tuple:
        """단일 도구 실행"""
        tool = self.tools.get(tool_name)
        if not tool:
            error_msg = f"Unknown tool: {tool_name}"
            logger.error(error_msg)
            return ToolMessage(content=error_msg, tool_call_id=tool_call_id), False, None
        
        try:
            start_time = time.time()
            
            # StateAware 도구 처리
            if isinstance(tool, StateAwareBaseTool):
                logger.info(f"📊 StateAware 도구 실행: {tool_name}")
                result = tool.execute_with_state(state, **tool_args)
                
                tool_message = ToolMessage(
                    content=result.message,
                    tool_call_id=tool_call_id
                )
                
                result_data = {
                    'execution_time': time.time() - start_time,
                    'data': result.data
                }
                
                return tool_message, result.success, result_data
            
            else:
                # 일반 도구 처리
                logger.info(f"🔧 일반 도구 실행: {tool_name}")
                
                # 기본 ToolNode 사용
                temp_last_message = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": tool_name,
                        "args": tool_args,
                        "id": tool_call_id
                    }]
                )
                temp_state = {
                    **state,
                    "messages": state.get("messages", [])[:-1] + [temp_last_message]
                }
                
                temp_result = self.base_tool_node(temp_state)
                
                # 결과 추출
                if temp_result.get("messages"):
                    new_messages = temp_result["messages"]
                    if new_messages and isinstance(new_messages[-1], ToolMessage):
                        tool_message = new_messages[-1]
                        return tool_message, True, {'execution_time': time.time() - start_time}
                
                # 폴백
                return ToolMessage(content="Tool execution completed", tool_call_id=tool_call_id), True, {'execution_time': time.time() - start_time}
                
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"❌ {tool_name} 실행 중 오류: {str(e)}")
            
            return ToolMessage(content=error_msg, tool_call_id=tool_call_id), False, None
    
    def _format_args_for_log(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """로깅용 인자 포맷팅 (긴 값들 요약)"""
        formatted = {}
        for key, value in args.items():
            if key.startswith('_'):
                formatted[key] = "[Agent Context]"
            elif isinstance(value, str) and len(value) > 100:
                formatted[key] = f"{value[:100]}... ({len(value)} 문자)"
            elif isinstance(value, list) and len(value) > 5:
                formatted[key] = f"[리스트: {len(value)}개 항목]"
            else:
                formatted[key] = value
        return formatted
    
    def _log_execution_results(self, tool_messages: List[ToolMessage], tools_used: List[str], analysis_history: List[Dict[str, Any]]):
        """실행 결과 로깅"""
        logger.info(f"📤 실행 완료 - 메시지: {len(tool_messages)}개")
        logger.info(f"📤 실행 완료 - 사용된 도구: {tools_used}")
        logger.info(f"📤 실행 완료 - 총 분석 이력: {len(analysis_history)}개")
        
        # 각 도구 결과 요약 로깅
        for i, msg in enumerate(tool_messages, 1):
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            logger.info(f"  {i}. 결과: {content_preview}")
    
    def _save_to_opensearch(self, state: AgentState, tool_name: str, content: str, 
                           result_data: Dict[str, Any], tool_args: Dict[str, Any]) -> None:
        """
        도구 결과를 OpenSearch에 segment-unit 방식으로 저장
        
        Args:
            state: LangGraph State
            tool_name: 도구 이름
            content: 도구 실행 결과 내용
            result_data: 도구 실행 결과 데이터
            tool_args: 도구 실행 인자
        """
        try:
            # State에서 기본 정보 추출
            index_id = state.get('index_id')
            document_id = state.get('document_id')
            segment_id = state.get('segment_id')
            segment_index = state.get('segment_index', 0)
            file_path = state.get('file_path', '')
            
            if not document_id:
                # 기본값으로 생성
                timestamp_ms = int(time.time() * 1000)
                tmp_doc_id = file_path.split("/")[-1].replace(".pdf", "") if file_path else "unknown"
                document_id = f"tool_{tmp_doc_id}_{timestamp_ms}"
                logger.warning(f"document_id가 State에 없어 기본값 사용: {document_id}")
            
            if not segment_id:
                # 기본값으로 생성
                segment_id = f"segment_{document_id}_{segment_index}"
                logger.warning(f"segment_id가 State에 없어 기본값 사용: {segment_id}")
            
            # 실제 사용된 query 추출
            analysis_query = None
            
            # result_data에서 query 추출 시도
            if result_data and result_data.get('data'):
                data = result_data['data']
                if isinstance(data, dict):
                    analysis_query = data.get('analysis_query')
                    model_version = data.get('model_version')
                    analysis_type = data.get('analysis_type')

            # 분석 단계 결정
            existing_analysis = state.get('analysis_history', [])
            analysis_steps = str(len(existing_analysis) + 1)
            
            # analysis_type이 'skip'인 경우 저장 생략
            if analysis_type == 'skip':
                logger.info("⏭️ analysis_type=skip - OpenSearch 저장 생략")
                return

            # Segment-unit 방식으로 ai_analysis 도구 추가
            success = self.opensearch_service.add_ai_analysis_tool(
                index_id=index_id,
                segment_id=segment_id,
                document_id=document_id,
                segment_index=segment_index,
                analysis_query=analysis_query,
                content=content,
                analysis_steps=analysis_steps,
                model_version=model_version,
                analysis_type=analysis_type,    
                media_type=state.get('media_type', 'DOCUMENT')
            )
            
            if success:
                logger.info(f"✅ OpenSearch segment-unit 저장 완료: {tool_name}")
                logger.info(f"📊 저장된 데이터: segment_id={segment_id}, query={analysis_query[:50]}...")
            else:
                logger.error(f"❌ OpenSearch segment-unit 저장 실패: {tool_name}")
            
        except Exception as e:
            logger.error(f"❌ OpenSearch 저장 실패 ({tool_name}): {str(e)}")
            # OpenSearch 저장 실패는 전체 프로세스를 중단하지 않음
            pass
    
    def _extract_references_and_content(self, tool_results: List[Dict[str, Any]]) -> tuple:
        """도구 실행 결과에서 references와 content 추출"""
        extracted_references = []
        extracted_content_parts = []
        
        logger.info(f"🔍 참조 및 컨텐츠 추출 시작 - {len(tool_results)}개 결과")
        
        for tool_result in tool_results:
            try:
                tool_name = tool_result.get("tool_name", "unknown")
                data = tool_result.get("data", {})
                
                # data가 딕셔너리이고 success가 True인 경우에만 처리
                if isinstance(data, dict) and data.get("success"):
                    result_data = data.get("data", {})
                    
                    # 1. references 추출
                    if "references" in result_data:
                        references = result_data["references"]
                        if isinstance(references, list):
                            for ref in references:
                                if isinstance(ref, str):
                                    # 문자열 형태의 reference를 구조화된 형태로 변환
                                    ref_dict = {
                                        "type": "document",
                                        "title": ref,
                                        "value": ref,
                                        "metadata": {"tool": tool_name, "source": "tool_execution"}
                                    }
                                    extracted_references.append(ref_dict)
                                elif isinstance(ref, dict):
                                    # 이미 구조화된 reference
                                    ref["metadata"] = ref.get("metadata", {})
                                    ref["metadata"]["tool"] = tool_name
                                    ref["metadata"]["source"] = "tool_execution"
                                    extracted_references.append(ref)
                            
                            logger.info(f"📋 {tool_name}에서 {len(references)}개 참조 추출")
                    
                    # 2. content 추출
                    if "content" in result_data:
                        content = result_data["content"]
                        if isinstance(content, list):
                            # content가 리스트인 경우 각 항목을 문자열로 변환하여 추가
                            for item in content:
                                if item:  # 빈 값이 아닌 경우에만
                                    extracted_content_parts.append(str(item))
                        elif isinstance(content, str) and content.strip():
                            # content가 문자열이고 빈 값이 아닌 경우
                            extracted_content_parts.append(content)
                        
                        logger.info(f"📝 {tool_name}에서 컨텐츠 추출: {len(str(content))}자")
                
            except Exception as e:
                logger.error(f"❌ {tool_result.get('tool_name', 'unknown')} 결과 처리 실패: {str(e)}")
        
        # 결합된 컨텐츠 생성
        combined_content = "\n\n".join(extracted_content_parts) if extracted_content_parts else ""
        
        logger.info(f"✅ 추출 완료 - 참조: {len(extracted_references)}개, 컨텐츠: {len(combined_content)}자")
        
        return extracted_references, combined_content