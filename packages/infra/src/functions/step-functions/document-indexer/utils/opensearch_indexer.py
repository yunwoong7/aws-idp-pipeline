"""
OpenSearch 인덱싱 유틸리티
PDF에서 추출한 텍스트를 임베딩하여 OpenSearch에 인덱싱하는 기능 제공
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List

import boto3
from opensearchpy import OpenSearch, AWSV4SignerAuth, RequestsHttpConnection

logger = logging.getLogger(__name__)

class OpenSearchIndexer:
    """OpenSearch 인덱싱 클래스"""
    
    def __init__(self, endpoint: str, index_name: str, region: str = None):
        """
        OpenSearch 인덱서 초기화
        
        Args:
            endpoint: OpenSearch 엔드포인트
            index_name: 인덱스 이름
            region: AWS 리전 (기본값: 환경변수에서 가져옴)
        """
        self.endpoint = endpoint.rstrip('/')
        self.index_name = index_name
        self.region = region or boto3.Session().region_name
        
        # 호스트명 추출 (search-service와 동일한 방식)
        host = self.endpoint.replace('https://', '').replace('http://', '')
        
        # AWS 인증 설정
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, self.region, 'es')
        
        # OpenSearch 클라이언트 초기화 (search-service와 동일한 설정)
        self.client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,      
            connection_class=RequestsHttpConnection,
            timeout=30,  # search-service와 동일한 타임아웃
        )
        
        # Bedrock Runtime 클라이언트 (임베딩용)
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=self.region)
        
        # 인덱스 초기화 (실패 시 예외 발생)
        self._ensure_index_exists()
        logger.info(f"✅ OpenSearch 클라이언트 초기화 완료: {host}")
    
    def _ensure_index_exists(self):
        """인덱스가 존재하지 않으면 생성"""
        try:
            # 인덱스 존재 확인
            if not self.client.indices.exists(index=self.index_name):
                # 인덱스 생성
                self._create_index()
                logger.info(f"OpenSearch 인덱스 생성 완료: {self.index_name}")
            else:
                logger.info(f"OpenSearch 인덱스 존재 확인: {self.index_name}")
                
        except Exception as e:
            logger.error(f"OpenSearch 연결 실패: {str(e)}")
            raise Exception(f"OpenSearch 인덱스 확인/생성 실패: {str(e)}")
    
    def _create_index(self):
        """OpenSearch 인덱스 생성"""
        index_mapping = {
            "mappings": {
                "properties": {
                    "agent_analysis_id": {
                        "type": "keyword"
                    },
                    "project_id": {
                        "type": "keyword"
                    },
                    "document_id": {
                        "type": "keyword"
                    },
                    "page_id": {
                        "type": "keyword"
                    },
                    "page_index": {
                        "type": "integer"
                    },
                    "seq": {
                        "type": "integer"
                    },
                    "created_at": {
                        "type": "date",
                        "format": "strict_date_optional_time||epoch_millis"
                    },
                    "tool_name": {
                        "type": "keyword"
                    },
                    "file_uri": {
                        "type": "keyword"
                    },
                    "image_uri": {
                        "type": "keyword"
                    },
                    "analysis_query": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "vector_content": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib"
                        }
                    },
                    "analysis_summary": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "bda_analysis_id": {
                        "type": "keyword"
                    }
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "index.knn": True
            }
        }
        
        try:
            response = self.client.indices.create(
                index=self.index_name,
                body=index_mapping
            )
            
            logger.info(f"OpenSearch 인덱스 생성 완료: {self.index_name}")
                
        except Exception as e:
            logger.error(f"인덱스 생성 중 오류: {str(e)}")
            raise
    
    def _create_embedding(self, text: str) -> List[float]:
        """
        텍스트를 임베딩 벡터로 변환
        
        Args:
            text: 임베딩할 텍스트
            
        Returns:
            임베딩 벡터
        """
        try:
            # Titan Embeddings V2 모델 사용
            body = json.dumps({
                "inputText": text,
                "dimensions": 1024,
                "normalize": True
            })
            
            response = self.bedrock_runtime.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=body,
                contentType="application/json",
                accept="application/json"
            )
            
            response_body = json.loads(response['body'].read())
            embedding = response_body.get('embedding', [])
            
            logger.info(f"임베딩 생성 완료 - 텍스트 길이: {len(text)}, 벡터 차원: {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {str(e)}")
            # 빈 벡터 반환 (1024 차원)
            return [0.0] * 1024
    
    def index_bda_page(
        self,
        project_id: str,
        document_id: str,
        page_id: str,
        page_index: int,
        content: str,
        file_uri: str,
        image_uri: str = "",
        seq: int = 1
    ) -> bool:
        """
        페이지 텍스트를 OpenSearch에 인덱싱
        
        Args:
            project_id: 프로젝트 ID
            document_id: 문서 ID
            page_id: 페이지 ID
            page_index: 페이지 인덱스
            content: 분석 텍스트
            file_uri: 파일 URI
            image_uri: 이미지 URI
            seq: 단계 시퀀스
            
        Returns:
            인덱싱 성공 여부
        """
        try:
            # Agent 분석 ID 생성
            agent_analysis_id = str(uuid.uuid4())
            
            # 텍스트 임베딩 생성
            vector_content = self._create_embedding(content)
            
            # 문서 데이터 구성
            doc_data = {
                "agent_analysis_id": agent_analysis_id,
                "project_id": project_id,
                "document_id": document_id,
                "page_id": page_id,
                "page_index": page_index,
                "seq": seq,
                "created_at": datetime.utcnow().isoformat(),
                "tool_name": "bda_page_indexer",
                "file_uri": file_uri,
                "image_uri": image_uri,
                "analysis_query": "BDA 페이지 분석",
                "content": content,
                "vector_content": vector_content,
                "analysis_summary": "",
                "bda_analysis_id": ""
            }
            
            # OpenSearch에 문서 인덱싱
            response = self.client.index(
                index=self.index_name,
                id=agent_analysis_id,
                body=doc_data,
                refresh=True  # 즉시 검색 가능하도록
            )
            
            logger.info(f"OpenSearch 인덱싱 성공: {agent_analysis_id}")
            return True
                
        except Exception as e:
            logger.error(f"OpenSearch 인덱싱 중 오류: {str(e)}")
            return False
    
    def search_text(self, query: str, project_id: str = None, size: int = 10) -> Dict[str, Any]:
        """
        텍스트 검색
        
        Args:
            query: 검색 쿼리
            project_id: 프로젝트 ID (필터링용)
            size: 결과 개수
            
        Returns:
            검색 결과
        """
        try:
            # 검색 쿼리 구성
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["text_content", "document_title", "document_description"],
                                    "type": "best_fields"
                                }
                            }
                        ]
                    }
                },
                "highlight": {
                    "fields": {
                        "text_content": {},
                        "document_title": {},
                        "document_description": {}
                    }
                },
                "size": size,
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"indexed_at": {"order": "desc"}}
                ]
            }
            
            # 프로젝트 필터 추가
            if project_id:
                search_body["query"]["bool"]["filter"] = [
                    {"term": {"project_id": project_id}}
                ]
            
            # 검색 실행
            response = self.client.search(
                index=self.index_name,
                body=search_body
            )
            
            return response
                
        except Exception as e:
            logger.error(f"검색 중 오류: {str(e)}")
            return {"hits": {"hits": []}}
    
    def delete_document_pages(self, document_id: str) -> bool:
        """
        특정 문서의 모든 페이지 삭제
        
        Args:
            document_id: 문서 ID
            
        Returns:
            삭제 성공 여부
        """
        try:
            # 삭제 쿼리 구성
            delete_query = {
                "query": {
                    "term": {
                        "document_id": document_id
                    }
                }
            }
            
            # 문서 삭제
            response = self.client.delete_by_query(
                index=self.index_name,
                body=delete_query
            )
            
            deleted_count = response.get('deleted', 0)
            logger.info(f"문서 페이지 삭제 완료: {document_id}, 삭제된 페이지: {deleted_count}")
            return True
                
        except Exception as e:
            logger.error(f"문서 페이지 삭제 중 오류: {str(e)}")
            return False
    
    def get_index_stats(self) -> Dict[str, Any]:
        """
        인덱스 통계 조회
        
        Returns:
            인덱스 통계
        """
        try:
            response = self.client.indices.stats(
                index=self.index_name
            )
            
            return response
                
        except Exception as e:
            logger.error(f"인덱스 통계 조회 중 오류: {str(e)}")
            return {} 