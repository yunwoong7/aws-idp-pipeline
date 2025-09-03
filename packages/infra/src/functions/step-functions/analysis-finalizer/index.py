"""
React Analysis Finalizer Lambda
After all tools have completed, create segment-specific embeddings and update OpenSearch
"""

import json
import logging
import os
from typing import Dict, Any, List
from datetime import datetime, timezone

# Common module imports
from common import (
    DynamoDBService,
    OpenSearchService,
    handle_lambda_error,
    create_success_response,
    get_current_timestamp
)

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()
opensearch_service = OpenSearchService()

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    React Analysis Finalizer Lambda handler
    Create segment-specific embeddings and update OpenSearch
    
    Args:
        event: Event received from Step Function (includes segment_id or document_id)
        context: Lambda context
        
    Returns:
        Processing result
    """
    try:
        logger.info(f"React Analysis Finalizer started - Event: {json.dumps(event, ensure_ascii=False, indent=2)}")
        
        # Extract input data
        index_id = event.get('index_id')
        document_id = event.get('document_id')
        segment_id = event.get('segment_id')
        
        if not document_id:
            raise ValueError("document_id is required.")
        
        logger.info(f"📝 Target: index_id={index_id}, document_id={document_id}, segment_id={segment_id}")
        
        # Mark document as analysis finalizing in-progress (react_finalizing) only when finalizing whole document
        try:
            if document_id and not segment_id:
                current_time = get_current_timestamp()
                db_service.update_item(
                    table_name='documents',
                    key={'document_id': document_id},
                    update_expression='SET #status = :status, updated_at = :updated_at',
                    expression_attribute_names={'#status': 'status'},
                    expression_attribute_values={
                        ':status': 'react_finalizing',
                        ':updated_at': current_time
                    }
                )
                logger.info(f"📌 Document status set to react_finalizing (full): {document_id}")
        except Exception as se:
            logger.warning(f"⚠️ Failed to set react_finalizing status: {str(se)}")

        # If index_id is missing, look up from Indices table
        if not index_id:
            index = db_service.get_item('indices', {'index_id': index_id})
            if index:
                index_id = index.get('index_id')
                logger.info(f"index_id looked up from Indices table: {index_id}")
        
        if segment_id:
            # Process only a specific segment
            processed_segments = process_single_segment(index_id, document_id, segment_id)
            total_segments = 1
        else:
            # Process all segments in the document
            processed_segments = process_all_segments_in_document(document_id, index_id)
            total_segments = processed_segments
        
        # Note: Document status will be updated by DocumentSummarizerTask as final step
        
        logger.info(f"✅ React Analysis Finalizer complete - Processed segments: {processed_segments}/{total_segments}")

        # Aggregate segment statuses to decide document status
        try:
            from boto3.dynamodb.conditions import Key
            segments_response = db_service.query_items(
                table_name='segments',
                key_condition_expression=Key('document_id').eq(document_id),
                index_name='DocumentIdIndex'
            )
            segments = segments_response.get('Items', []) if segments_response else []
            total = len(segments)
            finalized = sum(1 for s in segments if (s.get('status') or '').lower() in ['finalized'])
            analyzing = sum(1 for s in segments if (s.get('status') or '').lower() in ['react_analyzing'])

            next_status = None
            if total > 0 and finalized == total:
                next_status = 'react_finalized'
            elif finalized > 0:
                next_status = 'react_finalizing'

            if next_status:
                current_time = get_current_timestamp()
                db_service.update_item(
                    table_name='documents',
                    key={'document_id': document_id},
                    update_expression='SET #status = :status, updated_at = :updated_at',
                    expression_attribute_names={'#status': 'status'},
                    expression_attribute_values={
                        ':status': next_status,
                        ':updated_at': current_time
                    }
                )
                logger.info(f"📌 Aggregated document status set to {next_status}: {document_id} (finalized {finalized}/{total}, analyzing {analyzing})")
        except Exception as se:
            logger.warning(f"⚠️ Failed to aggregate/update document status: {str(se)}")
        
        # Step Function 호환 응답 (Lambda 프록시 응답 대신 직접 반환)
        return {
            'success': True,
            'message': 'React Analysis finalization complete',
            'document_id': document_id,
            'index_id': index_id,
            'processed_segments': processed_segments,
            'total_segments': total_segments
        }
        
    except Exception as e:
        logger.error(f"React Analysis Finalizer error: {str(e)}", exc_info=True)
        # Mark document as finalize failed
        try:
            if 'document_id' in locals() and document_id:
                current_time = get_current_timestamp()
                db_service.update_item(
                    table_name='documents',
                    key={'document_id': document_id},
                    update_expression='SET #status = :status, updated_at = :updated_at',
                    expression_attribute_names={'#status': 'status'},
                    expression_attribute_values={
                        ':status': 'react_finalize_failed',
                        ':updated_at': current_time
                    }
                )
                logger.info(f"📌 Document status set to react_finalize_failed: {document_id}")
        except Exception as se:
            logger.warning(f"⚠️ Failed to set react_finalize_failed status: {str(se)}")
        return handle_lambda_error(e)

def process_single_segment(index_id: str, document_id: str, segment_id: str) -> int:
    """Integrate tool results for a single segment and create embeddings"""
    try:
        logger.info(f"🔄 Segment embedding processing started: {segment_id}")
        
        # Retrieve segment document from OpenSearch
        segment_doc = opensearch_service.get_segment_document(index_id, segment_id)
        
        if not segment_doc:
            logger.warning(f"⚠️ Segment document not found: {segment_id}")
            return 0
        
        # Check content by tool
        tools = segment_doc.get('tools', {})
        bda_indexer_tools = tools.get('bda_indexer', [])
        pdf_text_extractor_tools = tools.get('pdf_text_extractor', [])
        ai_analysis_tools = tools.get('ai_analysis', [])
        
        total_tools = len(bda_indexer_tools) + len(pdf_text_extractor_tools) + len(ai_analysis_tools)
        
        if total_tools == 0:
            logger.info(f"ℹ️ No tool results for segment: {segment_id}")
            return 0
        
        logger.info(f"📊 Segment tool status: BDA={len(bda_indexer_tools)}, PDF={len(pdf_text_extractor_tools)}, AI={len(ai_analysis_tools)}")
        
        # Combine content from all tools
        combined_content_parts = []
        
        # Add BDA Indexer results
        for tool in bda_indexer_tools:
            content = tool.get('content', '').strip()
            if content:
                combined_content_parts.append(f"## BDA Analysis Result\n{content}")
        
        # Add PDF text extraction results
        for tool in pdf_text_extractor_tools:
            content = tool.get('content', '').strip()
            if content:
                combined_content_parts.append(f"## PDF Text Extraction\n{content}")
        
        # Add image analysis results
        for tool in ai_analysis_tools:
            content = tool.get('content', '').strip()
            analysis_query = tool.get('analysis_query', '')
            if content:
                if analysis_query and analysis_query != "페이지 분석":
                    combined_content_parts.append(f"## AI Analysis: {analysis_query}\n{content}")
                else:
                    combined_content_parts.append(f"## AI Analysis\n{content}")
        
        # Combine all content
        content_combined = "\n\n".join(combined_content_parts)
        
        if not content_combined.strip():
            logger.info(f"ℹ️ No valid content for segment: {segment_id}")
            return 0
        
        logger.info(f"📝 Combined content length: {len(content_combined)} chars")
        
        # Create embeddings and update segment document
        success = opensearch_service.update_segment_embeddings(index_id, segment_id, content_combined)
        
        if success:
            logger.info(f"✅ Segment embedding creation complete: {segment_id}")
            return 1
        else:
            logger.error(f"❌ Segment embedding creation failed: {segment_id}")
            return 0
            
    except Exception as e:
        logger.error(f"❌ Segment embedding processing error {segment_id}: {str(e)}")
        return 0

def process_all_segments_in_document(document_id: str, index_id: str) -> int:
    """Create embeddings for all segments in the document"""
    try:
        logger.info(f"📑 Document all segments embedding processing started: {document_id}")
        
        # 문서 정보 확인
        document = db_service.get_item('documents', {'document_id': document_id})
        if not document:
            logger.error(f"❌ Document not found: {document_id}")
            return 0
        
        # Retrieve all segments of the document from Segments table
        from boto3.dynamodb.conditions import Key
        segments_response = db_service.query_items(
            table_name='segments',
            key_condition_expression=Key('document_id').eq(document_id),
            index_name='DocumentIdIndex'
        )
        
        segments = segments_response.get('Items', [])
        logger.info(f"📋 Total segments: {len(segments)}")
        
        processed_count = 0
        
        for segment in segments:
            segment_id = segment.get('segment_id')
            segment_index = segment.get('segment_index', 0)
            
            if not segment_id:
                logger.warning(f"⚠️ Skipping segment with no segment_id: {segment}")
                continue
            
            logger.info(f"🔄 Processing segment: {segment_id} (index: {segment_index})")
            
            result = process_single_segment(index_id, document_id, segment_id)
            processed_count += result
            
            if result:
                logger.debug(f"✅ Segment processed: {segment_id}")
            else:
                logger.warning(f"⚠️ Segment processing failed or skipped: {segment_id}")
        
        logger.info(f"📊 Document embedding processing complete: {document_id} - {processed_count}/{len(segments)} segments processed")
        return processed_count
        
    except Exception as e:
        logger.error(f"❌ Document embedding processing error {document_id}: {str(e)}")
        raise

# Note: Document final status update is now handled by DocumentSummarizerTask

def get_document_embedding_status(index_id: str, document_id: str) -> Dict[str, Any]:
    """Check embedding processing status of the document (for debugging)"""
    try:
        # Retrieve segment list from Segments table
        from boto3.dynamodb.conditions import Key
        segments_response = db_service.query_items(
            table_name='segments',
            key_condition_expression=Key('document_id').eq(document_id),
            index_name='DocumentIdIndex'
        )

        segments = segments_response.get('Items', [])
        status = {
            'document_id': document_id,
            'total_segments': len(segments),
            'segments_with_embeddings': 0,
            'segments_without_embeddings': 0,
            'segments_with_tools': 0,
            'segments_without_tools': 0,
            'segment_details': []
        }
        
        for segment in segments:
            segment_id = segment.get('segment_id')
            segment_index = segment.get('segment_index', 0)
            
            # Retrieve segment document from OpenSearch
            segment_doc = opensearch_service.get_segment_document(index_id, segment_id)
            
            if segment_doc:
                has_embeddings = 'vector_content' in segment_doc and segment_doc['vector_content']
                tools = segment_doc.get('tools', {})
                tool_count = (
                    len(tools.get('bda_indexer', [])) +
                    len(tools.get('pdf_text_extractor', [])) +
                    len(tools.get('ai_analysis', []))
                )
                
                if has_embeddings:
                    status['segments_with_embeddings'] += 1
                else:
                    status['segments_without_embeddings'] += 1
                
                if tool_count > 0:
                    status['segments_with_tools'] += 1
                else:
                    status['segments_without_tools'] += 1
                
                status['segment_details'].append({
                    'segment_id': segment_id,
                    'segment_index': segment_index,
                    'has_embeddings': has_embeddings,
                    'tool_count': tool_count,
                    'content_combined_length': len(segment_doc.get('content_combined', ''))
                })
            else:
                status['segments_without_embeddings'] += 1
                status['segments_without_tools'] += 1
                status['segment_details'].append({
                    'segment_id': segment_id,
                    'segment_index': segment_index,
                    'has_embeddings': False,
                    'tool_count': 0,
                    'content_combined_length': 0,
                    'note': 'No OpenSearch document'
                })
        
        return status
        
    except Exception as e:
        logger.error(f"Error checking document embedding status {document_id}: {str(e)}")
        raise



# 테스트용 메인 함수
if __name__ == "__main__":
    # 로컬 테스트용
    # For local testing
    test_event = {
        "index_id": "test_index_123",
        "document_id": "test_document_456",
        "segment_id": "test_segment_789"
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, ensure_ascii=False, indent=2)) 