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
        
        # Query all segments of the document from DynamoDB Segments table with pagination support
        try:
            items = []
            last_evaluated_key = None

            # Paginate through all results
            while True:
                response = db_service.query_items(
                    table_name='segments',
                    key_condition_expression=Key('document_id').eq(document_id),
                    index_name='DocumentIdIndex',
                    exclusive_start_key=last_evaluated_key
                )
                page_items = response.get('Items', [])
                items.extend(page_items)

                # Check if there are more pages
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break

            logger.info(f"Retrieved {len(items)} segments with pagination")

            # Extract only essential segment IDs to stay within 32KB Step Function limit
            segment_ids = []
            for item in items:
                segment_info = {
                    'segment_id': item.get('segment_id'),
                    'segment_index': item.get('segment_index', 0),
                }
                segment_ids.append(segment_info)
        except Exception as e:
            logger.error(f"Failed to retrieve segments: {str(e)}")
            segment_ids = []
        logger.info(f"📊 Number of segments retrieved: {len(segment_ids)}")

        # Sort segments by segment_index
        segments_sorted = sorted(segment_ids, key=lambda x: int(x.get('segment_index', 0)))
        
        # Log results
        for segment in segments_sorted:
            logger.info(f"  - Segment {segment.get('segment_index')}: {segment.get('segment_id')}")
        
        # Success response (Step Function compatible - minimal payload)
        result = {
            'segment_ids': segments_sorted,  # Only IDs and indices
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
            'segment_ids': [],
            'count': 0,
            'timestamp': get_current_timestamp()
        } 