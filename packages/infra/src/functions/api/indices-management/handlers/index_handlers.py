import os
import sys
import json
from boto3.dynamodb.conditions import Key
import logging
from typing import Dict, Any

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lambda Layer imports  
from common import (
    DynamoDBService,
    OpenSearchService,
    generate_uuid, 
    get_current_timestamp
)
from utils.response import (
    create_success_response,
    create_internal_error_response,
    create_validation_error_response,
)

logger = logging.getLogger(__name__)
db = DynamoDBService()

# Initialize OpenSearch service (will be lazy loaded)
opensearch_service = None

def _get_opensearch_service():
    """Initialize OpenSearch service as singleton pattern"""
    global opensearch_service
    if opensearch_service is None:
        opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
        if opensearch_endpoint:
            opensearch_service = OpenSearchService(endpoint=opensearch_endpoint)
        else:
            logger.warning("OPENSEARCH_ENDPOINT not set - OpenSearch operations will be skipped")
    return opensearch_service


def handle_indices_list():
    try:
        # Indices table has only PK index_id; use scan for full list
        resp = db.scan_items('indices')
        items = resp.get('Items', [])
        
        # Compute total_documents for each index by counting documents table items with the same index_id
        for item in items:
            index_id = item.get('index_id')
            if not index_id:
                item['total_documents'] = 0
                continue

            try:
                # Use GSI 'IndexId' to query by index_id and count, with pagination
                table = db.tables['documents']
                total = 0
                last_evaluated_key = None
                while True:
                    kwargs = {
                        'IndexName': 'IndexId',
                        'KeyConditionExpression': Key('index_id').eq(index_id),
                        'Select': 'COUNT',
                    }
                    if last_evaluated_key:
                        kwargs['ExclusiveStartKey'] = last_evaluated_key

                    qresp = table.query(**kwargs)
                    total += int(qresp.get('Count', 0))
                    last_evaluated_key = qresp.get('LastEvaluatedKey')
                    if not last_evaluated_key:
                        break

                item['total_documents'] = total
            except Exception as count_error:
                logger.warning(f"Failed to count documents for index {index_id}: {count_error}")
                item['total_documents'] = 0
        
        return create_success_response({'items': items})
    except Exception as e:
        logger.error(f"Failed to list indices: {str(e)}")
        return create_internal_error_response(str(e))


def handle_index_create(body: Dict[str, Any]):
    try:
        required = ['index_id', 'owner_id', 'owner_name']
        missing = [k for k in required if not body.get(k)]
        if missing:
            return create_validation_error_response(f"Missing fields: {', '.join(missing)}")

        index_id = body['index_id']
        
        logger.info(f"Creating index: {index_id}")
        
        # 1. Create DynamoDB entry first
        item = {
            'index_id': index_id,
            'description': body.get('description', ''),
            'owner_id': body['owner_id'],
            'owner_name': body['owner_name'],
            'status': 'creating'  # Track creation status
        }
        saved = db.create_item('indices', item)
        
        # 2. Create OpenSearch index
        opensearch = _get_opensearch_service()
        opensearch_created = False
        
        if opensearch:
            try:
                opensearch_created = opensearch.create_index_for_id(index_id)
                if opensearch_created:
                    # Update status to active
                    db.update_item(
                        table_name='indices',
                        key={'index_id': index_id},
                        update_expression='SET #status = :status',
                        expression_attribute_names={'#status': 'status'},
                        expression_attribute_values={
                            ':status': 'active',
                        }
                    )
                    saved['status'] = 'active'
                    logger.info(f"Successfully created OpenSearch index for: {index_id}")
                else:
                    # Update status to error
                    db.update_item(
                        table_name='indices',
                        key={'index_id': index_id},
                        update_expression='SET #status = :status',
                        expression_attribute_names={'#status': 'status'},
                        expression_attribute_values={
                            ':status': 'error',
                        }
                    )
                    saved['status'] = 'error'
                    logger.error(f"Failed to create OpenSearch index for: {index_id}")
            except Exception as opensearch_error:
                logger.error(f"OpenSearch index creation failed for {index_id}: {str(opensearch_error)}")
                # Update status to error
                db.update_item(
                    table_name='indices',
                    key={'index_id': index_id},
                    update_expression='SET #status = :status',
                    expression_attribute_names={'#status': 'status'},
                    expression_attribute_values={
                        ':status': 'error',
                    }
                )
                saved['status'] = 'error'
        else:
            logger.warning(f"OpenSearch service not available - only DynamoDB entry created for: {index_id}")
            saved['status'] = 'dynamodb_only'
        
        return create_success_response({
            'item': saved,
            'opensearch_created': opensearch_created,
            'message': f"Index {index_id} created with status: {saved.get('status', 'unknown')}"
        })
    except Exception as e:
        logger.error(f"Failed to create index: {str(e)}")
        return create_internal_error_response(str(e))


def handle_index_get(index_id: str):
    try:
        item = db.get_item('indices', {'index_id': index_id})
        if not item:
            return create_validation_error_response('Index not found')
        return create_success_response(item)
    except Exception as e:
        return create_internal_error_response(str(e))


def handle_index_update(index_id: str, body: Dict[str, Any]):
    try:
        updates = {}
        for k in ['index_name', 'description', 'owner_id', 'owner_name']:
            if k in body:
                updates[k] = body[k]
        if not updates:
            return create_validation_error_response('No fields to update')
        updated = db.update_item('indices', {'index_id': index_id}, updates=updates)
        return create_success_response(updated)
    except Exception as e:
        return create_internal_error_response(str(e))


def handle_index_delete(index_id: str):
    try:
        logger.info(f"Deleting index: {index_id}")
        
        # 1. Delete OpenSearch index first
        opensearch = _get_opensearch_service()
        opensearch_deleted = False
        
        if opensearch:
            try:
                opensearch_deleted = opensearch.delete_index_for_id(index_id)
                if opensearch_deleted:
                    logger.info(f"Successfully deleted OpenSearch index for: {index_id}")
                else:
                    logger.warning(f"Failed to delete OpenSearch index for: {index_id}")
            except Exception as opensearch_error:
                logger.error(f"OpenSearch index deletion failed for {index_id}: {str(opensearch_error)}")
        else:
            logger.warning(f"OpenSearch service not available - only DynamoDB entry will be deleted for: {index_id}")
        
        # 2. Delete DynamoDB entry
        db.delete_item('indices', {'index_id': index_id})
        
        return create_success_response({
            'deleted': True, 
            'index_id': index_id,
            'opensearch_deleted': opensearch_deleted,
            'message': f"Index {index_id} deleted (OpenSearch: {'✓' if opensearch_deleted else '✗'})"
        })
    except Exception as e:
        logger.error(f"Failed to delete index {index_id}: {str(e)}")
        return create_internal_error_response(str(e))


