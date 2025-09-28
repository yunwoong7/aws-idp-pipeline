"""
PDF Text Extractor Lambda
Lambda function that directly extracts text from PDF files and indexes it into OpenSearch.
"""

import json
import logging
from typing import Dict, Any
from boto3.dynamodb.conditions import Key

# Common module imports
from common import (
    DynamoDBService,
    S3Service,
    OpenSearchService,
    handle_lambda_error,
    create_success_response,
    get_current_timestamp,
    generate_uuid
)

from utils.pdf_processor import PDFProcessor

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()
s3_service = S3Service()
opensearch_service = OpenSearchService()

def update_document_status(document_id: str, status: str) -> None:
    """
    Update document status in the Documents table (PRD schema compliant)
    """
    try:
        current_time = get_current_timestamp()
        
        db_service.update_item(
            table_name='documents',
            key={'document_id': document_id},
            update_expression='SET #status = :status, updated_at = :updated_at',
            expression_attribute_names={'#status': 'status'},
            expression_attribute_values={
                ':status': status,
                ':updated_at': current_time
            }
        )
        
        logger.info(f"Document status update complete: {document_id} -> {status}")
        
    except Exception as e:
        logger.error(f"Document status update failed: {str(e)}")
        # Status update failure does not stop the overall process

def lambda_handler(event: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    PDF Text Extractor Lambda handler
    Directly extracts text from PDF files and indexes it into OpenSearch
    
    Args:
        event: Event passed from Step Function
        context: Lambda context
    
    Returns:
        Processing result
    """
    try:
        logger.info(f"PDF Text Extractor started - Event: {json.dumps(event)}")
        
        # Common services automatically handle environment variables
        logger.info("Common services initialized successfully")
        
        # Extract required information from event
        document_id = event.get('document_id')
        media_type = event.get('media_type', 'DOCUMENT')  # media_type 추가
        
        if not document_id:
            raise ValueError("document_id is required.")
        
        logger.info(f"📄 Processing document: {document_id}, media_type: {media_type}")
        
        # Update to PDF text extracting status (PRD schema: pdf_text_extracting)
        update_document_status(document_id, 'pdf_text_extracting')
        
        # Use common services (already initialized)
        logger.info("Ready to use common services")
        
        pdf_processor = PDFProcessor()
        
        # Retrieve document info from Documents table
        document = db_service.get_item('documents', {'document_id': document_id})
        if not document:
            raise ValueError(f"Document not found: {document_id}")
        
        index_id = document.get('index_id', '')
        file_uri = document.get('file_uri', '')
        
        if not file_uri:
            raise ValueError(f"file_uri is missing for document: {document_id}")
        
        logger.info(f"Starting PDF text extraction - Document ID: {document_id}, File URI: {file_uri}")
        
        # Download PDF from S3 and extract text
        page_texts = pdf_processor.extract_text_from_pdf(file_uri)
        
        if not page_texts:
            logger.warning(f"No text extracted from PDF: {file_uri}")
            # Step Function 호환 응답 (Lambda 프록시 응답 대신 직접 반환)
            return {
                'success': True,
                'message': "No PDF text extraction result",
                'index_id': index_id,
                'document_id': document_id,
                'media_type': media_type,
                'pages_processed': 0
            }
        
        # Retrieve segment info from Segments table with pagination support
        segments = []
        last_evaluated_key = None

        while True:
            segments_response = db_service.query_items(
                table_name='segments',
                key_condition_expression=Key('document_id').eq(document_id),
                index_name='DocumentIdIndex',
                exclusive_start_key=last_evaluated_key
            )
            page_segments = segments_response.get('Items', [])
            segments.extend(page_segments)

            # Check if there are more pages
            last_evaluated_key = segments_response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break

        logger.info(f"Retrieved {len(segments)} segments with pagination for PDF text extraction")
        segment_map = {segment['segment_index']: segment for segment in segments}
        
        processed_pages = 0
        
        # Process each segment's text and index into OpenSearch
        for segment_index, text_content in enumerate(page_texts):
            # Check page info
            segment_info = segment_map.get(segment_index)
            if not segment_info:
                logger.warning(f"Segment info not found: segment_index={segment_index}")
                continue

            segment_id = segment_info['segment_id']

            # Handle empty pages - still process them with empty content
            if not text_content.strip():
                logger.debug(f"Segment {segment_index} has no text, processing with empty content")
                text_content = ""  # Use empty string instead of skipping

            # Add PDF text to OpenSearch using new page-unit storage method
            indexing_success = opensearch_service.add_pdf_text_extractor_tool(
                index_id=index_id,
                document_id=document_id,
                segment_id=segment_id,
                segment_index=segment_index,
                content=text_content,
                media_type=media_type
            )

            if indexing_success:
                processed_pages += 1
                logger.debug(f"📝 PDF text segment processed: {segment_id} (index: {segment_index})")
            else:
                logger.error(f"❌ PDF text OpenSearch indexing failed: {segment_id}")
        
        logger.info(f"PDF text extraction complete - Processed pages: {processed_pages}/{len(page_texts)}")
        
        # Update to PDF text extracted status (PRD schema: pdf_text_extracted)
        update_document_status(document_id, 'pdf_text_extracted')
        
        # Step Function 호환 응답 (Lambda 프록시 응답 대신 직접 반환)
        return {
            'success': True,
            'message': "PDF text extraction and indexing complete",
            'index_id': index_id,
            'document_id': document_id,
            'media_type': media_type,
            'total_pages': len(page_texts),
            'pages_processed': processed_pages,
            'file_uri': file_uri
        }
        
    except Exception as e:
        logger.error(f"PDF Text Extractor error: {str(e)}", exc_info=True)
        
        # On error, update document status (PRD schema: error)
        try:
            if 'document_id' in locals():
                update_document_status(document_id, 'error')
        except Exception as update_error:
            logger.error(f"Error status update failed: {str(update_error)}")
        
        return handle_lambda_error(e) 