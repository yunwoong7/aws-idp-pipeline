"""
Refactored AnalysisAgent - Optimized for LangGraph structure
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

# Common module imports
import sys
import os
sys.path.append('/opt/python')
from common import OpenSearchService
from common.dynamodb_service import DynamoDBService

from agent.llm import get_llm
from agent.state.agent_state import AgentState
from agent.graph.builder import create_analysis_graph

logger = logging.getLogger(__name__)


class AnalysisAgent:
    """
    LangGraph-based analysis agent
    """
    
    def __init__(self, 
                 index_id: str = None,
                 document_id: str = None,
                 segment_id: str = None,
                 segment_index: int = None,
                 image_uri: str = None,
                 file_path: str = None,
                 model_id: str = None,
                 max_tokens: int = 8192,
                 thread_id: str = None,
                 segment_type: str = None,
                 start_timecode_smpte: str = None,
                 end_timecode_smpte: str = None,
                 media_type: str = None):
        
        logger.info("🚀 AnalysisAgent initialization started")
        
        # Set basic information
        self.index_id = index_id
        self.document_id = document_id
        self.segment_id = segment_id
        self.segment_index = segment_index
        self.image_uri = image_uri
        self.file_path = file_path
        
        # 동영상 챕터 정보 (VideoAnalyzerTool용)
        self.segment_type = segment_type
        self.start_timecode_smpte = start_timecode_smpte
        self.end_timecode_smpte = end_timecode_smpte
        
        # 문서 타입 정보
        self.media_type = media_type or 'DOCUMENT'
        
        # Set thread_id for conversation continuity
        self.thread_id = thread_id or f"document_{document_id}_default"
        logger.info(f"🔄 Thread ID set to: {self.thread_id}")
        
        # Initialize LLM model
        self.model = get_llm(model_id=model_id, max_tokens=max_tokens)
        
        # Initialize OpenSearch service (for previous analysis lookup)
        self.opensearch_service = self._init_opensearch()
        
        # Initialize DynamoDB service (for updating segments table)
        self.dynamodb_service = self._init_dynamodb()
        
        # Create LangGraph
        self.graph = create_analysis_graph(self.model)
        
        logger.info(f"✅ AnalysisAgent initialization completed")
        logger.info(f"📁 Document: {document_id}, Segment: {segment_index}")

    
    def _init_opensearch(self):
        """Initialize OpenSearch service"""
        opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
        if not opensearch_endpoint:
            logger.warning("⚠️ OpenSearch endpoint is not set")
            return None
        
        try:
            service = OpenSearchService(
                endpoint=opensearch_endpoint,
                index_name=os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis'),
                region=os.environ.get('OPENSEARCH_REGION') or os.environ.get('AWS_REGION', 'us-west-2')
            )
            logger.info("✅ OpenSearch service initialization completed")
            return service
        except Exception as e:
            logger.warning(f"❌ OpenSearch initialization failed: {str(e)}")
            return None
    
    def _init_dynamodb(self):
        """Initialize DynamoDB service"""
        try:
            service = DynamoDBService(region=os.environ.get('AWS_REGION', 'us-west-2'))
            logger.info("✅ DynamoDB service initialization completed")
            return service
        except Exception as e:
            logger.warning(f"❌ DynamoDB initialization failed: {str(e)}")
            return None
    
    def analyze_document(self, user_query: str = None, analysis_type: str = "comprehensive") -> Dict[str, Any]:
        """
        Execute document analysis
        
        Args:
            user_query: User query
            analysis_type: Analysis type
            
        Returns:
            Analysis result
        """
        logger.info("-" * 50)
        logger.info("🎯 Document analysis started")
        logger.info("-" * 50)
        logger.info(f"💬 Analysis query: {user_query}")
        logger.info(f"📋 Analysis type: {analysis_type}")
        
        start_time = time.time()
        
        try:
            # 1. Get previous analysis context
            previous_analysis_context = self._get_previous_analysis()
            
            # 2. Create initial state
            initial_state = self._create_initial_state(user_query, previous_analysis_context)
            
            # 3. Create execution configuration
            config = self._create_config()
            
            # 4. Execute graph
            logger.info("🚀 _execute_graph 호출 시작")
            final_state = self._execute_graph(initial_state, config)
            logger.info("✅ _execute_graph 완료")
            
            # 5. Process results
            logger.info("🚀 _process_results 호출 시작")
            result = self._process_results(final_state, start_time)
            logger.info("✅ _process_results 완료")
            
            logger.info("-" * 50)
            logger.info("🎉 Document analysis completed")
            logger.info("-" * 50)
            
            return result
            
        except Exception as e:
            error_msg = f"Document analysis execution failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            import traceback
            logger.error(f"❌ 예외 상세: {traceback.format_exc()}")
            
            return {
                'success': False,
                'error': str(e),
                'document_id': self.document_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    def _get_previous_analysis(self) -> str:
        """Get previous analysis context"""
        if not self.opensearch_service:
            logger.info("📋 OpenSearch disabled - no previous analysis")
            return "**Previous analysis context**: OpenSearch disabled"
        
        try:
            logger.info("1. Get previous analysis context")
            
            filters = {
                "document_id": self.document_id,
                "segment_id": self.segment_id
            }
            
            response = self.opensearch_service.search_text(
                index_id=self.index_id,
                query="*",
                size=100,
                filters=filters
            )
            
            hits = response.get('hits', {}).get('hits', [])
            
            if not hits:
                logger.info("📋 No previous analysis results")
                return "**Previous analysis context**: No previous analysis results"
            
            # Construct analysis content
            context_parts = [f"**Previous analysis context** ({len(hits)} results):"]
            
            for i, hit in enumerate(hits, 1):
                source = hit.get('_source', {})
                
                # Extract actual content from new segment-unit structure
                content = self._extract_content_from_source(source)
                tool_name = self._extract_tool_name_from_source(source)
                created_at = source.get('created_at', '')
                
                if content and content.strip():
                    # If content is too long, summarize (use environment variable)
                    max_chars = int(os.environ.get('PREVIOUS_ANALYSIS_MAX_CHARACTERS', '100000'))
                    if len(content) > max_chars:
                        content_preview = content[:max_chars] + "...[summarized]"
                    else:
                        content_preview = content
                    
                    context_parts.append(f"\n{i}. **{tool_name}** ({created_at})")
                    context_parts.append(f"   {content_preview}")
            
            result = "\n".join(context_parts)
            logger.info(f"✅ Previous analysis context lookup completed: {len(result)} characters")
            
            # Previous analysis context preview
            logger.info(f"📋 Previous analysis context preview:\n{result}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Previous analysis context lookup failed: {str(e)}")
            return f"**Previous analysis context**: Lookup failed ({str(e)})"
    
    def _extract_content_from_source(self, source: Dict[str, Any]) -> str:
        """Extract actual analysis content from OpenSearch source"""
        content_parts = []
        
        # 1. content_combined field (highest priority)
        content_combined = source.get('content_combined', '')
        if content_combined and content_combined.strip():
            content_parts.append(content_combined)
        
        # 2. Extract content from tools structure
        tools = source.get('tools', {})
        
        # bda_indexer tool content
        bda_tools = tools.get('bda_indexer', [])
        for bda_tool in bda_tools:
            if isinstance(bda_tool, dict):
                bda_content = bda_tool.get('content', '')
                if bda_content and bda_content.strip():
                    content_parts.append(f"[BDA 분석] {bda_content}")
        
        # pdf_text_extractor tool content
        pdf_tools = tools.get('pdf_text_extractor', [])
        for pdf_tool in pdf_tools:
            if isinstance(pdf_tool, dict):
                pdf_content = pdf_tool.get('content', '')
                if pdf_content and pdf_content.strip():
                    content_parts.append(f"[PDF 텍스트] {pdf_content}")
        
        # image_analysis tool content
        img_tools = tools.get('image_analysis', [])
        for img_tool in img_tools:
            if isinstance(img_tool, dict):
                img_content = img_tool.get('content', '')
                if img_content and img_content.strip():
                    content_parts.append(f"[이미지 분석] {img_content}")
        
        # 3. Legacy content field (fallback)
        legacy_content = source.get('content', '')
        if legacy_content and legacy_content.strip() and not content_parts:
            content_parts.append(legacy_content)
        
        return '\n\n'.join(content_parts) if content_parts else ''
    
    def _extract_tool_name_from_source(self, source: Dict[str, Any]) -> str:
        """Extract tool name from OpenSearch source"""
        # 1. Legacy tool_name field
        tool_name = source.get('tool_name', '')
        if tool_name and tool_name != 'unknown':
            return tool_name
        
        # 2. Check active tools in tools structure
        tools = source.get('tools', {})
        active_tools = []
        
        if tools.get('bda_indexer') and len(tools['bda_indexer']) > 0:
            active_tools.append('bda_indexer')
        if tools.get('pdf_text_extractor') and len(tools['pdf_text_extractor']) > 0:
            active_tools.append('pdf_text_extractor')
        if tools.get('image_analysis') and len(tools['image_analysis']) > 0:
            active_tools.append('image_analysis')
        
        if active_tools:
            return '+'.join(active_tools)
        
        # 3. If content_combined exists, return combined_analysis
        if source.get('content_combined'):
            return 'combined_analysis'
        
        return 'unknown'
    
    def _create_initial_state(self, user_query: str, previous_analysis_context: str) -> AgentState:
        """Create initial AgentState"""
        logger.info("🔧 Creating initial state...")
        
        # Get max_iterations from environment variable
        max_iterations = int(os.environ.get('MAX_ITERATIONS', '10'))
        logger.info(f"🔢 Max iterations set to: {max_iterations}")
        
        initial_state: AgentState = {
            "messages": [HumanMessage(content=user_query)],
            "index_id": self.index_id,
            "document_id": self.document_id,
            "segment_id": self.segment_id,
            "segment_index": self.segment_index,
            "file_path": self.file_path,
            "file_uri": self.file_path,  # VideoAnalyzerTool용 별칭
            "image_path": self.image_uri,
            "session_id": f"session_{int(time.time())}",
            "thread_id": f"thread_{int(time.time())}",
            "user_query": user_query,
            "previous_analysis_context": previous_analysis_context,
            "current_step": 0,
            "max_iterations": max_iterations,
            "tools_used": [],
            "tool_results": [],
            "tool_references": [],  # 새로 추가된 필드
            "tool_content": "",  # 새로 추가된 필드
            "analysis_history": [],
            "combined_analysis_context": previous_analysis_context,  # initial value
            "skip_opensearch_query": True,  # already queried, skip
            "enable_opensearch": bool(self.opensearch_service),
            "segment_type": self.segment_type,
            "start_timecode_smpte": self.start_timecode_smpte,
            "end_timecode_smpte": self.end_timecode_smpte,
            "media_type": self.media_type
        }
        
        logger.info("✅ Initial state created")
        return initial_state
    
    def _create_config(self) -> RunnableConfig:
        """Create execution configuration"""
        # Get max_iterations from environment variable
        max_iterations = int(os.environ.get('MAX_ITERATIONS', '10'))
        
        # Use the stored thread_id for conversation continuity
        logger.info(f"🔄 Using stored thread_id: {self.thread_id}")
        
        return RunnableConfig(
            configurable={
                "thread_id": self.thread_id,
                "max_iterations": max_iterations
            }
        )
    
    def _execute_graph(self, initial_state: AgentState, config: RunnableConfig) -> AgentState:
        """Execute graph"""
        logger.info("⚡ LangGraph execution started...")
        
        try:
            # Monitor progress with streaming execution
            final_state = None
            step_count = 0
            
            for chunk in self.graph.stream(initial_state, config):
                step_count += 1
                
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    node_name, node_output = chunk
                    logger.info(f"🔄 Step {step_count}: {node_name} executed")
                    
                    if isinstance(node_output, dict):
                        final_state = node_output
                elif isinstance(chunk, dict):
                    final_state = chunk
            
            if final_state is None:
                logger.warning("⚠️ Graph execution completed but final_state is None")
                # Try fallback with invoke
                final_state = self.graph.invoke(initial_state, config)
            
            logger.info(f"✅ LangGraph execution completed - total {step_count} steps")
            return final_state
            
        except Exception as e:
            logger.error(f"❌ Graph execution error: {str(e)}")
            import traceback
            logger.error(f"❌ Graph execution traceback: {traceback.format_exc()}")
            
            # Try fallback with invoke
            try:
                logger.info("🔄 Fallback: invoke mode retry")
                final_state = self.graph.invoke(initial_state, config)
                logger.info("✅ Fallback invoke 성공")
                return final_state
            except Exception as fallback_error:
                logger.error(f"❌ Fallback invoke도 실패: {str(fallback_error)}")
                logger.error(f"❌ Fallback traceback: {traceback.format_exc()}")
                raise e  # 원래 에러를 다시 발생시킴
    
    def _process_results(self, final_state: AgentState, start_time: float) -> Dict[str, Any]:
        """Process and return results"""
        logger.info("🔄 _process_results 함수 호출됨")
        execution_time = time.time() - start_time
        
        # Extract information from state
        tools_used = final_state.get('tools_used', [])
        tool_results = final_state.get('tool_results', [])
        analysis_history = final_state.get('analysis_history', [])
        steps_count = final_state.get('current_step', 0)
        
        # 디버깅: final_state 구조 분석
        logger.info(f"🔍 final_state 구조 분석:")
        logger.info(f"   - final_state 키들: {list(final_state.keys()) if isinstance(final_state, dict) else 'dict가 아님'}")
        logger.info(f"   - tools_used: {len(tools_used)} 항목")
        logger.info(f"   - tool_results: {len(tool_results)} 항목")
        logger.info(f"   - analysis_history: {len(analysis_history)} 항목")
        logger.info(f"   - current_step: {steps_count}")
        
        # 특별한 키들 확인
        special_keys = ['analysis_content', 'final_content', 'result', 'output', 'response']
        for key in special_keys:
            if key in final_state:
                value = final_state[key]
                if isinstance(value, str) and len(value.strip()) > 10:
                    logger.info(f"   - 발견된 특별 키 '{key}': {len(value)}자")
                else:
                    logger.info(f"   - 특별 키 '{key}': {type(value)} (내용 없음)")
        
        # Extract final AI message - final_state 구조 확인 및 메시지 추출
        messages = []
        
        # final_state가 중첩 구조인지 확인
        if 'model' in final_state and isinstance(final_state['model'], dict) and 'messages' in final_state['model']:
            messages = final_state['model']['messages']
            logger.info("🔍 중첩된 model.messages에서 메시지 추출")
        else:
            messages = final_state.get('messages', [])
            logger.info("🔍 직접 messages에서 메시지 추출")
        
        final_content = ""
        
        logger.info(f"🔍 메시지 추출 디버깅:")
        logger.info(f"   - 전체 메시지 수: {len(messages)}")
        logger.info(f"   - final_state 최상위 키들: {list(final_state.keys())}")
        if 'model' in final_state:
            model_keys = list(final_state['model'].keys()) if isinstance(final_state['model'], dict) else 'dict가 아님'
            logger.info(f"   - final_state.model 키들: {model_keys}")
        
        # 메시지 타입별 분석
        message_types = {}
        for i, msg in enumerate(messages):
            msg_type = type(msg).__name__
            message_types[msg_type] = message_types.get(msg_type, 0) + 1
            logger.info(f"   - 메시지 {i}: {msg_type}")
            
            # 메시지 내용 미리보기 (처음 100자)
            if hasattr(msg, 'content') and msg.content:
                content_preview = str(msg.content)[:100] + "..." if len(str(msg.content)) > 100 else str(msg.content)
                logger.info(f"     내용: {content_preview}")
        
        logger.info(f"   - 메시지 타입별 통계: {message_types}")
        
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        
        # AI 메시지 추출 (개선된 방법들)
        ai_messages = []
        
        # 방법 1: AIMessage 타입 체크
        for msg in messages:
            if isinstance(msg, AIMessage):
                ai_messages.append(msg)
        
        logger.info(f"   - AIMessage 타입 메시지 수: {len(ai_messages)}")
        
        # 방법 2: 타입 이름으로 체크 (fallback)
        if not ai_messages:
            for msg in messages:
                if type(msg).__name__ == 'AIMessage':
                    ai_messages.append(msg)
            logger.info(f"   - 타입 이름 기반 AIMessage 수: {len(ai_messages)}")
        
        # 방법 3: hasattr로 AIMessage 속성 확인
        if not ai_messages:
            for msg in messages:
                if hasattr(msg, 'content') and hasattr(msg, 'response_metadata'):
                    ai_messages.append(msg)
            logger.info(f"   - 속성 기반 AIMessage 수: {len(ai_messages)}")
        
        # 방법 4: content가 있고 충분히 긴 메시지 (최후 수단)
        if not ai_messages:
            content_messages = [msg for msg in messages if hasattr(msg, 'content') and msg.content and len(str(msg.content).strip()) > 50]
            if content_messages:
                # 가장 긴 내용을 가진 메시지 선택
                longest_msg = max(content_messages, key=lambda m: len(str(m.content)) if m.content else 0)
                ai_messages = [longest_msg]
                logger.info(f"   - 가장 긴 콘텐츠 메시지 추출: {len(str(longest_msg.content))}자")
        
        if ai_messages:
            last_ai_msg = ai_messages[-1]
            if hasattr(last_ai_msg, 'content') and last_ai_msg.content:
                final_content = str(last_ai_msg.content)
                logger.info(f"   - 추출된 최종 응답 길이: {len(final_content)}")
                logger.info(f"   - 최종 응답 미리보기: {final_content[:200]}...")
            else:
                logger.warning(f"   - AI 메시지에 content가 없음: {type(last_ai_msg)}")
        else:
            logger.warning("   - AI 메시지를 찾을 수 없음")
            
            # 디버깅을 위해 모든 메시지 내용 출력
            logger.warning("   - 전체 메시지 내용 덤프:")
            for i, msg in enumerate(messages):
                logger.warning(f"     메시지 {i}: {type(msg).__name__}")
                if hasattr(msg, 'content'):
                    content_str = str(msg.content)[:300] + "..." if len(str(msg.content)) > 300 else str(msg.content)
                    logger.warning(f"       내용: {content_str}")
                else:
                    logger.warning(f"       내용: content 속성 없음")
        
        # 추가: final_state에서 다른 방법으로 콘텐츠 찾기
        if not final_content:
            logger.info("🔍 대안적 콘텐츠 추출 시도:")
            final_content = self._extract_content_from_state(final_state)
        
        # 여전히 콘텐츠가 없으면 종합 분석 생성
        if not final_content or len(final_content.strip()) < 100:
            logger.info("🔍 콘텐츠 부족으로 종합 분석 생성")
            final_content = self._generate_fallback_analysis(final_state)
        
        # 최종 확인
        if final_content:
            logger.info(f"✅ 최종 콘텐츠 추출 성공! 길이: {len(final_content)}자")
        else:
            logger.error("❌ 최종 콘텐츠 추출 실패 - 모든 방법 실패")
            logger.error("❌ final_state 전체 덤프:")
            import json
            try:
                state_dump = json.dumps(final_state, indent=2, default=str, ensure_ascii=False)[:2000]
                logger.error(f"   State dump (처음 2000자): {state_dump}")
            except Exception as dump_error:
                logger.error(f"   State dump 실패: {dump_error}")
                logger.error(f"   State type: {type(final_state)}")
                logger.error(f"   State keys: {list(final_state.keys()) if hasattr(final_state, 'keys') else 'keys() 없음'}")
        
        # Create analysis summary
        analysis_summary = final_content[:1000] + "..." if len(final_content) > 1000 else final_content
        
        # Log results
        logger.info(f"📊 Analysis result summary:")
        logger.info(f"  - Execution time: {execution_time:.2f} seconds")
        logger.info(f"  - Execution steps: {steps_count}")
        logger.info(f"  - Used tools: {tools_used}")
        logger.info(f"  - Tool results: {len(tool_results)}")
        logger.info(f"  - Analysis history: {len(analysis_history)}")
        logger.info(f"  - Final content: {len(final_content)} characters")

        # Aggregate and log token usage from tools (if provided by tools)
        try:
            token_input_sum = 0
            token_output_sum = 0
            token_total_sum = 0
            per_tool_tokens = []
            for tr in tool_results:
                if isinstance(tr, dict):
                    wrapper = tr.get('data', {})
                    inner = wrapper.get('data', {}) if isinstance(wrapper, dict) else {}
                    tok = inner.get('token_usage') if isinstance(inner, dict) else None
                    if isinstance(tok, dict):
                        ti = tok.get('input_tokens') or 0
                        to = tok.get('output_tokens') or 0
                        tt = tok.get('total_tokens') or 0
                        # Safe int conversion
                        ti = int(ti) if isinstance(ti, (int, float)) or (isinstance(ti, str) and ti.isdigit()) else 0
                        to = int(to) if isinstance(to, (int, float)) or (isinstance(to, str) and to.isdigit()) else 0
                        tt = int(tt) if isinstance(tt, (int, float)) or (isinstance(tt, str) and tt.isdigit()) else (ti + to)
                        token_input_sum += ti
                        token_output_sum += to
                        token_total_sum += tt
                        per_tool_tokens.append((tr.get('tool_name', 'unknown'), ti, to, tt))
            logger.info(f"🔢 Token usage by tool: {per_tool_tokens}")
            if per_tool_tokens:
                for name, ti, to, tt in per_tool_tokens:
                    logger.info(f"🔢 Token usage by tool [{name}]: input={ti}, output={to}, total={tt}")
                logger.info(f"🔢 Token usage total (tools): input={token_input_sum}, output={token_output_sum}, total={token_total_sum}")
        except Exception as token_err:
            logger.debug(f"Token usage aggregation skipped: {str(token_err)}")
        
        # Preview final analysis content (for development)
        if final_content:
            preview = final_content[:500] + "..." if len(final_content) > 500 else final_content
            logger.info(f"📝 Final analysis content preview:\n{preview}")
        
        # Save final AI response to OpenSearch
        opensearch_saved = self._save_final_ai_response_to_opensearch(final_content, final_state)
        logger.info(f"💾 OpenSearch 저장 최종 결과: {opensearch_saved}")
        
        # Save summary to Segments table
        segments_summary_saved = self._save_summary_to_segments_table(final_content)
        logger.info(f"💾 Segments 테이블 summary 저장 최종 결과: {segments_summary_saved}")
        
        # Extract references from final_state for streaming
        final_references = final_state.get('tool_references', [])
        logger.info(f"📋 최종 참조 개수: {len(final_references)}")
        
        return {
            'success': True,
            'document_id': self.document_id,
            'segment_id': self.segment_id,
            'segment_index': self.segment_index,
            'analysis_content': final_content,
            'analysis_summary': analysis_summary,
            'analysis_time': execution_time,
            'steps_count': steps_count,
            'tools_used': tools_used,
            'tool_results': tool_results,
            'analysis_history': analysis_history,
            'references': final_references,  # 참조 정보 추가
            'opensearch_saved': opensearch_saved,  # 실제 저장 결과 포함
            'segments_summary_saved': segments_summary_saved,  # Segments 테이블 summary 저장 결과
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _save_final_ai_response_to_opensearch(self, final_content: str, final_state: AgentState):
        """최종 AI 응답을 OpenSearch에 저장"""
        logger.info("🔄 _save_final_ai_response_to_opensearch 함수 호출됨")
        try:
            logger.info(f"📝 최종 응답 길이: {len(final_content) if final_content else 0}")
            
            if not final_content or len(final_content.strip()) < 10:
                logger.info("📝 응답 내용이 너무 짧아 최종 응답 저장 건너뜀")
                return False
            
            logger.info(f"🔍 OpenSearch 서비스 상태: {self.opensearch_service is not None}")
            if not self.opensearch_service:
                logger.warning("⚠️ OpenSearch 서비스가 없어 최종 응답 저장 건너뜀")
                return False
            
            # 사용자 쿼리 추출
            user_query = (f"문서 '{self.document_id}' "
                         f"페이지 {self.segment_index + 1}를 다양한 각도에서 도구를 활용하여 "
                         f"분석하고 상세히 설명해주세요.")
            logger.info(f"💬 사용자 쿼리: {user_query[:100]}...")
            
            # OpenSearch 저장 시도 전 상세 정보 로그
            logger.info("💾 OpenSearch에 최종 AI 응답 저장 시도 중...")
            logger.info(f"   - segment_id: {self.segment_id}")
            logger.info(f"   - document_id: {self.document_id}")
            logger.info(f"   - segment_index: {self.segment_index}")
            logger.info(f"   - analysis_query 길이: {len(user_query)}")
            logger.info(f"   - content 길이: {len(final_content)}")
            logger.info(f"   - analysis_steps: final_ai_response")
            
            # segment-unit 방식으로 최종 AI 응답을 ai_analysis 도구로 저장
            success = self.opensearch_service.add_ai_analysis_tool(
                index_id=self.index_id,
                document_id=self.document_id,
                segment_id=self.segment_id,
                segment_index=self.segment_index,
                analysis_query=user_query,
                content=final_content,
                analysis_steps="final_ai_response",
                analysis_type="final_ai_response",
                media_type=self.media_type
            )
            logger.info(f"💾 OpenSearch 저장 결과: {success}")
            
            if success:
                logger.info(f"✅ OpenSearch 최종 AI 응답 저장 완료")
                logger.info(f"💾 저장된 데이터: segment_id={self.segment_id}, query={user_query[:50]}...")
                
                # 임베딩 업데이트도 시도
                try:
                    logger.info("🔄 임베딩 업데이트 시도 중...")
                    embedding_success = self.opensearch_service.update_segment_embeddings(self.index_id, self.segment_id)
                    logger.info(f"🔄 임베딩 업데이트 결과: {embedding_success}")
                except Exception as embedding_error:
                    logger.warning(f"⚠️ 임베딩 업데이트 실패 (계속 진행): {str(embedding_error)}")
                
                return True
            else:
                logger.error(f"❌ OpenSearch 최종 AI 응답 저장 실패 (success=False)")
                return False
            
        except Exception as e:
            logger.error(f"❌ OpenSearch 최종 AI 응답 저장 실패: {str(e)}")
            logger.error(f"❌ 예외 타입: {type(e).__name__}")
            import traceback
            logger.error(f"❌ 오류 상세 스택 트레이스:")
            logger.error(traceback.format_exc())
            
            # 추가 디버깅 정보
            logger.error("🔍 추가 디버깅 정보:")
            logger.error(f"   - OpenSearch 서비스 객체: {type(self.opensearch_service) if self.opensearch_service else None}")
            logger.error(f"   - OpenSearch 엔드포인트: {getattr(self.opensearch_service, 'endpoint', 'N/A') if self.opensearch_service else 'N/A'}")
            logger.error(f"   - OpenSearch 인덱스: {getattr(self.opensearch_service, 'index_name', 'N/A') if self.opensearch_service else 'N/A'}")
            logger.error(f"   - 세그먼트 정보: segment_id={self.segment_id}")
            logger.error(f"   - 콘텐츠 정보: 길이={len(final_content) if final_content else 0}")
            
            # 예외를 다시 발생시키지 않고 False 반환으로 실패를 명확히 표시
            return False
    
    def _save_summary_to_segments_table(self, final_content: str) -> bool:
        """Segments 테이블에 summary를 저장"""
        logger.info("🔄 _save_summary_to_segments_table 함수 호출됨")
        
        if not final_content or len(final_content.strip()) < 10:
            logger.info("📝 요약 내용이 너무 짧아 저장 건너뜀")
            return False
        
        if not self.dynamodb_service:
            logger.warning("⚠️ DynamoDB 서비스가 없어 summary 저장 건너뜀")
            return False
        
        if not self.segment_id:
            logger.warning("⚠️ segment_id가 없어 summary 저장 건너뜀")
            return False
        
        try:
            # Segments 테이블에 summary 업데이트
            logger.info(f"💾 Segments 테이블에 summary 저장 시도 중...")
            logger.info(f"   - segment_id: {self.segment_id}")
            logger.info(f"   - summary 길이: {len(final_content)}")
            
            # Summary 내용 길이 제한 (DynamoDB 아이템 크기 제한 고려)
            max_summary_length = 30000  # 30KB 제한
            if len(final_content) > max_summary_length:
                summary_content = final_content[:max_summary_length] + "...[요약됨]"
                logger.info(f"   - summary 내용이 너무 길어 {max_summary_length}자로 제한됨")
            else:
                summary_content = final_content
            
            # DynamoDB 업데이트 데이터 구성
            update_data = {
                'summary': summary_content,
                'analysis_completed_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Segments 테이블 업데이트
            success = self.dynamodb_service.update_item(
                table_name='segments',
                key={'segment_id': self.segment_id},
                updates=update_data
            )
            
            if success:
                logger.info(f"✅ Segments 테이블에 summary 저장 완료")
                logger.info(f"💾 저장된 데이터: segment_id={self.segment_id}, summary_length={len(summary_content)}")
                return True
            else:
                logger.error(f"❌ Segments 테이블 summary 저장 실패 (success=False)")
                return False
                
        except Exception as e:
            logger.error(f"❌ Segments 테이블 summary 저장 실패: {str(e)}")
            logger.error(f"❌ 예외 타입: {type(e).__name__}")
            import traceback
            logger.error(f"❌ 오류 상세 스택 트레이스:")
            logger.error(traceback.format_exc())
            return False
    
    def _extract_content_from_state(self, final_state: AgentState) -> str:
        """final_state에서 콘텐츠 추출 (여러 전략 사용)"""
        logger.info("🔍 _extract_content_from_state 시작")
        
        # analysis_history에서 추출 시도
        analysis_history = final_state.get('analysis_history', [])
        if analysis_history:
            logger.info(f"   - analysis_history 항목 수: {len(analysis_history)}")
            for item in reversed(analysis_history):  # 최근 것부터
                if isinstance(item, dict):
                    for key in ['content', 'result', 'output', 'analysis']:
                        if key in item:
                            content_candidate = str(item[key])
                            if len(content_candidate.strip()) > 50:
                                logger.info(f"   - analysis_history['{key}']에서 콘텐츠 추출: {len(content_candidate)}자")
                                return content_candidate
        
        # tool_results에서 추출 시도
        tool_results = final_state.get('tool_results', [])
        if tool_results:
            logger.info(f"   - tool_results 항목 수: {len(tool_results)}")
            for result in reversed(tool_results):  # 최근 것부터
                if isinstance(result, dict):
                    for key in ['result', 'content', 'output', 'analysis']:
                        if key in result:
                            content_candidate = str(result[key])
                            if len(content_candidate.strip()) > 50:
                                logger.info(f"   - tool_results['{key}']에서 콘텐츠 추출: {len(content_candidate)}자")
                                return content_candidate
        
        # combined_analysis_context에서 추출
        combined_context = final_state.get('combined_analysis_context', '')
        if combined_context and len(combined_context.strip()) > 50:
            logger.info(f"   - combined_analysis_context에서 콘텐츠 추출: {len(combined_context)}자")
            return combined_context
        
        # final_state의 모든 값에서 긴 문자열 찾기 (최후 수단)
        logger.info("🔍 final_state 전체에서 콘텐츠 찾기:")
        for key, value in final_state.items():
            if isinstance(value, str) and len(value.strip()) > 100:
                logger.info(f"   - '{key}' 키에서 콘텐츠 발견: {len(value)}자")
                return value
            elif isinstance(value, list) and value:
                # 리스트의 마지막 항목이 문자열인지 확인
                last_item = value[-1]
                if isinstance(last_item, str) and len(last_item.strip()) > 100:
                    logger.info(f"   - '{key}' 리스트의 마지막 항목에서 콘텐츠 발견: {len(last_item)}자")
                    return last_item
                elif isinstance(last_item, dict) and 'content' in last_item:
                    content_candidate = str(last_item['content'])
                    if len(content_candidate.strip()) > 100:
                        logger.info(f"   - '{key}' 리스트 항목의 content에서 발견: {len(content_candidate)}자")
                        return content_candidate
        
        logger.info("   - 추출 가능한 콘텐츠를 찾지 못함")
        return ""
    
    def _generate_fallback_analysis(self, final_state: AgentState) -> str:
        """콘텐츠 추출에 실패했을 때 fallback 분석 생성"""
        logger.info("📝 _generate_fallback_analysis 시작")
        
        # 기본 정보 수집
        document_id = final_state.get('document_id', self.document_id)
        segment_id = final_state.get('segment_id', self.segment_id)
        user_query = final_state.get('user_query', '')
        current_step = final_state.get('current_step', 0)
        
        # State에서 유용한 정보 수집
        analysis_history = final_state.get('analysis_history', [])
        tool_results = final_state.get('tool_results', [])
        tools_used = final_state.get('tools_used', [])
        combined_context = final_state.get('combined_analysis_context', '')
        
        # 실행된 도구 정보
        tools_info = []
        for entry in analysis_history:
            if isinstance(entry, dict):
                tool_name = entry.get('tool_name', 'Unknown')
                success = entry.get('success', False)
                result_preview = str(entry.get('result', ''))[:200] + "..." if entry.get('result') else "No result"
                tools_info.append({
                    'tool': tool_name,
                    'success': success,
                    'preview': result_preview
                })
        
        # Fallback 분석 생성
        fallback_analysis = f"""# 문서 분석 결과 (Fallback 생성)

## 📋 분석 개요
- **문서 ID**: {document_id}
- **세그먼트 ID**: {segment_id}
- **분석 요청**: {user_query[:300]}{'...' if len(user_query) > 300 else ''}
- **실행 단계**: {current_step}
- **상태**: 분석 완료 (Fallback 생성)

## 🛠️ 실행된 분석 도구
"""
        
        if tools_info:
            for i, tool_info in enumerate(tools_info, 1):
                status = "✅" if tool_info['success'] else "❌"
                fallback_analysis += f"""
### {i}. {tool_info['tool']} {status}
- **실행 상태**: {"성공" if tool_info['success'] else "실패"}
- **결과 미리보기**: {tool_info['preview']}
"""
        else:
            fallback_analysis += "\n- 실행된 도구가 없습니다.\n"
        
        # 종합 분석 컨텍스트가 있는 경우 포함
        if combined_context and len(combined_context.strip()) > 10:
            fallback_analysis += f"""

## 🔗 수집된 분석 정보
{combined_context[:800]}{'...' if len(combined_context) > 800 else ''}
"""
        
        fallback_analysis += f"""

## ⚠️ 분석 완료 정보
이 결과는 시스템에서 자동으로 생성된 fallback 분석입니다. 
원본 AI 모델의 응답을 추출할 수 없어 수집된 정보를 바탕으로 구성되었습니다.

- **총 실행 단계**: {current_step}
- **사용된 도구 수**: {len(tools_info)}
- **수집된 정보량**: {len(combined_context)} 문자

---
*분석 생성 시간: {datetime.now(timezone.utc).isoformat()}*
*생성 방식: Fallback Analysis*
"""
        
        logger.info(f"📝 Fallback 분석 생성 완료 - 길이: {len(fallback_analysis)} 문자")
        logger.info(f"📝 포함된 도구 정보: {len(tools_info)}개")
        
        return fallback_analysis