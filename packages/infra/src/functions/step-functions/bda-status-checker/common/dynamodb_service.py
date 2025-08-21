"""
DynamoDB Service for unified database operations across all tables.
"""

import boto3
from boto3.dynamodb.conditions import Key, Attr
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import logging
from decimal import Decimal
import json

from .aws_clients import AWSClientFactory
from .utils import get_current_timestamp, generate_uuid

logger = logging.getLogger(__name__)


class DynamoDBService:
    """Unified service for DynamoDB operations across core tables."""
    
    def __init__(self, region: Optional[str] = None):
        self.dynamodb = AWSClientFactory.get_dynamodb_resource(region)
        self.client = AWSClientFactory.get_dynamodb_client(region)
        
        # Initialize table references using environment variables
        self.tables = {
            'documents': self.dynamodb.Table(AWSClientFactory.get_table_name('documents')),
            'segments': self.dynamodb.Table(AWSClientFactory.get_table_name('segments')),
            'indices': self.dynamodb.Table(AWSClientFactory.get_table_name('indices')),
        }
    
    def _serialize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python types to DynamoDB compatible types."""
        return json.loads(json.dumps(item, default=str), parse_float=Decimal)
    
    def _add_timestamps(self, item: Dict[str, Any], update: bool = False) -> Dict[str, Any]:
        """Add created_at and updated_at timestamps."""
        timestamp = get_current_timestamp()
        if not update:
            item['created_at'] = timestamp
        item['updated_at'] = timestamp
        return item
    
    # Generic CRUD Operations
    def create_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new item in the specified table."""
        try:
            table = self.tables[table_name]
            item = self._add_timestamps(self._serialize_item(item))
            
            response = table.put_item(Item=item)
            logger.info(f"Created item in {table_name}")
            return item
            
        except Exception as e:
            logger.error(f"Failed to create item in {table_name}: {str(e)}")
            raise
    
    def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get an item by primary key."""
        try:
            table = self.tables[table_name]
            response = table.get_item(Key=key)
            return response.get('Item')
            
        except Exception as e:
            logger.error(f"Failed to get item from {table_name}: {str(e)}")
            raise
    
    def update_item(self, table_name: str, key: Dict[str, Any], 
                   update_expression: str = None, 
                   expression_attribute_values: Dict[str, Any] = None,
                   expression_attribute_names: Dict[str, str] = None,
                   updates: Dict[str, Any] = None) -> Dict[str, Any]:
        """Update an item with flexible update patterns."""
        try:
            table = self.tables[table_name]
            
            # If simple updates dict provided, build expression
            if updates:
                updates = self._add_timestamps(self._serialize_item(updates), update=True)
                update_expr_parts = []
                expr_attr_values = {}
                expr_attr_names = {}
                
                for field, value in updates.items():
                    field_placeholder = f"#{field}"
                    value_placeholder = f":{field}"
                    update_expr_parts.append(f"{field_placeholder} = {value_placeholder}")
                    expr_attr_names[field_placeholder] = field
                    expr_attr_values[value_placeholder] = value
                
                update_expression = "SET " + ", ".join(update_expr_parts)
                expression_attribute_values = expr_attr_values
                expression_attribute_names = expr_attr_names
            
            # Add updated_at if not already being set by caller
            if expression_attribute_values:
                update_expr_compact = (update_expression or '').replace(' ', '').lower()
                caller_sets_updated_at = 'updated_at=' in update_expr_compact or '#updated_at=' in update_expr_compact
                if (':updated_at' not in expression_attribute_values) and (not caller_sets_updated_at):
                    if expression_attribute_names is None:
                        expression_attribute_names = {}
                    expression_attribute_names['#updated_at'] = 'updated_at'
                    expression_attribute_values[':updated_at'] = get_current_timestamp()
                    update_expression += ", #updated_at = :updated_at" if "SET" in update_expression else "SET #updated_at = :updated_at"
            
            kwargs = {
                'Key': key,
                'UpdateExpression': update_expression,
                'ReturnValues': 'ALL_NEW'
            }
            
            if expression_attribute_values:
                kwargs['ExpressionAttributeValues'] = expression_attribute_values
            if expression_attribute_names:
                kwargs['ExpressionAttributeNames'] = expression_attribute_names
            
            response = table.update_item(**kwargs)
            logger.info(f"Updated item in {table_name}")
            return response.get('Attributes', {})
            
        except Exception as e:
            logger.error(f"Failed to update item in {table_name}: {str(e)}")
            raise
    
    def delete_item(self, table_name: str, key: Dict[str, Any]) -> bool:
        """Delete an item by primary key."""
        try:
            table = self.tables[table_name]
            table.delete_item(Key=key)
            logger.info(f"Deleted item from {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete item from {table_name}: {str(e)}")
            raise
    
    def query_items(self, table_name: str, 
                   key_condition_expression: Any,
                   filter_expression: Any = None,
                   index_name: str = None,
                   scan_index_forward: bool = True,
                   limit: int = None,
                   exclusive_start_key: Dict[str, Any] = None) -> Dict[str, Any]:
        """Query items with flexible parameters."""
        try:
            table = self.tables[table_name]
            
            kwargs = {
                'KeyConditionExpression': key_condition_expression,
                'ScanIndexForward': scan_index_forward
            }
            
            if filter_expression:
                kwargs['FilterExpression'] = filter_expression
            if index_name:
                kwargs['IndexName'] = index_name
            if limit:
                kwargs['Limit'] = limit
            if exclusive_start_key:
                kwargs['ExclusiveStartKey'] = exclusive_start_key
            
            response = table.query(**kwargs)
            logger.info(f"Queried {len(response.get('Items', []))} items from {table_name}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to query {table_name}: {str(e)}")
            raise
    
    def scan_items(self, table_name: str,
                   filter_expression: Any = None,
                   limit: int = None,
                   exclusive_start_key: Dict[str, Any] = None) -> Dict[str, Any]:
        """Scan items for full-table reads (use sparingly)."""
        try:
            table = self.tables[table_name]
            kwargs = {}
            if filter_expression:
                kwargs['FilterExpression'] = filter_expression
            if limit:
                kwargs['Limit'] = limit
            if exclusive_start_key:
                kwargs['ExclusiveStartKey'] = exclusive_start_key
            response = table.scan(**kwargs)
            logger.info(f"Scanned {len(response.get('Items', []))} items from {table_name}")
            return response
        except Exception as e:
            logger.error(f"Failed to scan {table_name}: {str(e)}")
            raise
    
    def batch_get_items(self, requests: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Batch get items across multiple tables."""
        try:
            # Build request structure
            request_items = {}
            for table_name, request_data in requests.items():
                table = self.tables[table_name]
                request_items[table.name] = request_data
            
            response = self.client.batch_get_item(RequestItems=request_items)
            
            # Convert table names back to logical names
            result = {}
            for table_name, request_data in requests.items():
                table = self.tables[table_name]
                result[table_name] = response.get('Responses', {}).get(table.name, [])
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to batch get items: {str(e)}")
            raise
    
    def batch_write_items(self, requests: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Batch write items across multiple tables."""
        try:
            # Build request structure
            request_items = {}
            for table_name, items in requests.items():
                table = self.tables[table_name]
                request_items[table.name] = items
            
            response = self.client.batch_write_item(RequestItems=request_items)
            return response
            
        except Exception as e:
            logger.error(f"Failed to batch write items: {str(e)}")
            raise
    
    # High-level convenience methods
    def get_documents(self, index_id: str = 'default') -> List[Dict[str, Any]]:
        """Get all documents (index-independent)."""
        response = self.query_items(
            table_name='documents',
            key_condition_expression=Key('index_id').eq(index_id),
            index_name='IndexId'
        )
        return response.get('Items', [])
    
    def get_document_segments(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all segments for a document."""
        response = self.query_items(
            table_name='segments',
            key_condition_expression=Key('document_id').eq(document_id),
            index_name='DocumentIdIndex'
        )
        items = response.get('Items', [])
        # normalize legacy shape for callers still expecting page_* keys
        return [
            {
                'page_id': i.get('segment_id'),
                'page_index': i.get('page_index', i.get('segment_index', 0)),
                'image_uri': i.get('image_uri', ''),
                'document_id': i.get('document_id'),
            }
            for i in items
        ]
    
    def update_document_status(self, document_id: str, status: str) -> Dict[str, Any]:
        """Update document status."""
        return self.update_item(
            table_name='documents',
            key={'document_id': document_id},
            updates={'status': status}
        )
    
    def update_page_status(self, page_id: str, status: str) -> Dict[str, Any]:
        """Update segment status."""
        return self.update_item(
            table_name='segments',
            key={'segment_id': page_id},
            updates={'page_status': status}
        )

    # ------------------ Helpers ------------------
    @staticmethod
    def infer_media_type(file_type: Optional[str], file_name: Optional[str] = None) -> str:
        """Infer media type category used by pipeline from MIME type/filename.
        Returns one of: 'VIDEO' | 'AUDIO' | 'IMAGE' | 'DOCUMENT'.
        """
        try:
            ft = (file_type or '').lower()
            if ft.startswith('video/'):
                return 'VIDEO'
            elif ft.startswith('audio/'):
                return 'AUDIO'
            elif ft.startswith('image/'):
                return 'IMAGE'
            return 'DOCUMENT'
        except Exception:
            return 'DOCUMENT'