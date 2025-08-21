"""
OpenSearch Service for unified search and indexing operations.
"""

import boto3
from opensearchpy import OpenSearch
from typing import Dict, List, Any, Optional, Union
import json
import logging
import os
from datetime import datetime

from .aws_clients import AWSClientFactory
from .dynamodb_service import DynamoDBService
from .utils import get_current_timestamp, generate_uuid

logger = logging.getLogger(__name__)


class OpenSearchService:
    """Unified service for all OpenSearch operations."""
    
    def __init__(self, 
                 endpoint: Optional[str] = None,
                 index_name: Optional[str] = None,
                 region: Optional[str] = None):
        self.endpoint = endpoint or os.environ.get('OPENSEARCH_ENDPOINT')
        self.index_name = index_name or os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis')
        self.region = region or os.environ.get('AWS_REGION', 'us-west-2')
        
        # Search pipeline configuration (optimized weights)
        self.search_pipeline_name = f"{self.index_name}-hybrid-search-pipeline"
        self.keyword_weight = 0.6  # Increased keyword weight for better precision
        self.vector_weight = 0.4   # Reduced vector weight
        
        # Search threshold score configuration (optimized)
        self.search_threshold_score = float(os.environ.get('SEARCH_THRESHOLD_SCORE', '0.3'))  # 0.4 → 0.3으로 감소
        
        if not self.endpoint:
            raise ValueError("OpenSearch endpoint is required")
        
        self.client = AWSClientFactory.get_opensearch_client(self.endpoint, self.region)
        self.bedrock_runtime = AWSClientFactory.get_bedrock_runtime_client(self.region)
        
        # Initialize index if it doesn't exist
        self._ensure_index_exists()
        
        # Setup search pipeline for hybrid search
        self._setup_search_pipeline()
    
    def _ensure_index_exists(self):
        """Create index with proper mapping if it doesn't exist."""
        max_retries = 3
        retry_delay = 3  # seconds
        
        for attempt in range(max_retries):
            try:
                if not self.client.indices.exists(index=self.index_name):
                    self._create_index()
                    logger.info(f"Created OpenSearch index: {self.index_name}")
                else:
                    logger.info(f"OpenSearch index exists: {self.index_name}")
                return  # Success, exit retry loop
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {error_msg}")
                
                if attempt < max_retries - 1:
                    # Collection might still be initializing, wait and retry
                    if "IllegalArgumentException" in error_msg or "403" in error_msg or "AuthorizationException" in error_msg:
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        # Different error, don't retry
                        break
                else:
                    # Final attempt failed
                    logger.error(f"Failed to check/create index after {max_retries} attempts: {error_msg}")
                    raise
    
    def _setup_search_pipeline(self):
        """OpenSearch 검색 파이프라인을 설정합니다."""
        pipeline_body = {
            "description": "AWS IDP AI Analysis hybrid search pipeline",
            "phase_results_processors": [
                { 
                    "normalization-processor": {
                        "normalization": {
                            "technique": "min_max"
                        },
                        "combination": {
                            "technique": "arithmetic_mean",
                            "parameters": {
                                "weights": [
                                    self.keyword_weight, 
                                    self.vector_weight
                                ]  # 텍스트:0.4, 벡터:0.6 가중치
                            }
                        }
                    }
                }
            ]
        }

        try:
            # 파이프라인 생성 또는 업데이트
            self.client.transport.perform_request(
                'PUT',
                f'/_search/pipeline/{self.search_pipeline_name}',
                body=pipeline_body
            )
            logger.info(f"검색 파이프라인이 성공적으로 생성되었습니다: {self.search_pipeline_name}")
            return True
        except Exception as e:
            logger.warning(f"검색 파이프라인 생성 중 오류 발생: {str(e)} (계속 진행)")
            # 파이프라인 생성 실패는 전체 서비스를 중단하지 않음
            return False
    
    def _create_index(self, custom_index_name: Optional[str] = None):
        """Create index with proper mapping and settings.
        
        Args:
            custom_index_name: Optional custom index name. If not provided, uses self.index_name
        """
        index_name_to_create = custom_index_name or self.index_name
        index_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "knn": True,
                "knn.algo_param.ef_search": 100
            },
            "mappings": {
                "properties": {
                    # Source fields
                    "agent_analysis_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "segment_id": {"type": "keyword"},
                    "segment_index": {"type": "integer"},
                    "media_type": {"type": "keyword"},  # DOCUMENT, VIDEO 등 미디어 타입
                    "created_at": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"},
                    "updated_at": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"},
                    "file_uri": {"type": "keyword"},
                    "image_uri": {"type": "keyword"},     
                    # Content fields
                    "content_combined": {"type": "text", "analyzer": "standard"},
                    # User content field
                    "user_content": {
                        "type": "nested",
                        "properties": {
                            "content": {"type": "text", "analyzer": "standard"},
                            "created_at": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"}
                        }
                    },
                    # Tools fields
                    "tools": {
                        "type": "object",
                        "properties": {
                            "bda_indexer": {
                                "type": "nested",
                                "properties": {
                                    "content": {"type": "text", "analyzer": "standard"},
                                    "analysis_query": {"type": "text", "analyzer": "standard"},
                                    "created_at": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"},
                                    "elements": {
                                        "type": "nested",
                                        "properties": {
                                            "summary": {"type": "text", "analyzer": "standard"},
                                            "reading_order": {"type": "integer"},
                                            "sub_type": {"type": "keyword"},
                                            "page_indices": {"type": "integer"},
                                            "crop_images": {"type": "keyword"},
                                            "id": {"type": "keyword"},
                                            "type": {"type": "keyword"},
                                            "title": {"type": "text", "analyzer": "standard"},
                                            "locations": {
                                                "type": "nested",
                                                "properties": {
                                                    "bounding_box": {
                                                        "type": "object",
                                                        "properties": {
                                                            "top": {"type": "float"},
                                                            "left": {"type": "float"},
                                                            "width": {"type": "float"},
                                                            "height": {"type": "float"}
                                                        }
                                                    },
                                                    "page_index": {"type": "integer"}
                                                }
                                            },
                                            "representation": {
                                                "type": "object",
                                                "properties": {
                                                    "markdown": {"type": "text", "analyzer": "standard"}
                                                }
                                            }
                                        }
                                    },
                                    "frames": {
                                        "type": "nested",
                                        "properties": {
                                            "timecode_smpte": {"type": "keyword"},
                                            "timestamp_millis": {"type": "long"},
                                            "text_words": {
                                                "type": "nested",
                                                "properties": {
                                                    "text": {"type": "text", "analyzer": "standard"}
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                            "pdf_text_extractor": {
                                "type": "nested",
                                "properties": {
                                    "content": {"type": "text", "analyzer": "standard"},
                                    "analysis_query": {"type": "text", "analyzer": "standard"},
                                    "created_at": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"}
                                }
                            },
                            "ai_analysis": {
                                "type": "nested",
                                "properties": {
                                    "analysis_type": {"type": "keyword"},  # "image_analyzer", "video_analyzer", etc.
                                    "analysis_query": {"type": "text", "analyzer": "standard"},
                                    "content": {"type": "text", "analyzer": "standard"},
                                    "metadata": {
                                        "type": "object",
                                        "properties": {
                                            "model_version": {"type": "keyword"},
                                            "analysis_steps": {"type": "keyword"},
                                            "start_timecode_smpte": {"type": "keyword"},  # For video analysis
                                            "end_timecode_smpte": {"type": "keyword"},    # For video analysis
                                            "segment_type": {"type": "keyword"}           # For video segments
                                        }
                                    },
                                    "created_at": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"}
                                }
                            }
                        }
                    },
                    
                    # Vector embeddings field
                    "vector_content": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 24
                            }
                        }
                    }
                }
            }
        }
        
        self.client.indices.create(index=index_name_to_create, body=index_body)
    
    def create_index_for_id(self, index_id: str) -> bool:
        """Create OpenSearch index for a specific index_id.
        
        Args:
            index_id: The index ID from the DynamoDB indices table
            
        Returns:
            bool: True if index was created successfully, False otherwise
        """
        try:
            # Get index information from DynamoDB indices table
            index_info = self._get_index_info_from_dynamodb(index_id)
            if not index_info:
                logger.error(f"Index ID '{index_id}' not found in indices table")
                return False
            
            # Use index_id as-is for OpenSearch index name (user input)
            index_name = index_id
            
            # Check if index already exists
            if self.client.indices.exists(index=index_name):
                logger.warning(f"OpenSearch index '{index_name}' already exists for index_id '{index_id}'")
                return True
            
            # Create the index
            self._create_index(custom_index_name=index_name)
            
            # Update DynamoDB indices table with the created index name
            self._update_index_info_in_dynamodb(index_id, index_name)
            
            logger.info(f"Successfully created OpenSearch index '{index_name}' for index_id '{index_id}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index for index_id '{index_id}': {str(e)}")
            return False
    
    def delete_index_for_id(self, index_id: str) -> bool:
        """Delete OpenSearch index for a specific index_id.
        
        Args:
            index_id: The index ID from the DynamoDB indices table
            
        Returns:
            bool: True if index was deleted successfully, False otherwise
        """
        try:
            # Get index information from DynamoDB indices table
            index_info = self._get_index_info_from_dynamodb(index_id)
            if not index_info:
                logger.error(f"Index ID '{index_id}' not found in indices table")
                return False
            
            # Use index_id as-is for OpenSearch index name (user input)
            index_name = index_id
            
            # Check if index exists
            if not self.client.indices.exists(index=index_name):
                logger.warning(f"OpenSearch index '{index_name}' does not exist for index_id '{index_id}'")
                return True
            
            # Delete the index
            self.client.indices.delete(index=index_name)
            
            logger.info(f"Successfully deleted OpenSearch index '{index_name}' for index_id '{index_id}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete index for index_id '{index_id}': {str(e)}")
            return False
    
    def _get_index_info_from_dynamodb(self, index_id: str) -> Optional[Dict[str, Any]]:
        """Get index information from DynamoDB indices table."""
        try:
            db = DynamoDBService()
            item = db.get_item('indices', {'index_id': index_id})
            return item
        except Exception as e:
            logger.error(f"Failed to get index info from DynamoDB for index_id '{index_id}': {str(e)}")
            return None
    
    def _update_index_info_in_dynamodb(self, index_id: str, index_name: str) -> bool:
        """Update index information in DynamoDB indices table with the created OpenSearch index name."""
        try:
            db = DynamoDBService()
            db.update_item(
                table_name='indices',
                key={'index_id': index_id},
                update_expression='SET index_name = :name',
                expression_attribute_values={
                    ':name': index_name,
                }
            )
            logger.info(f"Updated DynamoDB indices table with index_name '{index_name}' for index_id '{index_id}'")
            return True
        except Exception as e:
            logger.error(f"Failed to update DynamoDB indices table for index_id '{index_id}': {str(e)}")
            return False
    
    
    def _get_os_id_from_segments_table(self, segment_id: str) -> Optional[str]:
        """Fetch stored OpenSearch _id for the given segment_id from DynamoDB segments table."""
        try:
            db = DynamoDBService()
            item = db.get_item('segments', {'segment_id': segment_id})
            if item and 'opensearch_id' in item:
                return item['opensearch_id']
            return None
        except Exception as e:
            logger.debug(f"Failed to read opensearch_id from segments table for {segment_id}: {str(e)}")
            return None

    def _set_os_id_for_page(self, segment_id: str, os_id: str) -> None:
        """Persist OpenSearch _id mapping to DynamoDB segments table for fast lookups."""
        try:
            db = DynamoDBService()
            db.update_item(
                table_name='segments',
                key={'segment_id': segment_id},
                update_expression='SET opensearch_id = :osid, updated_at = :u',
                expression_attribute_values={
                    ':osid': os_id,
                    ':u': get_current_timestamp(),
                }
            )
        except Exception as e:
            logger.debug(f"Failed to persist opensearch_id for {segment_id}: {str(e)}")
    
    def generate_embeddings(self, text: str) -> List[float]:
        """Generate embeddings using Amazon Titan Embeddings V2."""
        try:
            # Truncate text if too long (Titan has limits)
            if len(text) > 8000:
                text = text[:8000]
            
            body = json.dumps({
                "inputText": text,
                "dimensions": 1024,
                "normalize": True
            })
            
            response = self.bedrock_runtime.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=body,
                contentType="application/json"
            )
            
            response_body = json.loads(response['body'].read())
            embeddings = response_body.get('embedding', [])
            
            logger.info(f"Generated embeddings for text length: {len(text)}")
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {str(e)}")
            raise
    
    def index_document(self, index_id: str, document: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """Index a document with automatic embedding generation."""
        try:
            # Add timestamps
            timestamp = get_current_timestamp()
            document['created_at'] = timestamp
            document['updated_at'] = timestamp
            
            # Generate embeddings for content
            content = document.get('content', '')
            if content:
                document['vector_content'] = self.generate_embeddings(content)
            
            # Index document
            response = self.client.index(
                index=index_id,
                id=doc_id,
                body=document,
                refresh=True
            )
            
            doc_id = response['_id']
            logger.info(f"Indexed document: {doc_id}")
            return doc_id
            
        except Exception as e:
            logger.error(f"Failed to index document: {str(e)}")
            raise
    
    # ==================== NEW PAGE-UNIT STORAGE METHODS ====================
    def get_segment_document(self, index_id: str, segment_id: str) -> Optional[Dict[str, Any]]:
        """Get existing page document by segment_id and include internal _id for updates."""
        try:
            # Prefer DynamoDB mapping to avoid search and eventual consistency issues
            mapped_os_id = self._get_os_id_from_segments_table(segment_id)
            if mapped_os_id:
                try:
                    # Always use provided index_id for consistency
                    doc = self.client.get(index=index_id, id=mapped_os_id)
                    source = doc.get('_source', {})
                    source['_opensearch_id'] = mapped_os_id
                    return source
                except Exception as get_err:
                    logger.debug(f"Direct get by mapped id failed for {segment_id}: {str(get_err)}. Falling back to search.")
            # Use search instead of get for OpenSearch Serverless compatibility
            query = {
                "query": {
                    "term": {
                        "segment_id": segment_id
                    }
                },
                "size": 1
            }
            
            response = self.client.search(
                index=index_id,
                body=query
            )
            
            hits = response.get('hits', {}).get('hits', [])
            if hits:
                hit = hits[0]
                source = hit.get('_source', {})
                # Attach internal _id for follow-up update operations
                source['_opensearch_id'] = hit.get('_id')
                return source
            return None
        except Exception as e:
            logger.warning(f"Failed to get page document {segment_id}: {str(e)}")
            return None
    
    def create_segment_document(self,
                           index_id: str,
                           document_id: str,
                           segment_id: str,
                           segment_index: int,
                           file_uri: str = "",
                           image_uri: str = "",
                           media_type: str = "DOCUMENT") -> str:
        """Create a new page document with tools structure."""

        timestamp = get_current_timestamp()

        document = {
            "segment_id": segment_id,
            "document_id": document_id,
            "segment_index": segment_index,
            "media_type": media_type,
            "file_uri": file_uri,
            "image_uri": image_uri,
            "tools": {
                "bda_indexer": [],
                "pdf_text_extractor": [],
                "ai_analysis": []
            },
            "updated_at": timestamp,
            "created_at": timestamp
        }
        
        response = self.client.index(
            index=index_id,
            id=segment_id,
            body=document,
            refresh=True
        )
        
        logger.info(f"Created page document: {segment_id}")
        os_id = response['_id']
        # Persist mapping for future updates
        self._set_os_id_for_page(segment_id, os_id)
        return os_id
    
    def add_bda_indexer_tool(self,
                           index_id: str,
                           document_id: str, 
                           segment_id: str,
                           segment_index: int,
                           content: str,
                           file_uri: str = "",
                           image_uri: str = "",
                           elements: List[Dict[str, Any]] = None,
                           media_type: str = "DOCUMENT") -> bool:
        """Add bda_indexer tool result to page document."""
        try:
            # Get or create page document
            segment_doc = self.get_segment_document(index_id, segment_id)
            if segment_doc is None:
                self.create_segment_document(index_id, document_id, segment_id, segment_index, file_uri, image_uri, media_type)
                segment_doc = self.get_segment_document(index_id, segment_id)
            
            # Create bda_indexer tool entry
            bda_tool = {
                "content": content,
                "analysis_query": "BDA 페이지 분석 결과",
                "created_at": get_current_timestamp()
            }
            
            # Add elements if provided (exclude PARAGRAPH and PAGE_NUMBER sub types)
            if elements:
                filtered_elements = [
                    element for element in elements 
                    if element.get('sub_type', '') not in ['PARAGRAPH', 'PAGE_NUMBER']
                ]
                bda_tool["elements"] = filtered_elements
            
            # Add to tools.bda_indexer array
            segment_doc['tools']['bda_indexer'].append(bda_tool)
            segment_doc['updated_at'] = get_current_timestamp()

            # Update document
            response = self.client.update(
                index=index_id,
                id=segment_id,
                body={"doc": segment_doc},
                refresh=True
            )
            
            logger.info(f"Added bda_indexer tool to page: {segment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add bda_indexer tool to page {segment_id}: {str(e)}")
            raise
    
    def add_pdf_text_extractor_tool(self,
                                   index_id: str,
                                   document_id: str,
                                   segment_id: str,
                                   segment_index: int, 
                                   content: str,
                                   media_type: str = "DOCUMENT") -> bool:
        """Add pdf_text_extractor tool result to page document."""
        try:
            # Get or create page document
            segment_doc = self.get_segment_document(index_id, segment_id)
            if segment_doc is None:
                self.create_segment_document(index_id, document_id, segment_id, segment_index, media_type=media_type)
                segment_doc = self.get_segment_document(index_id, segment_id)
            
            # Create pdf_text_extractor tool entry
            pdf_tool = {
                "content": content,
                "analysis_query": "PDF 직접 텍스트 추출",
                "created_at": get_current_timestamp()
            }
            
            # Add to tools.pdf_text_extractor array
            segment_doc['tools']['pdf_text_extractor'].append(pdf_tool)
            segment_doc['updated_at'] = get_current_timestamp()
            
            # Update document
            response = self.client.update(
                index=index_id,
                id=segment_id,
                body={"doc": segment_doc},
                refresh=True
            )
            
            logger.info(f"Added pdf_text_extractor tool to segment: {segment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add pdf_text_extractor tool to segment {segment_id}: {str(e)}")
            raise
    
    def add_ai_analysis_tool(self,
                           index_id: str,
                           document_id: str,
                           segment_id: str,
                           segment_index: int,
                           analysis_type: str,  # "image_analyzer", "video_analyzer", final_ai_response.
                           analysis_query: str,
                           content: str,
                           analysis_steps: str = "1",
                           model_version: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                           start_timecode_smpte: str = None,
                           end_timecode_smpte: str = None,
                           segment_type: str = None,
                           media_type: str = "DOCUMENT") -> bool:
        """Add AI analysis tool result (image, video, etc.) to segment document."""
        try:
            # Get or create page document
            segment_doc = self.get_segment_document(index_id, segment_id)
            if segment_doc is None:
                self.create_segment_document(index_id, document_id, segment_id, segment_index, media_type=media_type)
                segment_doc = self.get_segment_document(index_id, segment_id)
            
            # Create AI analysis tool entry
            analysis_tool = {
                "analysis_type": analysis_type,
                "analysis_query": analysis_query,
                "content": content,
                "metadata": {
                    "model_version": model_version,
                    "analysis_steps": analysis_steps
                },
                "created_at": get_current_timestamp()
            }
            
            # Add video-specific metadata if provided
            if start_timecode_smpte:
                analysis_tool["metadata"]["start_timecode_smpte"] = start_timecode_smpte
            if end_timecode_smpte:
                analysis_tool["metadata"]["end_timecode_smpte"] = end_timecode_smpte
            if segment_type:
                analysis_tool["metadata"]["segment_type"] = segment_type
            
            # Add to tools.ai_analysis array
            segment_doc['tools']['ai_analysis'].append(analysis_tool)
            segment_doc['updated_at'] = get_current_timestamp()
            
            # Update document
            response = self.client.update(
                index=index_id,
                id=segment_id,
                body={"doc": segment_doc},
                refresh=True
            )
            
            logger.info(f"Added {analysis_type} AI analysis tool to segment: {segment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add {analysis_type} AI analysis tool to segment {segment_id}: {str(e)}")
            raise
    
    def get_segment_tools_content(self, index_id: str, segment_id: str) -> Optional[str]:
        """Get combined content from all tools in a segment for embedding generation."""
        try:
            segment_doc = self.get_segment_document(index_id, segment_id)
            if not segment_doc:
                return None
            
            content_parts = []
            tools = segment_doc.get('tools', {})
            
            # Add bda_indexer content
            for bda_tool in tools.get('bda_indexer', []):
                content = bda_tool.get('content', '')
                if content:
                    content_parts.append(f"BDA 인덱서: {content}")
            
            # Add pdf_text_extractor content
            for pdf_tool in tools.get('pdf_text_extractor', []):
                content = pdf_tool.get('content', '')
                if content:
                    content_parts.append(f"PDF 텍스트: {content}")
            
            # Add ai_analysis content (images, videos, etc.)
            for ai_tool in tools.get('ai_analysis', []):
                content = ai_tool.get('content', '')
                analysis_query = ai_tool.get('analysis_query', '')
                analysis_type = ai_tool.get('analysis_type', 'AI')
                if content:
                    if analysis_query:
                        content_parts.append(f"{analysis_type} 분석 ({analysis_query}): {content}")
                    else:
                        content_parts.append(f"{analysis_type} 분석: {content}")
            
            # Add user content
            user_content_list = segment_doc.get('user_content', [])
            if user_content_list:
                for user_item in user_content_list:
                    content = user_item.get('content', '')
                    created_at = user_item.get('created_at', '')
                    if content:
                        content_parts.append(f"사용자 입력 ({created_at}): {content}")
            
            return '\n\n'.join(content_parts) if content_parts else None
            
        except Exception as e:
            logger.error(f"Failed to get segment tools content for {segment_id}: {str(e)}")
            return None
    
    def update_segment_embeddings(self, index_id: str, segment_id: str, content_combined: str = None) -> bool:
        """Update embeddings for page document based on combined tools content."""
        try:
            # 외부에서 content_combined를 제공하면 사용, 아니면 내부에서 생성
            if content_combined:
                content = content_combined
                logger.info(f"Using provided content_combined: {len(content)} characters")
            else:
                content = self.get_segment_tools_content(index_id, segment_id)
                logger.info(f"Generated content from tools: {len(content)} characters")
            
            if not content:
                logger.warning(f"No content found for segment {segment_id} - skipping embedding update")
                return False
            
            # Generate embeddings
            embeddings = self.generate_embeddings(content)
            
            # Update page document with embeddings and combined content
            updates = {
                'content_combined': content,
                'vector_content': embeddings,
                'updated_at': get_current_timestamp()
            }
            
            os_id_doc = self.get_segment_document(index_id, segment_id)
            os_id = os_id_doc.get('_opensearch_id') if os_id_doc else None
            # Fallback to segment_id if internal _id mapping is not available
            target_id = os_id or segment_id
            response = self.client.update(
                index=index_id,
                id=target_id,
                body={"doc": updates},
                refresh=True
            )
            
            logger.info(f"Updated embeddings for segment: {segment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update embeddings for segment {segment_id}: {str(e)}")
            raise
    
    def add_user_content(self,
                        index_id: str,
                        segment_id: str,
                        document_id: str,
                        segment_index: int,
                        content: str,
                        media_type: str = "DOCUMENT") -> bool:
        """Add user content to page document."""
        try:
            # Get or create page document
            segment_doc = self.get_segment_document(index_id, segment_id)
            if segment_doc is None:
                self.create_segment_document(index_id, document_id, segment_id, segment_index, media_type=media_type)
                segment_doc = self.get_segment_document(index_id, segment_id)
            
            # Create user content entry
            user_entry = {
                "content": content,
                "created_at": get_current_timestamp()
            }
            
            # Initialize user_content array if it doesn't exist
            if 'user_content' not in segment_doc:
                segment_doc['user_content'] = []
            
            # Add to user_content array
            segment_doc['user_content'].append(user_entry)
            segment_doc['updated_at'] = get_current_timestamp()
            
            # Update document
            response = self.client.update(
                index=index_id,
                id=segment_id,
                body={"doc": segment_doc},
                refresh=True
            )
            
            logger.info(f"Added user content to segment: {segment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add user content to segment {segment_id}: {str(e)}")
            raise
    
    def remove_user_content(self,
                           index_id: str,
                           segment_id: str,
                           content_index: int) -> bool:
        """Remove specific user content by index from page document."""
        try:
            segment_doc = self.get_segment_document(index_id, segment_id)
            if not segment_doc:
                logger.warning(f"Segment document not found: {segment_id}")
                return False
            
            user_content_list = segment_doc.get('user_content', [])
            if content_index >= len(user_content_list) or content_index < 0:
                logger.warning(f"Invalid content index {content_index} for segment {segment_id}")
                return False
            
            # Remove the content at specified index
            user_content_list.pop(content_index)
            segment_doc['user_content'] = user_content_list
            segment_doc['updated_at'] = get_current_timestamp()
            
            # Update document
            response = self.client.update(
                index=index_id,
                id=segment_id,
                body={"doc": segment_doc},
                refresh=True
            )
            
            logger.info(f"Removed user content at index {content_index} from segment: {segment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove user content from segment {segment_id}: {str(e)}")
            raise
    
    # ==================== END PAGE-UNIT STORAGE METHODS ====================
    
    # def update_document(self, index_id: str, doc_id: str, updates: Dict[str, Any]) -> bool:
    #     """Update an existing document."""
    #     try:
    #         updates['updated_at'] = get_current_timestamp()
            
    #         # Generate new embeddings if content updated
    #         if 'content' in updates and updates['content']:
    #             updates['vector_content'] = self.generate_embeddings(updates['content'])
            
    #         response = self.client.update(
    #             index=index_id,
    #             id=doc_id,
    #             body={"doc": updates},
    #             refresh=True
    #         )
            
    #         logger.info(f"Updated document: {doc_id}")
    #         return True
            
    #     except Exception as e:
    #         logger.error(f"Failed to update document {doc_id}: {str(e)}")
    #         raise
    
    # def delete_document(self, index_id: str, doc_id: str) -> bool:
    #     """Delete a document from the index."""
    #     try:
    #         response = self.client.delete(
    #             index=index_id,
    #             id=doc_id,
    #             refresh=True
    #         )
            
    #         logger.info(f"Deleted document: {doc_id}")
    #         return True
            
    #     except Exception as e:
    #         logger.error(f"Failed to delete document {doc_id}: {str(e)}")
    #         raise
    
    def search_text(self,
                   index_id: str,
                   query: str,
                   size: int = 10,
                   filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform text-based search."""
        try:
            # Query configuration
            if query == "*":
                # Get all documents
                query_clause = {"match_all": {}}
            else:
                # Text search (legacy fields + new page-unit fields)
                query_clause = {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "content^2", "analysis_summary", "analysis_query",
                            "content_combined^3",
                            "tools.bda_indexer.content",
                            "tools.pdf_text_extractor.content", 
                            "tools.ai_analysis.content",
                            "tools.ai_analysis.analysis_query"
                        ],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                }
            
            search_body = {
                "size": size,
                "query": {
                    "bool": {
                        "must": [query_clause]
                    }
                },
                "highlight": {
                    "fields": {
                        "content": {},
                        "analysis_summary": {},
                        "content_combined": {},
                        "tools.bda_indexer.content": {},
                        "tools.pdf_text_extractor.content": {},
                        "tools.ai_analysis.content": {}
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"created_at": {"order": "desc"}}
                ]
            }
            
            # Add filters
            filter_conditions = []
            if filters:
                for field, value in filters.items():
                    if value:  # Add filter only if value exists
                        filter_conditions.append({"term": {field: value}})
            
            if filter_conditions:
                search_body["query"]["bool"]["filter"] = filter_conditions
            
            # Improved logging
            logger.info(f"OpenSearch search started:")
            logger.info(f"  - Index: {index_id}")
            logger.info(f"  - Query: {query}")
            logger.info(f"  - Size: {size}")
            logger.info(f"  - Filters: {filters}")
            logger.info(f"  - Search body: {json.dumps(search_body, indent=2)}")
            
            response = self.client.search(
                index=index_id,
                body=search_body
            )
            
            # Apply score threshold filtering
            response = self._filter_results_by_score_threshold(response)
            
            result_count = len(response['hits']['hits'])
            logger.info(f"Text search returned {result_count} results")
            
            # Additional debugging if no results
            if result_count == 0:
                logger.info("No results found. Debug info:")
                
                # Check total document count
                total_count_response = self.client.count(index=index_id)
                total_docs = total_count_response.get('count', 0)
                logger.info(f"  - Total document count: {total_docs}")
                
                # Check document count per filter
                if filters:
                    for field, value in filters.items():
                        if value:
                            field_count_response = self.client.count(
                                index=index_id,
                                body={"query": {"term": {field: value}}}
                            )
                            field_docs = field_count_response.get('count', 0)
                            logger.info(f"  - {field}={value} document count: {field_docs}")
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to perform text search: {str(e)}")
            raise
    
    def search_vector(self, 
                     index_id: str,
                     query_text: str,
                     size: int = 10,
                     filters: Optional[Dict[str, Any]] = None,
                     ) -> Dict[str, Any]:
        """Perform vector-based semantic search."""
        try:
            # Generate query embeddings
            query_vector = self.generate_embeddings(query_text)
            
            search_body = {
                "size": size,
                "query": {
                    "knn": {
                        "vector_content": {
                            "vector": query_vector,
                            "k": size * 2
                        }
                    }
                }
            }
            
            # Add filters
            filter_conditions = []
            if filters:
                for field, value in filters.items():
                    filter_conditions.append({"term": {field: value}})
            
            if filter_conditions:
                # Wrap knn query in bool query for filtering
                search_body["query"] = {
                    "bool": {
                        "must": [search_body["query"]],
                        "filter": filter_conditions
                    }
                }
            
            response = self.client.search(
                index=index_id,
                body=search_body
            )
            
            # Apply score threshold filtering
            response = self._filter_results_by_score_threshold(response)
            
            logger.info(f"Vector search returned {len(response['hits']['hits'])} results")
            return response
            
        except Exception as e:
            logger.error(f"Failed to perform vector search: {str(e)}")
            raise
    
    def hybrid_search(self, 
                     index_id: str,
                     query: str,
                     size: int = 10,
                     text_weight: float = None,
                     vector_weight: float = None,
                     filters: Optional[Dict[str, Any]] = None,
                     ) -> Dict[str, Any]:
        """Perform hybrid search using search pipeline for optimal performance."""
        try:
            # Use default weights if not provided
            if text_weight is None:
                text_weight = self.keyword_weight
            if vector_weight is None:
                vector_weight = self.vector_weight
            
            # Generate query embeddings
            query_vector = self.generate_embeddings(query)
            
            # Build filter conditions for hybrid query
            filter_conditions = []
            if filters:
                for field, value in filters.items():
                    filter_conditions.append({"term": {field: value}})
            
            # Build text query with filters (optimized for performance)
            text_query = {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "content_combined^5",  # Primary search field with highest boost
                        "tools.bda_indexer.content^2",
                        "tools.pdf_text_extractor.content^2", 
                        "tools.ai_analysis.content^2",
                        "user_content.content^2"  # User content field
                    ],
                    "type": "best_fields",
                    "fuzziness": "1",  # Reduced fuzziness for better performance
                    "tie_breaker": 0.2
                }
            }
            
            # Build vector query with filters (optimized k value)
            vector_query = {
                "knn": {
                    "vector_content": {
                        "vector": query_vector,
                        "k": min(size * 2, 50)  # Limit k to max 50 for better performance
                    }
                }
            }
            
            # Apply filters to each query if any
            if filter_conditions:
                text_query = {
                    "bool": {
                        "must": [text_query],
                        "filter": filter_conditions
                    }
                }
                vector_query = {
                    "bool": {
                        "must": [vector_query],
                        "filter": filter_conditions
                    }
                }
            
            # Hybrid search query for pipeline (must be top-level)
            search_body = {
                "size": size,
                "query": {
                    "hybrid": {
                        "queries": [text_query, vector_query]
                    }
                },
                "highlight": {
                    "fields": {
                        "content": {},
                        "analysis_summary": {},
                        "content_combined": {},
                        "tools.bda_indexer.content": {},
                        "tools.pdf_text_extractor.content": {},
                        "tools.ai_analysis.content": {},
                        "user_content.content": {}
                    }
                },
                "sort": [{"_score": {"order": "desc"}}]
            }
            
            # Execute search with pipeline
            try:
                response = self.client.search(
                    index=index_id,
                    body=search_body,
                    params={"search_pipeline": self.search_pipeline_name}
                )
                logger.info(f"Hybrid search with pipeline returned {len(response['hits']['hits'])} results")
            except Exception as pipeline_error:
                logger.warning(f"Pipeline search failed: {str(pipeline_error)}, falling back to direct search")
                # Fallback to direct search without pipeline
                response = self.client.search(
                    index=index_id,
                    body=search_body
                )
                logger.info(f"Hybrid search fallback returned {len(response['hits']['hits'])} results")
            
            # Apply score threshold filtering
            response = self._filter_results_by_score_threshold(response)
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to perform hybrid search: {str(e)}")
            raise
    
    def delete_by_query(self, index_id: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Delete documents matching the specified filters."""
        try:
            query_body = {
                "query": {
                    "bool": {
                        "filter": []
                    }
                }
            }
            
            for field, value in filters.items():
                query_body["query"]["bool"]["filter"].append({"term": {field: value}})
            
            response = self.client.delete_by_query(
                index=index_id,
                body=query_body,
                refresh=True
            )
            
            deleted_count = response.get('deleted', 0)
            logger.info(f"Deleted {deleted_count} documents matching filters: {filters}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to delete by query: {str(e)}")
            raise
    
    def get_document_count(self, index_id: str, filters: Optional[Dict[str, Any]] = None) -> int:
        """Get count of documents in index."""
        try:
            if filters:
                query_body = {
                    "query": {
                        "bool": {
                            "filter": []
                        }
                    }
                }
                
                for field, value in filters.items():
                    query_body["query"]["bool"]["filter"].append({"term": {field: value}})
                
                response = self.client.count(
                    index=self.index_name,
                    body=query_body
                )
            else:
                response = self.client.count(index=index_id)
            
            count = response.get('count', 0)
            logger.info(f"Document count: {count}")
            return count
            
        except Exception as e:
            logger.error(f"Failed to get document count: {str(e)}")
            raise
    
    def update_search_pipeline_weights(self, keyword_weight: float = 0.4, vector_weight: float = 0.6) -> bool:
        """Update search pipeline weights."""
        try:
            self.keyword_weight = keyword_weight
            self.vector_weight = vector_weight
            
            # Reset pipeline
            return self._setup_search_pipeline()
            
        except Exception as e:
            logger.error(f"Failed to update search pipeline weights: {str(e)}")
            raise
    
    def get_search_pipeline_info(self) -> Dict[str, Any]:
        """Get search pipeline info."""
        try:
            response = self.client.transport.perform_request(
                'GET',
                f'/_search/pipeline/{self.search_pipeline_name}'
            )
            
            pipeline_info = {
                "pipeline_name": self.search_pipeline_name,
                "keyword_weight": self.keyword_weight,
                "vector_weight": self.vector_weight,
                "exists": True,
                "configuration": response
            }
            
            logger.info(f"Search pipeline info retrieved: {self.search_pipeline_name}")
            return pipeline_info
            
        except Exception as e:
            logger.warning(f"Failed to get search pipeline info: {str(e)}")
            return {
                "pipeline_name": self.search_pipeline_name,
                "keyword_weight": self.keyword_weight,
                "vector_weight": self.vector_weight,
                "exists": False,
                "error": str(e)
            }
    
    def delete_search_pipeline(self) -> bool:
        """Delete search pipeline."""
        try:
            self.client.transport.perform_request(
                'DELETE',
                f'/_search/pipeline/{self.search_pipeline_name}'
            )
            
            logger.info(f"Search pipeline deleted: {self.search_pipeline_name}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to delete search pipeline: {str(e)}")
            return False
    
    def _filter_results_by_score_threshold(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Filter search results based on minimum score threshold."""
        try:
            if 'hits' not in response or 'hits' not in response['hits']:
                return response
            
            original_hits = response['hits']['hits']
            filtered_hits = []
            
            for hit in original_hits:
                score = hit.get('_score', 0)
                if score >= self.search_threshold_score:
                    filtered_hits.append(hit)
                else:
                    logger.debug(f"Filtered out result with score {score} (threshold: {self.search_threshold_score})")
            
            # Update response with filtered results
            response['hits']['hits'] = filtered_hits
            response['hits']['total']['value'] = len(filtered_hits)
            
            logger.info(f"Score filtering: {len(original_hits)} -> {len(filtered_hits)} results (threshold: {self.search_threshold_score})")
            
            return response
            
        except Exception as e:
            logger.warning(f"Failed to filter results by score threshold: {str(e)}")
            return response