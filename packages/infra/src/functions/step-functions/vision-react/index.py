"""
AWS IDP AI Analysis - Vision ReAct Lambda Function
"""

import json
import os
import sys
import logging
import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

# Add local module paths
sys.path.append('/opt/python')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.react_agent import ReactAgent

# Common module imports
from common import (
    DynamoDBService,
    S3Service,
    AWSClientFactory,
    get_current_timestamp,
    OpenSearchService,
)

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize services
db_service = DynamoDBService()
s3_service = S3Service()
aws_clients = AWSClientFactory()

# Environment variables
STAGE = os.environ.get('STAGE', 'prod')
S3_BUCKET_NAME = os.environ.get('DOCUMENTS_TABLE_NAME')
SEGMENTS_TABLE_NAME = os.environ.get('SEGMENTS_TABLE_NAME')
MODEL_REGION = os.environ.get('AWS_REGION', 'us-west-2')
BEDROCK_AGENT_MODEL_ID = os.environ.get('BEDROCK_AGENT_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
BEDROCK_AGENT_MAX_TOKENS = int(os.environ.get('BEDROCK_AGENT_MAX_TOKENS', 8192))
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT', '')
DOCUMENTS_TABLE_NAME = os.environ.get('DOCUMENTS_TABLE_NAME')

class LambdaVisionReactHandler:
    """Handler for Vision ReAct analysis"""
    
    def __init__(self):
        """Initialize handler"""
        self.model_id = BEDROCK_AGENT_MODEL_ID
        self.max_tokens = BEDROCK_AGENT_MAX_TOKENS
        self.opensearch_service = None
        
        logger.info("=" * 80)
        logger.info("✅ Vision ReAct Handler Initialized")
        logger.info(f"📊 Model: {self.model_id}")
        logger.info(f"📊 Max Tokens: {self.max_tokens}")
        logger.info(f"📊 OpenSearch: {'Enabled' if OPENSEARCH_ENDPOINT else 'Disabled'}")
        logger.info("=" * 80)

        # Initialize OpenSearch service (used to fetch previous BDA/PDF results)
        try:
            if OPENSEARCH_ENDPOINT:
                # Note: index is provided per-call; service methods accept explicit index_id
                self.opensearch_service = OpenSearchService(
                    endpoint=OPENSEARCH_ENDPOINT,
                    index_name=os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis'),
                    region=MODEL_REGION
                )
                logger.info("✅ OpenSearch service initialized for previous context fetching")
        except Exception as e:
            logger.warning(f"⚠️ OpenSearch init failed (previous context disabled): {e}")
    
    async def _analyze_single_segment(self, segment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze single segment using Vision ReAct
        """
        try:
            # Extract segment data
            index_id = segment_data['index_id']
            document_id = segment_data['document_id']
            segment_index = segment_data['segment_index']
            segment_id = segment_data['segment_id']
            image_uri = segment_data.get('image_uri', '')  # May be empty for non-image segments
            file_path = segment_data.get('file_path', '')
            thread_id = segment_data.get('thread_id')

            # Video chapter info
            segment_type = segment_data.get('segment_type', 'PAGE')
            start_timecode_smpte = segment_data.get('start_timecode_smpte', '')
            end_timecode_smpte = segment_data.get('end_timecode_smpte', '')

            # Media type
            media_type = segment_data.get('media_type', 'DOCUMENT')
            
            # Log analysis start
            logger.info("\n" + "🎯" * 40)
            logger.info("🎯 SEGMENT ANALYSIS STARTED")
            logger.info(f"> Index: {index_id}")
            logger.info(f"> Document: {document_id}")
            logger.info(f"> Segment: {segment_index} ({segment_id})")
            logger.info(f"> Media Type: {media_type}")
            logger.info(f"> Image: {image_uri}")
            if thread_id:
                logger.info(f"> Thread: {thread_id}")
            logger.info("🎯" * 40)
            
            # Update segment status
            self._update_segment_status(
                document_id=document_id,
                segment_id=segment_id,
                segment_index=segment_index,
                status='react_analyzing',
                message='Vision ReAct analysis started'
            )
            
            # Build previous analysis context from existing BDA/PDF results in OpenSearch
            previous_analysis_context = self._get_previous_analysis_context(
                index_id=index_id,
                segment_id=segment_id
            )

            # Initialize agent
            agent = ReactAgent()
            
            # Prepare input data
            input_data = {
                'index_id': index_id,
                'document_id': document_id,
                'segment_id': segment_id,
                'segment_index': segment_index,
                'image_uri': image_uri,
                'file_path': file_path,
                'media_type': media_type,
                'previous_analysis_context': previous_analysis_context or '',
                'segment_type': segment_type,
                'start_timecode_smpte': start_timecode_smpte,
                'end_timecode_smpte': end_timecode_smpte
            }
            
            # Execute analysis
            start_time = time.time()
            result = agent.invoke(input_data)
            analysis_time = time.time() - start_time
            
            # Process results
            if result.get('success'):
                logger.info("\n" + "🎉" * 40)
                logger.info("🎉 ANALYSIS SUCCESS")
                logger.info(f"> Time: {analysis_time:.2f}s")
                logger.info(f"> Iterations: {result.get('iterations', 0)}")
                logger.info(f"> Response: {len(result.get('response', ''))} chars")
                logger.info("🎉" * 40)
                
                # Update segment status
                self._update_segment_status(
                    document_id=document_id,
                    segment_id=segment_id,
                    segment_index=segment_index,
                    status='completed',
                    message='Vision ReAct analysis completed successfully'
                )
                
                return {
                    'success': True,
                    'document_id': document_id,
                    'segment_id': segment_id,
                    'segment_index': segment_index,
                    'analysis_content': result.get('response', ''),
                    'analysis_time': analysis_time,
                    'iterations': result.get('iterations', 0),
                    'thoughts': result.get('thoughts', []),
                    'actions': result.get('actions', []),
                    'timestamp': get_current_timestamp()
                }
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"❌ Analysis failed: {error_msg}")
                raise Exception(f"Analysis failed: {error_msg}")
                
        except Exception as e:
            error_msg = f"Segment analysis failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            
            # Update segment status
            try:
                self._update_segment_status(
                    document_id=segment_data['document_id'],
                    segment_id=segment_data['segment_id'],
                    segment_index=segment_data['segment_index'],
                    status='vision_failed',
                    message=f'Vision analysis failed: {str(e)[:200]}'
                )
            except Exception as update_error:
                logger.error(f"Status update failed: {update_error}")
            
            raise Exception(error_msg)
    
    def _update_segment_status(self, document_id: str, segment_id: str, 
                               segment_index: int, status: str, message: str):
        """Update segment status in DynamoDB"""
        try:
            if not SEGMENTS_TABLE_NAME:
                logger.warning("SEGMENTS_TABLE_NAME not set")
                return
            
            update_expr = """
                SET #status = :status,
                    updated_at = :updated_at
            """
            
            attr_values = {
                ':status': status,
                ':updated_at': get_current_timestamp()
            }
            
            attr_names = {'#status': 'status'}
            
            db_service.update_item(
                'segments',
                {'segment_id': segment_id},
                update_expression=update_expr,
                expression_attribute_values=attr_values,
                expression_attribute_names=attr_names
            )
            
            logger.info(f"✅ Segment status updated: {segment_id} -> {status}")
            
        except Exception as e:
            logger.error(f"❌ Status update failed: {e}")

    def _get_previous_analysis_context(self, index_id: str, segment_id: str) -> str:
        """Build previous analysis context from BDA/PDF tool results in OpenSearch.

        Preference: Only include 'bda_indexer' and 'pdf_text_extractor' contents.
        """
        try:
            if not self.opensearch_service:
                return ""

            # Fetch existing segment document
            segment_doc = self.opensearch_service.get_segment_document(index_id, segment_id)
            if not segment_doc:
                return ""

            tools = segment_doc.get('tools', {}) or {}
            parts = []

            # BDA indexer results
            bda_items = tools.get('bda_indexer', []) or []
            bda_contents = []
            for item in bda_items:
                content = (item.get('content') or '').strip()
                if content:
                    bda_contents.append(content)
            if bda_contents:
                parts.append("=== BDA 분석 결과 ===\n" + "\n\n".join(bda_contents))

            # PDF text extractor results
            pdf_items = tools.get('pdf_text_extractor', []) or []
            pdf_contents = []
            for item in pdf_items:
                content = (item.get('content') or '').strip()
                if content:
                    pdf_contents.append(content)
            if pdf_contents:
                parts.append("=== PDF 텍스트 추출 결과 ===\n" + "\n\n".join(pdf_contents))

            return "\n\n".join(parts)
        except Exception as e:
            logger.warning(f"Failed to build previous analysis context: {e}")
            return ""

# Global handler instance
handler_instance = None

def lambda_handler(event, context):
    """
    Lambda handler entry point
    """
    global handler_instance
    handler_start_time = datetime.now(timezone.utc)
    
    try:
        # Log start
        logger.info("\n" + "🚀" * 50)
        logger.info("🚀 VISION REACT LAMBDA STARTED")
        logger.info("🚀" * 50)
        
        # Log environment
        logger.info("🌍 Environment Variables:")
        for var in ['STAGE', 'BEDROCK_AGENT_MODEL_ID', 'AWS_REGION', 'OPENSEARCH_ENDPOINT']:
            value = os.environ.get(var, 'NOT_SET')
            if len(str(value)) > 50:
                value = str(value)[:50] + "..."
            logger.info(f"  {var}: {value}")
        
        # Log input event
        logger.info("\n📋 Input Event:")
        logger.info(json.dumps(event, ensure_ascii=False, indent=2, default=str))
        
        # Initialize handler
        if handler_instance is None:
            handler_instance = LambdaVisionReactHandler()
        
        # Run async analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Get essential segment details from DynamoDB using single query (optimized for minimal latency)
            segment_id = event['segment_id']

            segment_details = db_service.get_item(
                table_name='segments',
                key={'segment_id': segment_id}
            )

            if not segment_details:
                raise Exception(f"Segment not found in database: {segment_id}")

            logger.info(f"✅ Retrieved segment details for segment_id: {segment_id}")

            # Convert event to segment data
            segment_data = {
                'index_id': event['index_id'],
                'document_id': event['document_id'],
                'segment_index': event.get('segment_index', segment_details.get('segment_index', 0)),
                'segment_id': segment_id,
                'image_uri': segment_details.get('image_uri', ''),
                'file_path': event.get('file_uri', segment_details.get('file_uri', '')),
                'thread_id': event.get('thread_id'),
                'segment_type': segment_details.get('segment_type', 'PAGE'),
                'start_timecode_smpte': segment_details.get('start_timecode_smpte', ''),
                'end_timecode_smpte': segment_details.get('end_timecode_smpte', ''),
                'media_type': event.get('media_type', 'DOCUMENT')
            }
            
            result = loop.run_until_complete(
                handler_instance._analyze_single_segment(segment_data)
            )
        finally:
            loop.close()
        
        # Log completion
        handler_end_time = datetime.now(timezone.utc)
        handler_duration = (handler_end_time - handler_start_time).total_seconds()
        
        logger.info("\n" + "🏁" * 50)
        logger.info("🏁 LAMBDA COMPLETED")
        logger.info(f"⏱️ Duration: {handler_duration:.2f}s")
        logger.info(f"✅ Success: {result.get('success', False)}")
        logger.info(f"📑 Segment: {result.get('segment_index', 'unknown')}")
        logger.info("🏁" * 50)
        
        return result
        
    except Exception as e:
        # Error handling
        handler_end_time = datetime.now(timezone.utc)
        handler_duration = (handler_end_time - handler_start_time).total_seconds()
        
        logger.error("\n" + "💥" * 50)
        logger.error("💥 LAMBDA ERROR")
        logger.error(f"💥 Message: {str(e)}")
        logger.error(f"💥 Type: {type(e).__name__}")
        logger.error(f"> Duration: {handler_duration:.2f}s")
        
        import traceback
        logger.error("Stack trace:")
        logger.error(traceback.format_exc())
        logger.error("💥" * 50)
        
        # Raise for Step Functions
        raise Exception(f"Lambda execution failed: {str(e)}")