"""
OpenSearch Indexing Utility
Provides functions to embed text extracted from PDF and index it into OpenSearch
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

import boto3
from opensearchpy import OpenSearch, AWSV4SignerAuth, RequestsHttpConnection

logger = logging.getLogger(__name__)

class OpenSearchIndexer:
    """OpenSearch Indexing Class"""
    
    def __init__(self, endpoint: str, index_name: str, region: str = None):
        """
        Initialize OpenSearch indexer
        
        Args:
            endpoint: OpenSearch endpoint
            index_name: Index name
            region: AWS region (default: from environment variable)
        """
        self.endpoint = endpoint.rstrip('/')
        self.index_name = index_name
        self.region = region or boto3.Session().region_name
        
        # Extract host name (same as search-service)
        host = self.endpoint.replace('https://', '').replace('http://', '')
        
        # AWS authentication setup
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, self.region, 'es')
        
        # Initialize OpenSearch client (same settings as search-service)
        self.client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,      
            connection_class=RequestsHttpConnection,
            timeout=30,  # search-service와 동일한 타임아웃
        )
        
        # Bedrock Runtime client (for embedding)
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=self.region)
        
        # Initialize index
        self._ensure_index_exists()
    
    def _ensure_index_exists(self):
        """Create index if it does not exist"""
        try:
            # 인덱스 존재 확인
            if not self.client.indices.exists(index=self.index_name):
                # 인덱스 생성
                self._create_index()
                logger.info(f"OpenSearch index created: {self.index_name}")
            else:
                logger.info(f"OpenSearch index exists: {self.index_name}")
                
        except Exception as e:
            logger.error(f"Index existence check failed: {str(e)}")
            # 인덱스 생성 시도
            try:
                self._create_index()
            except Exception as create_error:
                logger.error(f"Index creation failed: {str(create_error)}")
    
    def _create_index(self):
        """Create OpenSearch index"""
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
            
            logger.info(f"OpenSearch index created: {self.index_name}")
                
        except Exception as e:
            logger.error(f"Error creating index: {str(e)}")
            raise
    
    def _create_embedding(self, text: str) -> List[float]:
        """
        Convert text to embedding vector
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
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
            
            logger.info(f"Embedding created - text length: {len(text)}, vector dimension: {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding creation failed: {str(e)}")
            # 빈 벡터 반환 (1024 차원)
            return [0.0] * 1024
    
    def index_page_text(
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
        Index page text into OpenSearch
        
        Args:
            project_id: Project ID
            document_id: Document ID
            page_id: Page ID
            page_index: Page index
            content: Analysis text
            file_uri: File URI
            image_uri: Image URI
            seq: Step sequence
            
        Returns:
            Whether indexing succeeded
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
                "tool_name": "pdf_text_extractor",
                "file_uri": file_uri,
                "image_uri": image_uri,
                "analysis_query": "PDF 텍스트 추출",
                "content": content,
                "vector_content": vector_content,
                "analysis_summary": "",  # 비워둠
                "bda_analysis_id": ""    # 비워둠
            }
            
            # OpenSearch에 문서 인덱싱
            response = self.client.index(
                index=self.index_name,
                id=agent_analysis_id,
                body=doc_data
            )
            
            logger.info(f"OpenSearch indexing success: {agent_analysis_id}")
            return True
                
        except Exception as e:
            logger.error(f"Error during OpenSearch indexing: {str(e)}")
            return False
    
    def index_pdf_text(
        self,
        project_id: str,
        document_id: str,
        page_id: str,
        page_index: int,
        content: str,
        file_uri: str,
        image_uri: str = "",
        seq: int = 2
    ) -> bool:
        """
        Index text directly extracted from PDF into OpenSearch
        
        Args:
            project_id: Project ID
            document_id: Document ID
            page_id: Page ID
            page_index: Page index
            content: Text directly extracted from PDF
            file_uri: File URI
            image_uri: Image URI
            seq: Step sequence (default: 2, after BDA)
            
        Returns:
            Whether indexing succeeded
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
                "tool_name": "pdf_text_extractor",
                "file_uri": file_uri,
                "image_uri": image_uri,
                "analysis_query": "PDF 직접 텍스트 추출",
                "content": content,
                "vector_content": vector_content,
                "analysis_summary": f"PDF 페이지 {page_index + 1}에서 직접 추출한 텍스트",
                "bda_analysis_id": ""    # PDF 직접 추출이므로 비워둠
            }
            
            # OpenSearch에 문서 인덱싱
            response = self.client.index(
                index=self.index_name,
                id=agent_analysis_id,
                body=doc_data
            )
            
            logger.info(f"PDF text OpenSearch indexing success: {agent_analysis_id} (page {page_index + 1})")
            return True
                
        except Exception as e:
            logger.error(f"Error during PDF text OpenSearch indexing: {str(e)}")
            return False
    
    def search_text(self, query: str, project_id: Optional[str] = None, size: int = 10) -> Dict[str, Any]:
        """
        Search text
        
        Args:
            query: Search query
            project_id: Project ID (for filtering)
            size: Number of results
            
        Returns:
            Search results
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
                                    "fields": ["content", "analysis_query", "analysis_summary"],
                                    "type": "best_fields"
                                }
                            }
                        ]
                    }
                },
                "highlight": {
                    "fields": {
                        "content": {},
                        "analysis_query": {},
                        "analysis_summary": {}
                    }
                },
                "size": size,
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"created_at": {"order": "desc"}}
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
            logger.error(f"Error during search: {str(e)}")
            return {"hits": {"hits": []}}
    
    def delete_document_pages(self, document_id: str) -> bool:
        """
        Delete all pages of a specific document
        
        Args:
            document_id: Document ID
            
        Returns:
            Whether deletion succeeded
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
            logger.info(f"Document pages deletion complete: {document_id}, deleted pages: {deleted_count}")
            return True
                
        except Exception as e:
            logger.error(f"Error during document pages deletion: {str(e)}")
            return False
    
    def get_index_stats(self) -> Dict[str, Any]:
        """
        Retrieve index statistics
        
        Returns:
            Index statistics
        """
        try:
            response = self.client.indices.stats(
                index=self.index_name
            )
            
            return response
                
        except Exception as e:
            logger.error(f"Error retrieving index statistics: {str(e)}")
            return {} 