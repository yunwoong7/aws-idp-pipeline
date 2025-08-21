import json
import os
import logging
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from typing import Dict, Any, List

# Common module imports
from common import (
    DynamoDBService,
    get_current_timestamp
)

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()

# Environment variables
STAGE = os.environ.get('STAGE', 'dev')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to retrieve all segments of a document, called from Step Function
    """
    try:
        logger.info(f"🔍 Get Document Segments Lambda started - Event: {json.dumps(event, default=str)}")
        
        # Extract document_id from event (Step Function Lambda invoke response structure)
        index_id = None
        document_id = None
        
        # Extract data directly from Payload in Lambda invoke response
        if 'Payload' in event and isinstance(event['Payload'], dict):
            payload = event['Payload']
            index_id = payload.get('index_id')
            document_id = payload.get('document_id')
            media_type = payload.get('media_type', 'DOCUMENT')
        # Extract document_id directly from event
        elif 'document_id' in event:
            index_id = event.get('index_id')
            document_id = event.get('document_id')
            media_type = event.get('media_type', 'DOCUMENT')
        
        if not document_id:
            raise ValueError(f"document_id must be included in the event. Event structure: {json.dumps(event, default=str)}")
        
        logger.info(f"📄 Document ID: {document_id}")
        logger.info(f"📄 Media Type: {media_type}")
        if index_id:
            logger.info(f"📁 Index ID: {index_id}")
        
        # Update document status to react_analyzing in Documents table
        if index_id:
            try:
                current_time = get_current_timestamp()
                
                db_service.update_item(
                    table_name='documents',
                    key={'document_id': document_id},
                    update_expression='SET #status = :status, updated_at = :updated_at',
                    expression_attribute_names={'#status': 'status'},
                    expression_attribute_values={
                        ':status': 'react_analyzing',
                        ':updated_at': current_time
                    }
                )
                logger.info(f"📝 Document status updated to react_analyzing")
            except Exception as update_error:
                logger.warning(f"⚠️ Document status update failed (continuing): {str(update_error)}")
        
        # Query all segments of the document from DynamoDB Segments table
        try:
            response = db_service.query_items(
                table_name='segments',
                key_condition_expression=Key('document_id').eq(document_id),
                index_name='DocumentIdIndex'
            )
            items = response.get('Items', [])
            # Extract required fields and include video chapter information directly from items
            filtered_segments = []
            for item in items:
                segment_data = {
                    'segment_id': item.get('segment_id'),
                    'segment_index': item.get('segment_index', 0),
                    'image_uri': item.get('image_uri', ''),
                    'document_id': item.get('document_id')
                }
                
                # 세그먼트 타입 추가 (모든 경우에 대해)
                segment_type = item.get('segment_type', 'PAGE')  # 기본값은 PAGE
                segment_data['segment_type'] = segment_type
                    
                # 동영상 챕터 시간 정보 추가 (VideoAnalyzerTool용)
                # Step Function에서 필드를 참조하므로 모든 경우에 대해 기본값 설정
                start_timecode = item.get('start_timecode_smpte', '')
                end_timecode = item.get('end_timecode_smpte', '')
                file_uri = item.get('file_uri', '')
                
                segment_data['start_timecode_smpte'] = start_timecode
                segment_data['end_timecode_smpte'] = end_timecode
                segment_data['file_uri'] = file_uri
                    
                filtered_segments.append(segment_data)
        except Exception:
            filtered_segments = []
        logger.info(f"📊 Number of segments retrieved: {len(filtered_segments)}")
        
        # Sort segments by segment_index
        segments_sorted = sorted(filtered_segments, key=lambda x: int(x.get('segment_index', 0)))
        
        # Log results
        for segment in segments_sorted:
            logger.info(f"  - Segment {segment.get('segment_index')}: {segment.get('segment_id')}")
        
        # Success response (Step Function compatible - direct data return)
        result = {
            'segments': segments_sorted,
            'count': len(segments_sorted),
            'document_id': document_id,
            'index_id': index_id,
            'media_type': media_type,
            'timestamp': get_current_timestamp()
        }
        
        logger.info(f"✅ Get Document Segments Lambda complete - {len(segments_sorted)} segments retrieved")
        return result
        
    except Exception as e:
        error_message = f"Get Document Segments Lambda error: {str(e)}"
        logger.error(error_message)
        
        # Error response (Step Function compatible - direct data return)
        return {
            'error': error_message,
            'segments': [],
            'count': 0,
            'timestamp': get_current_timestamp()
        } 