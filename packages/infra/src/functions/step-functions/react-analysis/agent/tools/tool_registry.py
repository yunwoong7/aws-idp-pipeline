"""
Tool registry for managing and executing tools with OpenSearch integration (Lambda 버전)
"""

import json
import logging
import time
import sys
import os
from typing import Dict, Any, List, Optional
from langchain_core.tools import StructuredTool
from agent.tools.base import BaseTool, ToolResult

# Common module imports
sys.path.append('/opt/python')
from common import OpenSearchService, get_current_timestamp, generate_uuid

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Registry for managing tools with OpenSearch integration (백엔드와 동일)"""
    
    def __init__(self, enable_opensearch: bool = True, project_id: str = None, document_id: str = None, page_id: str = None,
                 file_path: str = None, image_path: str = None, page_index: int=None):
        self._tools: Dict[str, BaseTool] = {}
        self.enable_opensearch = enable_opensearch
        self.opensearch_service = None
        
        # Agent 컨텍스트 저장소ㅁ
        self._agent_context: Dict[str, Any] = {
            "project_id": project_id,
            "document_id": document_id,
            "page_id": page_id,
            "file_path": file_path,
            "image_path": image_path,
            "page_index": page_index,
            "thread_id": None,
            "session_id": None,
            "user_query": ""
        }
        
        # 도구 결과 캐시 (간단화)
        self._tool_results_cache: List[Dict[str, Any]] = []
        
        # OpenSearch 서비스 초기화
        if self.enable_opensearch:
            try:
                opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
                if opensearch_endpoint:
                    self.opensearch_service = OpenSearchService(
                        endpoint=opensearch_endpoint,
                        index_name=os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis'),
                        region=os.environ.get('OPENSEARCH_REGION') or os.environ.get('AWS_REGION', 'us-west-2')
                    )
                    logger.info(f"ToolRegistry OpenSearch 활성화: 프로젝트 ID = {project_id}")
                else:
                    logger.warning("OPENSEARCH_ENDPOINT 환경 변수가 설정되지 않음")
                    self.enable_opensearch = False
            except Exception as e:
                logger.warning(f"ToolRegistry OpenSearch 초기화 실패: {str(e)}")
                self.enable_opensearch = False
    
    def register_tool(self, name: str, tool_instance: BaseTool):
        """Register a tool instance"""
        self._tools[name] = tool_instance
        return self
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool instance by name"""
        return self._tools.get(name)
    
    def set_agent_context(self, context_data: Dict[str, Any]) -> None:
        """
        Agent 컨텍스트 설정 (백엔드와 동일)
        
        Args:
            context_data: 설정할 컨텍스트 데이터
        """
        # 프로젝트나 세션이 변경되면 캐시 초기화
        old_project_id = self._agent_context.get("project_id")
        new_project_id = context_data.get("project_id")
        
        if (context_data.get("clear_cache", False) or 
            (old_project_id and new_project_id and old_project_id != new_project_id)):
            self.clear_tool_results_cache()
        
        # 컨텍스트 업데이트
        self._agent_context.update(context_data)
        
        # 프로젝트 ID 변경 시 OpenSearch 서비스 업데이트는 필요 없음 (Common 모듈 사용)
        if "project_id" in context_data and self.enable_opensearch:
            logger.info(f"OpenSearch 프로젝트 ID 업데이트: {context_data['project_id']}")
    
    def get_agent_context(self, key: str = None) -> Any:
        """Agent 컨텍스트 조회"""
        if key:
            return self._agent_context.get(key)
        return self._agent_context.copy()
    
    def _cache_tool_result(self, tool_name: str, result: ToolResult, kwargs: Dict[str, Any]) -> None:
        """도구 실행 결과를 간단한 캐시에 저장"""
        try:
            cache_item = {
                "timestamp": time.time(),
                "timestamp_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tool_name": tool_name,
                "success": result.success,
                "message": result.message[:200] + "..." if len(result.message) > 200 else result.message,
                "project_id": self._agent_context.get("project_id", "unknown")
            }
            
            self._tool_results_cache.append(cache_item)
            
            # 캐시 크기 제한 (최대 20개)
            if len(self._tool_results_cache) > 20:
                self._tool_results_cache = self._tool_results_cache[-20:]
            
        except Exception as e:
            logger.error(f"도구 결과 캐시 저장 실패: {str(e)}")
    
    def clear_tool_results_cache(self) -> None:
        """도구 결과 캐시 초기화"""
        cache_count = len(self._tool_results_cache)
        self._tool_results_cache.clear()
        logger.info(f"도구 결과 캐시 초기화: {cache_count}개 항목 삭제")
        print(f"🗑️ 도구 결과 캐시 초기화됨 (이전 {cache_count}개 항목 삭제)")
    
    def get_cached_tool_results(self, limit: int = None, tool_name: str = None) -> List[Dict[str, Any]]:
        """캐시된 도구 결과 조회"""
        try:
            results = self._tool_results_cache.copy()
            
            # 도구명 필터링
            if tool_name:
                results = [r for r in results if r["tool_name"] == tool_name]
            
            # 시간순 정렬 (최신 순)
            results.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # 개수 제한
            if limit:
                results = results[:limit]
            
            return results
            
        except Exception as e:
            logger.error(f"캐시된 도구 결과 조회 실패: {str(e)}")
            return []
    
    def execute_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name with OpenSearch logging"""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        
        # 🚀 도구 호출 시작 로깅
        start_time = time.time()
        logger.info("🚀" + "=" * 80)
        logger.info(f"🚀 도구 실행 시작: {name}")
        logger.info("🚀" + "=" * 80)
        logger.info(f"🔧 도구 타입: {type(tool).__name__}")
        logger.info(f"📋 Agent 컨텍스트 지원: {getattr(tool, 'supports_agent_context', False)}")
        logger.info(f"📊 입력 인자 수: {len(kwargs)}")
        
        # 인자 로깅 (민감한 정보 제외)
        safe_kwargs = {}
        for key, value in kwargs.items():
            if key.startswith('_'):
                safe_kwargs[key] = "[Agent Context]"
            elif isinstance(value, str) and len(value) > 100:
                safe_kwargs[key] = f"{value[:100]}... ({len(value)} 문자)"
            elif isinstance(value, list) and len(value) > 5:
                safe_kwargs[key] = f"[리스트: {len(value)}개 항목]"
            else:
                safe_kwargs[key] = value
        
        logger.info(f"📝 입력 인자: {safe_kwargs}")
        
        # Agent 컨텍스트 주입 (필요한 경우)
        if hasattr(tool, 'supports_agent_context') and tool.supports_agent_context:
            kwargs['_agent_context'] = self.get_agent_context()
            logger.info("✅ Agent 컨텍스트가 도구에 전달됨")
        
        try:
            # 도구 실행
            logger.info(f"⚡ {name} 실행 중...")
            result = tool.execute(**kwargs)
            
            execution_time = time.time() - start_time
            
            # 🎯 도구 실행 완료 로깅
            logger.info("🎯" + "=" * 80)
            logger.info(f"🎯 도구 실행 완료: {name}")
            logger.info("🎯" + "=" * 80)
            logger.info(f"✅ 성공 여부: {result.success}")
            logger.info(f"⏱️  실행 시간: {execution_time:.2f}초")
            logger.info(f"📄 응답 길이: {len(result.message)} 문자")
            logger.info(f"📊 데이터 포함: {'예' if result.data else '아니오'}")
            
            # 도구 결과 캐시
            self._cache_tool_result(name, result, kwargs)
            
            # OpenSearch에 결과 저장 (성공한 경우만)
            if self.enable_opensearch and self.opensearch_service and result.success:
                try:
                    self._save_to_opensearch(name, result, kwargs)
                except Exception as e:
                    logger.error(f"OpenSearch 저장 실패: {str(e)}")
            
            logger.info("✅" + "=" * 80)
            
            return {
                "success": result.success,
                "message": result.message,
                "data": result.data,
                "execution_time": execution_time
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"도구 '{name}' 실행 실패: {str(e)}"
            
            # ❌ 도구 실행 실패 로깅
            logger.error("❌" + "=" * 80)
            logger.error(f"❌ 도구 실행 실패: {name}")
            logger.error("❌" + "=" * 80)
            logger.error(f"💥 오류 메시지: {str(e)}")
            logger.error(f"⏱️  실행 시간: {execution_time:.2f}초")
            logger.error("❌" + "=" * 80)
            
            return {
                "success": False,
                "message": error_msg,
                "data": None,
                "execution_time": execution_time
            }

    def _save_to_opensearch(self, tool_name: str, result: ToolResult, kwargs: Dict[str, Any]) -> None:
        """
        도구 결과를 OpenSearch에 저장 (Common 모듈 사용)
        
        Args:
            tool_name: 도구 이름
            result: 도구 실행 결과
            kwargs: 도구 실행 인자
        """
        try:
            # 기본 정보 추출
            project_id = self._agent_context.get("project_id")
            document_id = self._agent_context.get('document_id')
            page_id = self._agent_context.get('page_id')
            page_number = self._extract_page_number(kwargs)
            file_path = self._extract_file_path(result, kwargs)
            image_path = self._extract_image_path(result, kwargs)
            
            if not project_id:
                logger.warning("project_id가 없어 OpenSearch 저장 건너뜀")
                return
            
            if not document_id:
                # 기본값으로 생성
                timestamp_ms = int(time.time() * 1000)
                tmp_doc_id = file_path.split("/")[-1].replace(".pdf", "") if file_path else "unknown"
                document_id = f"tool_{tmp_doc_id}_{timestamp_ms}"
                logger.warning(f"document_id가 컨텍스트에 없어 기본값 사용: {document_id}")

            # OpenSearch 문서 데이터 구성
            doc_data = {
                "project_id": project_id,
                "document_id": document_id,
                "page_id": page_id,
                "page_number": page_number,
                "tool_name": tool_name,
                "content": result.message,
                "success": result.success,
                "file_path": file_path,
                "image_path": image_path,
                "created_at": get_current_timestamp(),
                "session_id": self._agent_context.get("session_id"),
                "thread_id": self._agent_context.get("thread_id")
            }
            
            # 추가 데이터가 있으면 포함
            if result.data:
                doc_data["additional_data"] = result.data
            
            # OpenSearch에 문서 저장
            doc_id = generate_uuid()
            self.opensearch_service.index_document(doc_id, doc_data)
            
            logger.info(f"✅ OpenSearch 저장 완료: {tool_name} → 문서 ID: {doc_id}")
            
        except Exception as e:
            logger.error(f"❌ OpenSearch 저장 실패 ({tool_name}): {str(e)}")

    def _extract_page_number(self, kwargs: Dict[str, Any]) -> int:
        """인수에서 페이지 번호 추출"""
        return (kwargs.get('page_number') or 
                kwargs.get('page_num') or 
                kwargs.get('page_index') or
                self._agent_context.get('page_num') or 
                self._agent_context.get('page_index') or 
                1)

    def _extract_file_path(self, result: ToolResult, kwargs: Dict[str, Any]) -> Optional[str]:
        """결과나 인수에서 파일 경로 추출"""
        # 인수에서 먼저 확인
        for key in ['file_path', 'pdf_path', 'image_path']:
            if kwargs.get(key):
                return kwargs[key]
        
        # result data에서 확인
        if result.data:
            for key in ['file_path', 'pdf_path', 'image_path']:
                if result.data.get(key):
                    return result.data[key]
        
        # agent context에서 확인
        return (self._agent_context.get('file_path') or 
                self._agent_context.get('image_path'))

    def _extract_image_path(self, result: ToolResult, kwargs: Dict[str, Any]) -> Optional[str]:
        """결과나 인수에서 이미지 경로 추출"""
        # 인수에서 먼저 확인
        for key in ['image_path', 'image_paths', 'images']:
            value = kwargs.get(key)
            if value:
                # 리스트인 경우 첫 번째 항목 반환
                if isinstance(value, list) and value:
                    return value[0]
                return value
        
        # result data에서 확인
        if result.data:
            for key in ['image_path', 'image_paths', 'images']:
                value = result.data.get(key)
                if value:
                    if isinstance(value, list) and value:
                        return value[0]
                    return value
        
        # agent context에서 확인
        return self._agent_context.get('image_path')

    def list_tools(self) -> List[str]:
        """등록된 모든 도구 이름 반환"""
        return list(self._tools.keys())
    
    def get_all_langchain_tools(self) -> List:
        """LangChain 호환 도구 리스트 반환 (백엔드와 동일)"""
        langchain_tools = []
        
        for tool_name, tool_instance in self._tools.items():
            def create_wrapper(tool_name: str, tool_instance: BaseTool):
                def wrapper(**kwargs) -> str:
                    """LangChain 도구 래퍼"""
                    try:
                        # Agent context 설정 (도구가 지원하는 경우)
                        if hasattr(tool_instance, 'supports_agent_context') and tool_instance.supports_agent_context:
                            kwargs['_agent_context'] = self.get_agent_context()
                        
                        # 도구 실행
                        result = tool_instance.execute(**kwargs)
                        
                        # 캐시에 저장
                        self._cache_tool_result(tool_name, result, kwargs)
                        
                        # OpenSearch에 저장
                        if self.enable_opensearch and self.opensearch_service and result.success:
                            try:
                                self._save_to_opensearch(tool_name, result, kwargs)
                            except Exception as e:
                                logger.error(f"OpenSearch 저장 실패: {str(e)}")
                        
                        # LangChain은 문자열 응답을 기대하므로 message 반환
                        return result.message
                        
                    except Exception as e:
                        error_msg = f"도구 '{tool_name}' 실행 실패: {str(e)}"
                        logger.error(error_msg)
                        return error_msg
                
                return wrapper
            
            # 도구 스키마 가져오기
            schema = tool_instance.get_schema()
            
            # LangChain StructuredTool 생성
            langchain_tool = StructuredTool(
                name=tool_name,
                description=f'{tool_name} 도구',
                args_schema=schema,
                func=create_wrapper(tool_name, tool_instance)
            )
            
            langchain_tools.append(langchain_tool)
        
        return langchain_tools

    def search_project_results(self, query: str, analysis_type: str = None, 
                              tool_name: str = None, size: int = 10) -> List[Dict[str, Any]]:
        """
        프로젝트 내 분석 결과 검색 (Common 모듈 사용)
        
        Args:
            query: 검색 쿼리
            analysis_type: 분석 타입 필터
            tool_name: 도구명 필터
            size: 결과 개수
            
        Returns:
            검색 결과 리스트
        """
        if not self.opensearch_service:
            logger.warning("OpenSearch가 활성화되지 않음")
            return []
        
        try:
            index_id = self._agent_context.get("index_id")
            # 필터 구성
            filters = {}
            if analysis_type:
                filters["analysis_type"] = analysis_type
            if tool_name:
                filters["tool_name"] = tool_name
            
            response = self.opensearch_service.search_text(
                index_id=index_id,
                query=query,
                size=size,
                filters=filters
            )
            
            hits = response.get('hits', {}).get('hits', [])
            results = []
            
            for hit in hits:
                source = hit.get('_source', {})
                results.append({
                    'id': hit.get('_id'),
                    'score': hit.get('_score'),
                    'content': source.get('content'),
                    'tool_name': source.get('tool_name'),
                    'created_at': source.get('created_at'),
                    'project_id': source.get('project_id'),
                    'document_id': source.get('document_id'),
                    'page_id': source.get('page_id'),
                    'page_number': source.get('page_number')
                })
            
            return results
            
        except Exception as e:
            logger.error(f"프로젝트 결과 검색 실패: {str(e)}")
            return []

    def get_project_statistics(self) -> Dict[str, Any]:
        """
        프로젝트 통계 조회 (Common 모듈 사용)
        
        Returns:
            프로젝트 통계
        """
        if not self.opensearch_service:
            return {"error": "OpenSearch가 활성화되지 않음"}
        
        try:
            index_id = self._agent_context.get("index_id")
            if not index_id:
                return {"error": "인덱스 ID가 설정되지 않음"}
            

            # 전체 결과 수 조회
            response = self.opensearch_service.search_text(
                index_id=index_id,
                query="*",
                size=0,  # 개수만 필요
            )
            
            total_count = response.get('hits', {}).get('total', {}).get('value', 0)
            
            # 도구별 통계는 aggregation이 필요한데, 현재 Common 모듈에서 지원하지 않으므로 간단하게 처리
            stats = {
                "index_id": index_id,
                "total_documents": total_count,
                "last_updated": get_current_timestamp()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"프로젝트 통계 조회 실패: {str(e)}")
            return {"error": str(e)}

    @property
    def project_id(self) -> Optional[str]:
        """현재 프로젝트 ID 반환"""
        return self._agent_context.get("project_id")

    def set_project_id(self, project_id: str, file_path: str = None, image_path: str = None) -> None:
        """
        프로젝트 ID 설정 (백엔드와 동일)
        
        Args:
            project_id: 프로젝트 ID
            file_path: 파일 경로 (선택사항)
            image_path: 이미지 경로 (선택사항)
        """
        old_project_id = self._agent_context.get("project_id")
        
        # 프로젝트가 변경되면 캐시 초기화
        if old_project_id and old_project_id != project_id:
            self.clear_tool_results_cache()
        
        # 컨텍스트 업데이트
        self._agent_context.update({
            "project_id": project_id,
            "file_path": file_path or self._agent_context.get("file_path"),
            "image_path": image_path or self._agent_context.get("image_path")
        })
        
        logger.info(f"프로젝트 ID 설정: {project_id}")
        logger.info(f"파일 경로: {file_path}")
        logger.info(f"이미지 경로: {image_path}")

    def reset_for_new_session(self, project_id: str = None, session_id: str = None, 
                             thread_id: str = None, clear_cache: bool = True) -> None:
        """
        새 세션을 위한 리셋 (백엔드와 동일)
        
        Args:
            project_id: 프로젝트 ID
            session_id: 세션 ID  
            thread_id: 스레드 ID
            clear_cache: 캐시 초기화 여부
        """
        if clear_cache:
            self.clear_tool_results_cache()
        
        # 컨텍스트 업데이트
        update_data = {}
        if project_id:
            update_data["project_id"] = project_id
        if session_id:
            update_data["session_id"] = session_id
        if thread_id:
            update_data["thread_id"] = thread_id
        
        if update_data:
            self._agent_context.update(update_data)
        
        logger.info(f"새 세션 리셋 완료: project_id={project_id}, session_id={session_id}, thread_id={thread_id}")

# 전역 인스턴스
tool_registry = ToolRegistry() 