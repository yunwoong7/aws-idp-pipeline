"""
DynamoDB Client Utility
Provides functions to interact with Documents and Pages tables
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class DatabaseClient:
    """DynamoDB Client Class"""
    
    def __init__(self, documents_table_name: str, pages_table_name: str):
        """
        Initialize database client
        
        Args:
            documents_table_name: Documents table name
            pages_table_name: Pages table name
        """
        self.documents_table_name = documents_table_name
        self.pages_table_name = pages_table_name
        
        # DynamoDB client initialization
        self.dynamodb = boto3.resource('dynamodb')
        self.documents_table = self.dynamodb.Table(documents_table_name)
        self.pages_table = self.dynamodb.Table(pages_table_name)
    
    def get_current_timestamp(self) -> str:
        """Return current UTC timestamp"""
        return datetime.now(timezone.utc).isoformat()
    
    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve document information
        
        Args:
            document_id: Document ID
        
        Returns:
            Document info or None
        """
        try:
            response = self.documents_table.get_item(
                Key={'document_id': document_id}
            )
            
            if 'Item' in response:
                logger.info(f"Document retrieval success: {document_id}")
                return response['Item']
            else:
                logger.warning(f"Document not found: {document_id}")
                return None
                
        except ClientError as e:
            logger.error(f"Document retrieval failed: {document_id}, error: {str(e)}")
            return None
    
    def get_pages_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all pages of a document
        
        Args:
            document_id: Document ID
        
        Returns:
            List of pages
        """
        try:
            response = self.pages_table.query(
                IndexName='DocumentIdIndex',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('document_id').eq(document_id)
            )
            
            pages = response.get('Items', [])
            logger.info(f"Document pages retrieval complete: {document_id}, page count: {len(pages)}")
            
            return pages
            
        except ClientError as e:
            logger.error(f"Document pages retrieval failed: {document_id}, error: {str(e)}")
            return []
    
    def update_page_text(self, page_id: str, extracted_text: str) -> bool:
        """
        Update page text information
        
        Args:
            page_id: Page ID
            extracted_text: Extracted text
        
        Returns:
            Whether update succeeded
        """
        try:
            current_time = self.get_current_timestamp()
            
            # Construct update expression
            update_expression = "SET extracted_text = :text, text_extraction_completed_at = :completed_at"
            expression_values = {
                ':text': extracted_text,
                ':completed_at': current_time
            }
            
            # Add text length
            if extracted_text:
                update_expression += ", text_length = :length"
                expression_values[':length'] = len(extracted_text)
            
            # Update page
            response = self.pages_table.update_item(
                Key={'page_id': page_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ReturnValues='UPDATED_NEW'
            )
            
            logger.info(f"Page text update success: {page_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Page text update failed: {page_id}, error: {str(e)}")
            return False
    
    def update_document_processing_status(
        self,
        document_id: str,
        status: str,
        processing_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update document processing status
        
        Args:
            document_id: Document ID
            status: Processing status
            processing_metadata: Processing metadata
        
        Returns:
            Whether update succeeded
        """
        try:
            current_time = self.get_current_timestamp()
            
            # Basic update expression
            update_expression = "SET processing_status = :status, updated_at = :updated_at"
            expression_values = {
                ':status': status,
                ':updated_at': current_time
            }
            
            # Add processing metadata
            if processing_metadata:
                for key, value in processing_metadata.items():
                    attr_name = f"#{key}"
                    attr_value = f":{key}"
                    
                    update_expression += f", {attr_name} = {attr_value}"
                    expression_values[attr_value] = value
                    
                    # Set ExpressionAttributeNames (handle reserved words)
                    if 'ExpressionAttributeNames' not in locals():
                        expression_attribute_names = {}
                    expression_attribute_names[attr_name] = key
            
            # Update document
            update_params = {
                'Key': {'document_id': document_id},
                'UpdateExpression': update_expression,
                'ExpressionAttributeValues': expression_values,
                'ReturnValues': 'UPDATED_NEW'
            }
            
            if 'expression_attribute_names' in locals():
                update_params['ExpressionAttributeNames'] = expression_attribute_names
            
            response = self.documents_table.update_item(**update_params)
            
            logger.info(f"Document processing status update success: {document_id}, status: {status}")
            return True
            
        except ClientError as e:
            logger.error(f"Document processing status update failed: {document_id}, error: {str(e)}")
            return False
    
    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve page information
        
        Args:
            page_id: Page ID
        
        Returns:
            Page info or None
        """
        try:
            response = self.pages_table.get_item(
                Key={'page_id': page_id}
            )
            
            if 'Item' in response:
                logger.info(f"Page retrieval success: {page_id}")
                return response['Item']
            else:
                logger.warning(f"Page not found: {page_id}")
                return None
                
        except ClientError as e:
            logger.error(f"Page retrieval failed: {page_id}, error: {str(e)}")
            return None
    
    def batch_update_pages(self, page_updates: List[Dict[str, Any]]) -> int:
        """
        Batch update multiple pages
        
        Args:
            page_updates: List of page update info
                         [{'page_id': str, 'extracted_text': str}, ...]
        
        Returns:
            Number of successfully updated pages
        """
        success_count = 0
        
        for update_info in page_updates:
            page_id = update_info.get('page_id')
            extracted_text = update_info.get('extracted_text', '')
            
            if page_id and self.update_page_text(page_id, extracted_text):
                success_count += 1
        
        logger.info(f"Batch page update complete: {success_count}/{len(page_updates)}")
        return success_count
    
    def get_documents_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Retrieve documents with specific status
        
        Args:
            status: Processing status
        
        Returns:
            List of documents
        """
        try:
            response = self.documents_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('processing_status').eq(status)
            )
            
            documents = response.get('Items', [])
            logger.info(f"Documents by status retrieval complete: {status}, document count: {len(documents)}")
            
            return documents
            
        except ClientError as e:
            logger.error(f"Documents by status retrieval failed: {status}, error: {str(e)}")
            return []
    
    def check_table_health(self) -> Dict[str, bool]:
        """
        Check table health
        
        Returns:
            Table health info
        """
        health_status = {
            'documents_table': False,
            'pages_table': False
        }
        
        try:
            # Documents table health check
            response = self.documents_table.describe_table()
            if response['Table']['TableStatus'] == 'ACTIVE':
                health_status['documents_table'] = True
                
        except Exception as e:
            logger.error(f"Documents table health check failed: {str(e)}")
        
        try:
            # Pages table health check
            response = self.pages_table.describe_table()
            if response['Table']['TableStatus'] == 'ACTIVE':
                health_status['pages_table'] = True
                
        except Exception as e:
            logger.error(f"Pages table health check failed: {str(e)}")
        
        logger.info(f"Table health check complete: {health_status}")
        return health_status 