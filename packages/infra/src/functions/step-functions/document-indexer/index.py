"""
Document Indexer Lambda
Read BDA result file, update Documents table, index Pages to OpenSearch, create Elements table
"""

import json
import logging
import os
import time
from decimal import Decimal
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError
from datetime import datetime, timezone

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

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()
s3_service = S3Service()
opensearch_service = OpenSearchService()

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Document Indexer Lambda handler
    Read BDA result file and process Documents/Pages/Elements
    
    Args:
        event: Event from Step Function (includes bda_metadata_uri)
        context: Lambda context
        
    Returns:
        Processing result
    """
    try:
        logger.info(f"Document Indexer started: {json.dumps(event, ensure_ascii=False, indent=2)}")
                
        # Environment variables are handled automatically in common module
        logger.info("Common service initialization complete")
        
        # Input data validation
        index_id = event.get('index_id')
        document_id = event.get('document_id')
        bda_metadata_uri = event.get('bda_metadata_uri')
        
        if not document_id:
            raise ValueError("document_id is required.")
        
        # bda_metadata_uri is optional for non-BDA supported files (video, audio, etc.)
        
        # Use common services (already initialized)
        logger.info("Ready to use common services")
        
        # Check document_id (lookup from Documents table)
        document = db_service.get_item('documents', {'document_id': document_id})
        if not document:
            raise ValueError(f"Document not found: {document_id}")
        media_type = document.get('media_type', 'DOCUMENT')
        
        # Update document status to document_indexing (start)
        try:
            current_time = get_current_timestamp()
            
            db_service.update_item(
                table_name='documents',
                key={'document_id': document_id},
                update_expression='SET #status = :status, updated_at = :updated_at',
                expression_attribute_names={'#status': 'status'},
                expression_attribute_values={
                    ':status': 'document_indexing',
                    ':updated_at': current_time
                }
            )
            logger.info(f"📝 Document status updated to document_indexing")
        except Exception as update_error:
            logger.warning(f"⚠️ Document status update failed (continuing): {str(update_error)}")
        
        # Branch by media_type
        if media_type == 'VIDEO':
            logger.info("Processing VIDEO BDA results")
            process_video_bda_results(index_id, document_id, media_type, bda_metadata_uri)
        elif media_type == 'DOCUMENT':
            if bda_metadata_uri:
                logger.info("Processing DOCUMENT BDA results")
                process_document_bda_results(index_id, document_id, media_type, bda_metadata_uri)
            else:
                logger.info("No BDA metadata URI - skipping BDA results processing for DOCUMENT")
                create_basic_page_metadata(index_id, document_id, media_type, document)
        elif media_type == 'IMAGE':
            if bda_metadata_uri:
                logger.info("Processing IMAGE BDA results")
                process_image_bda_results(index_id, document_id, media_type, bda_metadata_uri)
            else:
                logger.info("No BDA metadata URI - creating basic single-segment metadata for IMAGE")
                create_basic_page_metadata(index_id, document_id, media_type, document)
        else:
            # AUDIO 등 기타 타입도 VIDEO와 유사 분기 가능. 우선 기본 메타 생성
            if bda_metadata_uri:
                logger.info("BDA metadata URI found, processing as media (generic)")
                process_video_bda_results(index_id, document_id, media_type, bda_metadata_uri)
            else:
                create_basic_page_metadata(index_id, document_id, media_type, document)
        
        # Update document status to document_indexing_completed (complete)
        try:
            current_time = get_current_timestamp()
            
            db_service.update_item(
                table_name='documents',
                key={'document_id': document_id},
                update_expression='SET #status = :status, updated_at = :updated_at',
                expression_attribute_names={'#status': 'status'},
                expression_attribute_values={
                    ':status': 'document_indexing_completed',
                    ':updated_at': current_time
                }
            )
            logger.info(f"✅ Document status updated to document_indexing_completed")
        except Exception as update_error:
            logger.warning(f"⚠️ Document status update failed: {str(update_error)}")
        
        logger.info("Document Indexer complete")
        # Step Function 호환 응답 (Lambda 프록시 응답 대신 직접 반환)
        return {
            'success': True,
            'document_id': document_id,
            'media_type': media_type,  # media_type을 Step Function 출력에 추가
            'message': 'BDA result processing complete'
        }
        
    except Exception as e:
        logger.error(f"Document Indexer failed: {str(e)}")
        return handle_lambda_error(e)

def read_s3_json_file(s3_uri: str) -> Dict[str, Any]:
    """
    Read JSON file from S3
    
    Args:
        s3_uri: S3 URI (s3://bucket/path/to/file.json)
        
    Returns:
        JSON data
    """
    try:
        logger.info(f"Reading S3 file: {s3_uri}")
        
        # Use S3Service to get file content
        response = s3_service.get_object(s3_uri)
        content = response['Body'].read().decode('utf-8')
        
        result = json.loads(content)
        logger.info(f"S3 file read success: {len(content)} bytes")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to read S3 file: {str(e)}")
        raise

def convert_floats_to_decimals(obj):
    """
    Recursively convert floats to Decimals
    
    Args:
        obj: Object to convert
        
    Returns:
        Object with floats converted to Decimals
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(item) for item in obj]
    else:
        return obj

def process_document_bda_results(index_id: str, document_id: str, media_type: str, bda_metadata_uri: str) -> None:
    """
    Process BDA results and update Documents/Pages/Elements
    
    Args:
        bda_metadata_uri: job_metadata.json S3 URI
        document_id: Document ID
    """
    try:
        # 1. Read job_metadata.json
        logger.info("1. Reading job_metadata.json")
        job_metadata = read_s3_json_file(bda_metadata_uri)
        
        # 2. Extract standard_output_path
        standard_output_path = job_metadata["output_metadata"][0]["segment_metadata"][0]["standard_output_path"]
        logger.info(f"2. Extracted standard_output_path: {standard_output_path}")
        
        # 3. Read standard_output
        logger.info("3. Reading standard_output")
        standard_output = read_s3_json_file(standard_output_path)
        
        # 4. Calculate page count and update Documents table
        logger.info("4. Calculating page count and updating Documents table")
        document_data = standard_output.get("document", {})
        pages_data = standard_output.get("pages", [])
        page_count = len(pages_data)
        logger.info(f"Page count calculated from BDA result: {page_count}")
        
        update_documents_table(document_id, document_data, bda_metadata_uri, page_count)
        
        # 5. Create and update Pages DynamoDB
        logger.info("5. Creating and updating Pages DynamoDB")
        create_and_update_pages_table(index_id, document_id, pages_data, bda_metadata_uri)
        
        # 6. Index Pages to OpenSearch
        logger.info("6. Indexing Pages to OpenSearch")
        elements_data = standard_output.get("elements", [])
        index_pages_to_opensearch(index_id, document_id, media_type, pages_data, elements_data)
        
        try:
            # Lookup filename from Documents table
            document = db_service.get_item('documents', {'document_id': document_id})
            filename = document.get('filename', 'unknown_file') if document else 'unknown_file'
            
            # Extract BDA job ID (from bda_metadata_uri)
            bda_job_id = 'unknown'
            try:
                # URI format: s3://bucket/bda-results/job-id/job_metadata.json
                if 'bda-results/' in bda_metadata_uri:
                    bda_job_id = bda_metadata_uri.split('bda-results/')[1].split('/')[0]
            except:
                pass
        except Exception as activity_error:
            logger.warning(f"Failed to record BDA analysis completed activity: {str(activity_error)}")
        
        logger.info("BDA result processing complete")
        
    except Exception as e:
        logger.error(f"BDA result processing failed: {str(e)}")
        raise

def process_video_bda_results(index_id: str, document_id: str, media_type: str, bda_metadata_uri: Optional[str]) -> None:
    """
    Process VIDEO BDA results: update documents.summary, create segments per chapter, index OS with frames
    """
    try:
        if not bda_metadata_uri:
            logger.info("No BDA metadata for video - skipping")
            return

        document = db_service.get_item('documents', {'document_id': document_id})
        if not document:
            raise ValueError(f"Document not found: {document_id}")
        
        file_uri = document.get('file_uri', '')
        logger.info(f"Original video file_uri: {file_uri}")

        job_metadata = read_s3_json_file(bda_metadata_uri)
        standard_output_path = job_metadata["output_metadata"][0]["segment_metadata"][0]["standard_output_path"]
        standard_output = read_s3_json_file(standard_output_path)

        # Update documents.summary from standard_output.video.summary
        video = standard_output.get('video', {})
        doc_summary = video.get('summary', '')
        if doc_summary:
            db_service.update_item(
                table_name='documents',
                key={'document_id': document_id},
                updates={'bda_metadata_uri': bda_metadata_uri,
                         'description': doc_summary,
                         'status': 'bda_completed'}
            )

        chapters = standard_output.get('chapters', []) or video.get('chapters', [])
        if not chapters:
            logger.info("No chapters found in video standard_output")
            return

        logger.info(f"Video chapters detected: {len(chapters)} chapters")
        
        # Build segments and OS docs
        from boto3.dynamodb.conditions import Key
        # Create segments table entries and OS documents
        for chapter_idx, chapter in enumerate(chapters):
            segment_id = generate_uuid()

            segment_item = convert_floats_to_decimals({
                'segment_id': segment_id,
                'document_id': document_id,
                'index_id': index_id,
                'segment_index': chapter_idx,
                'segment_type': 'CHAPTER',
                'summary': chapter.get('summary', ''),
                'start_timecode_smpte': chapter.get('start_timecode_smpte'),
                'end_timecode_smpte': chapter.get('end_timecode_smpte'),
                'file_uri': file_uri,
                'status': 'bda_completed'
            })
            db_service.create_item('segments', segment_item)
            logger.info(f"Chapter {chapter_idx} segment created: {segment_id} (time: {chapter.get('start_timecode_smpte')} - {chapter.get('end_timecode_smpte')})")

            try:
                chapter_content = chapter.get('summary', f"Video chapter {chapter_idx + 1}")
                
                opensearch_service.add_bda_indexer_tool(
                    index_id=index_id,
                    document_id=document_id,
                    segment_id=segment_id,
                    segment_index=chapter_idx,
                    content=chapter_content,
                    file_uri=file_uri,
                    image_uri='',
                    elements=[],
                    media_type=media_type
                )
                logger.info(f"Chapter {chapter_idx} OpenSearch BDA tool added: {segment_id}")
            except Exception as os_error:
                logger.warning(f"OpenSearch BDA tool addition failed (continuing): {str(os_error)}")

        logger.info(f"Video chapters split complete: {len(chapters)} chapters stored in segments table")
    except Exception as e:
        logger.error(f"Video BDA processing failed: {str(e)}")
        raise

def process_image_bda_results(index_id: str, document_id: str, media_type: str, bda_metadata_uri: Optional[str]) -> None:
    """
    Process IMAGE BDA results: update documents, create 1 segment, index OS
    """
    try:
        if not bda_metadata_uri:
            logger.info("No BDA metadata for image - skipping")
            return

        # Load current document (to reuse file_uri)
        document = db_service.get_item('documents', {'document_id': document_id})
        if not document:
            raise ValueError(f"Document not found: {document_id}")
        file_uri = document.get('file_uri', '')

        # Read job metadata and standard output
        job_metadata = read_s3_json_file(bda_metadata_uri)
        standard_output_path = job_metadata["output_metadata"][0]["segment_metadata"][0]["standard_output_path"]
        standard_output = read_s3_json_file(standard_output_path)

        # Extract summary and image uri
        image_obj = standard_output.get('image', {}) or {}
        meta = standard_output.get('metadata', {}) or {}
        summary = image_obj.get('summary', '')

        # Build image s3 uri if possible
        image_uri = ''
        try:
            bucket = meta.get('s3_bucket')
            key = meta.get('s3_key')
            if bucket and key:
                image_uri = f"s3://{bucket}/{key}"
        except Exception:
            pass

        # 1) Update document minimal fields: description/summary/statistics/total_pages/status
        try:
            updates = {
                'bda_metadata_uri': bda_metadata_uri,
                'description': summary,
                'status': 'bda_completed',
                'total_pages': 1,
            }
            statistics = standard_output.get('statistics')
            if isinstance(statistics, dict):
                updates['statistics'] = convert_floats_to_decimals(statistics)

            db_service.update_item(
                table_name='documents',
                key={'document_id': document_id},
                updates=updates
            )
            logger.info("Documents table updated for IMAGE")
        except Exception as doc_update_err:
            logger.warning(f"Failed to update documents for IMAGE: {doc_update_err}")

        # 2) Create single IMAGE segment at index 0
        segment_id = generate_uuid()
        segment_item = convert_floats_to_decimals({
            'segment_id': segment_id,
            'document_id': document_id,
            'index_id': index_id,
            'segment_index': 0,
            'segment_type': 'IMAGE',
            'summary': summary or '',
            'image_uri': image_uri,
            'file_uri': file_uri,
            'status': 'bda_completed',
            'related_pages': []
        })
        db_service.create_item('segments', segment_item)
        logger.info(f"IMAGE segment created: {segment_id}")

        # 3) Index to OpenSearch (use summary + top text lines if any)
        content_parts: List[str] = []
        if summary:
            content_parts.append(summary)
        # Optionally include first N text lines for searchability
        try:
            text_lines = standard_output.get('text_lines') or []
            if isinstance(text_lines, list) and text_lines:
                top_lines = []
                for tl in text_lines[:10]:
                    txt = tl.get('text')
                    if isinstance(txt, str) and txt.strip():
                        top_lines.append(txt.strip())
                if top_lines:
                    content_parts.append('\n'.join(top_lines))
        except Exception:
            pass

        content = '\n\n'.join([p for p in content_parts if p])
        try:
            opensearch_service.add_bda_indexer_tool(
                index_id=index_id,
                document_id=document_id,
                segment_id=segment_id,
                segment_index=0,
                content=content or 'Image contents',
                file_uri=file_uri,
                image_uri=image_uri,
                elements=[],
                media_type=media_type
            )
            logger.info("IMAGE OpenSearch entry added")
        except Exception as os_err:
            logger.warning(f"OpenSearch indexing failed for IMAGE (continuing): {os_err}")

    except Exception as e:
        logger.error(f"Image BDA processing failed: {str(e)}")
        raise

def update_documents_table(
    document_id: str, 
    document_data: Dict[str, Any],
    bda_metadata_uri: str,
    page_count: int
) -> None:
    """
    Update Documents table (BDA document info and page count)
    
    Args:
        document_id: Document ID
        document_data: BDA document data
        bda_metadata_uri: BDA metadata URI
        page_count: Page count calculated from BDA result
    """
    try:
        update_data = {
            'bda_metadata_uri': bda_metadata_uri,
            'total_pages': page_count,  # Add calculated page count
            'status': 'bda_completed',  # Update to BDA analysis completed status
        }
        
        # Add BDA document info (including representation)
        if 'description' in document_data:
            update_data['description'] = document_data['description']
        
        if 'summary' in document_data:
            update_data['summary'] = document_data['summary']
        
        # Do not store representation info due to DynamoDB size limit (400KB)
        # Searchable in OpenSearch, so not needed in DynamoDB
        # if 'representation' in document_data:
        #     update_data['representation'] = document_data['representation']
        logger.info("representation field is not stored due to DynamoDB size limit")
        
        if 'statistics' in document_data:
            update_data['statistics'] = document_data['statistics']
        
        # Update Documents table
        try:
            # Dynamically build update_expression (handle DynamoDB reserved words)
            update_parts = []
            attr_values = {}
            attr_names = {}
            
            # DynamoDB reserved keywords
            reserved_keywords = {'status', 'timestamp', 'type', 'data', 'value', 'key', 'name', 'size'}
            
            for key, value in update_data.items():
                if key.lower() in reserved_keywords:
                    # Use ExpressionAttributeNames for reserved words
                    name_placeholder = f"#{key}"
                    value_placeholder = f":{key}"
                    update_parts.append(f"{name_placeholder} = {value_placeholder}")
                    attr_names[name_placeholder] = key
                    attr_values[value_placeholder] = value
                else:
                    # Normal attribute
                    value_placeholder = f":{key}"
                    update_parts.append(f"{key} = {value_placeholder}")
                    attr_values[value_placeholder] = value
            
            update_expression = "SET " + ", ".join(update_parts)
            
            kwargs = {
                'table_name': 'documents',
                'key': {'document_id': document_id},
                'update_expression': update_expression,
                'expression_attribute_values': attr_values
            }
            
            if attr_names:
                kwargs['expression_attribute_names'] = attr_names
            
            db_service.update_item(**kwargs)
            logger.info(f"Documents table update complete: {document_id}")
        except Exception as e:
            logger.warning(f"Documents table update failed: {document_id} - {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"Documents table update error: {str(e)}")
        raise

def create_and_update_pages_table(
    index_id: str,
    document_id: str,
    pages_data: List[Dict[str, Any]],
    bda_metadata_uri: str
) -> None:
    """
    Create Pages table (from BDA pages info) - only this function creates pages
    
    Args:
        document_id: Document ID
        pages_data: List of BDA pages data
        bda_metadata_uri: BDA metadata URI
    """
    try:
        logger.info(f"Starting creation of {len(pages_data)} segments in Segments table: {document_id}")
        
        for page_data in pages_data:
            page_index = page_data.get('page_index', 0)
            
            # Extract required data from BDA result
            representation = page_data.get('representation', {})
            statistics = page_data.get('statistics', {})
            asset_metadata = page_data.get('asset_metadata', {})
            
            # Extract image_uri (use rectified_image)
            image_uri = asset_metadata.get('rectified_image', '')
            
            # Always create new segment (PAGE type)
            segment_id = generate_uuid()
            logger.info(f"Creating segment(PAGE): document_id={document_id}, page_index={page_index}, segment_id={segment_id}")
            
            # Create page in Pages table (basic info) - apply Float → Decimal conversion
            # Exclude representation field due to DynamoDB size limit
            segment_item = convert_floats_to_decimals({
                'segment_id': segment_id,
                'document_id': document_id,
                'index_id': index_id,
                'segment_index': page_index,
                'segment_type': 'PAGE',
                'summary': '',
                'image_uri': image_uri,
                'bda_metadata_uri': bda_metadata_uri,
                'status': 'bda_processing',
                'related_pages': []
            })
            logger.info(f"Page {page_index}: representation field not stored due to DynamoDB size limit")
            
            # Create segment in Segments table
            db_service.create_item('segments', segment_item)
            logger.info(f"Segment creation complete: {segment_id} (page_index: {page_index})")
            
            # Immediately update with BDA details (Float → Decimal conversion)
            update_data = convert_floats_to_decimals({
                'statistics': statistics,                # Page statistics
                'analysis_started_at': datetime.utcnow().isoformat(),  # Analysis start time
                'page_status': 'bda_completed'           # BDA analysis completed status
            })
            
            # Update Pages table (dynamically build update_expression, handle DynamoDB reserved words)
            update_parts = []
            attr_values = {}
            attr_names = {}
            
            # DynamoDB reserved keywords
            reserved_keywords = {'status', 'timestamp', 'type', 'data', 'value', 'key', 'name', 'size'}
            
            for key, value in update_data.items():
                if key.lower() in reserved_keywords:
                    # Use ExpressionAttributeNames for reserved words
                    name_placeholder = f"#{key}"
                    value_placeholder = f":{key}"
                    update_parts.append(f"{name_placeholder} = {value_placeholder}")
                    attr_names[name_placeholder] = key
                    attr_values[value_placeholder] = value
                else:
                    # Normal attribute
                    value_placeholder = f":{key}"
                    update_parts.append(f"{key} = {value_placeholder}")
                    attr_values[value_placeholder] = value
            
            update_expression = "SET " + ", ".join(update_parts)
            
            kwargs = {
                'table_name': 'segments',
                'key': {'segment_id': segment_id},
                'update_expression': update_expression,
                'expression_attribute_values': attr_values
            }
            
            if attr_names:
                kwargs['expression_attribute_names'] = attr_names
            
            success = db_service.update_item(**kwargs)
            
            if success:
                logger.info(f"Segment BDA info update complete: {segment_id} (page_index: {page_index})")
            else:
                logger.warning(f"Segment BDA info update failed: {segment_id} (page_index: {page_index})")
        
        logger.info(f"Segments table creation and update complete: {document_id} - {len(pages_data)} segments")
        
    except Exception as e:
        logger.error(f"Pages table update error: {str(e)}")
        raise

def index_pages_to_opensearch(
    index_id: str,
    document_id: str,
    media_type: str,
    pages_data: List[Dict[str, Any]],
    elements_data: List[Dict[str, Any]] = None
) -> None:
    """
    Index Pages data to OpenSearch
    
    Args:
        document_id: Document ID
        pages_data: List of BDA pages data
        elements_data: List of BDA elements data
    """
    try:
        if not pages_data:
            logger.info("No Pages data, skipping indexing")
            return
        
        # Lookup file_uri from Documents table
        document = db_service.get_item('documents', {'document_id': document_id})
        if not document:
            raise ValueError(f"Document not found: {document_id}")
        
        file_uri = document.get('file_uri', '')
        logger.info(f"file_uri looked up from Documents table: {file_uri}")
        
        # Retrieve all segments of the document (for segment_index to segment_id mapping and image_uri lookup)
        from boto3.dynamodb.conditions import Key
        # Prefer segments table; normalize to segment-like dict
        try:
            # Get all segments with pagination support
            all_segments = []
            last_evaluated_key = None

            while True:
                seg_response = db_service.query_items(
                    table_name='segments',
                    key_condition_expression=Key('document_id').eq(document_id),
                    index_name='DocumentIdIndex',
                    exclusive_start_key=last_evaluated_key
                )
                seg_items = seg_response.get('Items', [])

                # Process items for the simplified format
                processed_items = [
                    {
                        'segment_id': item.get('segment_id'),
                        'segment_index': item.get('segment_index', 0),
                        'image_uri': item.get('image_uri', ''),
                    }
                    for item in seg_items
                ]
                all_segments.extend(processed_items)

                # Check if there are more pages
                last_evaluated_key = seg_response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break

            logger.info(f"Retrieved {len(all_segments)} segments with pagination")

        except Exception as e:
            logger.warning(f"Failed to get segments with pagination: {str(e)}")
            # Fallback to single page query
            segments_response = db_service.query_items(
                table_name='segments',
                key_condition_expression=Key('document_id').eq(document_id),
                index_name='DocumentIdIndex'
            )
            all_segments = segments_response.get('Items', [])

        segments_map = {int(segment['segment_index']): segment for segment in all_segments}
        
        for page_data in pages_data:
            page_index = page_data.get('page_index', 0)
            
            # Lookup actual segment_id
            existing_segment = segments_map.get(page_index)
            if not existing_segment:
                logger.warning(f"Page not found: document_id={document_id}, page_index={page_index}")
                continue
            
            segment_id = existing_segment.get('segment_id')
            
            # Extract page content (markdown representation)
            representation = page_data.get('representation', {})
            content = representation.get('markdown', '')
            
            # Extract page image URI (use rectified_image)
            asset_metadata = page_data.get('asset_metadata', {})
            image_uri = asset_metadata.get('rectified_image', '')
            
            logger.info(f"Page {page_index} info: content={len(content)} chars, image_uri={image_uri}")
            
            if content:
                # Filter elements for this page (exclude PARAGRAPH, PAGE_NUMBER)
                page_elements = []
                if elements_data:
                    for element in elements_data:
                        element_page_indices = element.get('page_indices', [])
                        if page_index in element_page_indices:
                            sub_type = element.get('sub_type', '')
                            if sub_type not in ['PARAGRAPH', 'PAGE_NUMBER']:
                                page_elements.append(element)
                
                # Index to OpenSearch using new page-unit storage method
                success = opensearch_service.add_bda_indexer_tool(
                    index_id=index_id,
                    document_id=document_id,
                    segment_id=segment_id,
                    segment_index=page_index,
                    content=content,
                    file_uri=file_uri,
                    image_uri=image_uri,
                    elements=page_elements,
                    media_type=media_type  # Documents 테이블의 media_type 사용
                )
                
                if success:
                    logger.info(f"📝 Page OpenSearch bda_indexer tool added: {segment_id}")
                else:
                    logger.error(f"❌ Failed to add page OpenSearch bda_indexer tool: {segment_id}")
                    raise Exception(f"Failed to add page OpenSearch bda_indexer tool: {segment_id}")
                    
    except Exception as e:
        logger.error(f"Pages OpenSearch indexing error: {str(e)}")
        raise


def create_basic_page_metadata(index_id: str, document_id: str, media_type: str, document: Dict[str, Any]) -> None:
    """
    Create basic page metadata for non-BDA supported files (video, audio, etc.)
    """
    try:
        logger.info(f"Creating basic page metadata for document: {document_id}")
        
        # Get file information
        file_name = document.get('file_name', '')
        file_type = document.get('file_type', '')
        file_uri = document.get('file_uri', '')
        total_pages = document.get('total_pages', 1)
        
        # Ensure total_pages is at least 1 for media files
        if not total_pages or total_pages < 1:
            total_pages = 1
        
        current_time = get_current_timestamp()
        
        # Create a single page entry for media files
        segment_id = generate_uuid()
        segment_item = {
            'segment_id': segment_id,
            'document_id': document_id,
            'index_id': index_id,
            'media_type': media_type,
            'segment_index': 0,  # Media files have only one logical "segment"
            'image_uri': '',  # No image for video/audio files
            'file_uri': file_uri,  # Reference to the original media file
            'status': 'completed',  # Mark as completed since no further processing needed
            'analysis_started_at': current_time,
            'analysis_completed_at': current_time,
            'representation': '',
            'statistics': {},
            'summary': f'Media file: {file_name} ({file_type})',
            'bda_metadata_uri': '',  # No BDA processing
            'related_pages': []
        }
        
        # Store page in Pages table
        success = db_service.create_item('segments', segment_item)
        
        if success:
            logger.info(f"Basic page metadata created for media file: {document_id}")
        else:
            logger.warning(f"Failed to create basic page metadata: {document_id}")
            
        # Create basic OpenSearch index entry for the media file
        try:
            opensearch_doc = {
                'document_id': document_id,
                'segment_id': segment_id,
                'segment_index': 0,
                'media_type': media_type,
                'file_name': file_name,
                'file_type': file_type,
                'file_uri': file_uri,
                'content': f'Media file: {file_name}',
                'tool_name': 'basic_indexer',
                'analysis_query': 'Basic media file indexing',
                'vector_dimensions': 0,
                'execution_time': 0,
                'created_at': current_time,
                'data_structure': 'media_file'
            }
            
            # Index to OpenSearch
            opensearch_service.index_document(
                index_name=index_id,
                doc_id=f"{document_id}_{segment_id}_basic",
                document=opensearch_doc
            )
            
            logger.info(f"Basic OpenSearch entry created for media file: {document_id}")
            
        except Exception as opensearch_error:
            logger.warning(f"OpenSearch indexing failed for media file (continuing): {str(opensearch_error)}")
        
    except Exception as e:
        logger.error(f"Failed to create basic page metadata: {str(e)}")
        raise

 