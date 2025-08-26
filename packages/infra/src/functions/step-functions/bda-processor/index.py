"""
Bedrock Data Automation Lambda Function (Step Function)
First Step of Step Function
"""

import json
import os
import time
import logging
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional
from dataclasses import dataclass

# Common module imports
from common import (
    DynamoDBService,
    S3Service,
    AWSClientFactory,
    get_current_timestamp,
)

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()
s3_service = S3Service()
aws_clients = AWSClientFactory()

# Initialize AWS clients
bda_client = boto3.client('bedrock-data-automation')
bda_runtime_client = boto3.client('bedrock-data-automation-runtime')

# Environment variables
BDA_PROJECT_NAME = os.environ.get('BDA_PROJECT_NAME', 'aws-idp-ai-bda-project')
STAGE = os.environ.get('STAGE', 'prod')

@dataclass
class BDAProcessingResult:
    """BDA processing result"""
    success: bool
    index_id: str
    document_id: str
    bda_project_name: str
    bda_invocation_arn: Optional[str] = None
    status: str = 'STARTED'
    error: Optional[str] = None
    processing_time: float = 0

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    BDA processing main handler
    """
    start_time = time.time()
    
    try:
        logger.info(f"BDA processing started - Stage: {STAGE}")
        logger.info(f"Received event: {json.dumps(event, ensure_ascii=False, indent=2)}")
        
        # Validate input data
        validate_input(event)
        
        # Check if file type is supported by BDA
        file_type = event.get('file_type', '')
        
        if not is_bda_supported_file_type(file_type):
            # For unsupported file types (video, audio, etc.), skip BDA processing
            logger.info(f"File type {file_type} is not supported by BDA. Skipping BDA processing and returning success.")
            
            # Update document status to indicate basic processing completed
            update_document_status(event['document_id'], 'bda_skipped')
            
            processing_result = BDAProcessingResult(
                success=True,
                index_id=event['index_id'],
                document_id=event['document_id'],
                bda_project_name=BDA_PROJECT_NAME,
                bda_invocation_arn=None,  # No BDA invocation for unsupported types
                status='SKIPPED'  # Custom status for skipped files
            )
        else:
            # Check/create BDA project for supported file types
            bda_project_arn = ensure_bda_project()
            
            # Start BDA asynchronous processing
            processing_result = start_bda_processing(event, bda_project_arn)
        
        # Return result
        total_time = time.time() - start_time
        processing_result.processing_time = total_time
        
        response = {
            'success': processing_result.success,
            'index_id': processing_result.index_id,
            'document_id': processing_result.document_id,
            'bda_project_name': processing_result.bda_project_name,
            'bda_invocation_arn': processing_result.bda_invocation_arn,
            'status': processing_result.status,
            'processing_time': total_time,
            'stage': STAGE
        }
        
        if not processing_result.success:
            response['error'] = processing_result.error
        
        logger.info(f"BDA processing completed: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return response
        
    except Exception as e:
        error_message = f"BDA processing failed: {str(e)}"
        logger.error(error_message)
        
        return {
            'success': False,
            'index_id': event.get('index_id', 'unknown'),
            'document_id': event.get('document_id', 'unknown'),
            'error': error_message,
            'processing_time': time.time() - start_time,
            'stage': STAGE
        }

def validate_input(event: Dict[str, Any]) -> None:
    """
    Validate input data
    """
    required_fields = ['index_id', 'document_id', 'file_name', 'file_type', 'file_uri']
    
    for field in required_fields:
        if field not in event:
            raise ValueError(f"Missing required field: {field}")

def is_bda_supported_file_type(file_type: str) -> bool:
    """
    Check if file type is supported by BDA
    """
    bda_supported_types = [
        # Documents
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
        'application/msword',  # .doc
        'text/plain',  # .txt
        'application/rtf',  # .rtf
        'application/vnd.oasis.opendocument.text',  # .odt
        'application/dwg', 
        'application/dxf',
        # Images
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/bmp',
        'image/tiff',  # .tiff, .tif
        'image/webp',
        # Videos (MP4, MOV with H.264, H.265, VP8, VP9 codecs)
        'video/mp4',
        'video/quicktime',  # MOV files
        'video/x-msvideo',  # .avi
        'video/x-ms-wmv',  # .wmv
        'video/x-flv',  # .flv
        'video/x-matroska',  # .mkv
        'video/webm',
        'video/3gpp',
        # Audio (FLAC, M4A, MP3, Ogg, WAV)
        'audio/mp4',  # M4A
        'audio/mpeg',  # MP3
        'audio/flac',
        'audio/ogg',
        'audio/wav',
        'audio/x-wav',
        'audio/aac',
        'audio/x-ms-wma',
        'audio/aiff'
    ]
    return file_type.lower() in bda_supported_types

def update_document_status(document_id: str, status: str) -> None:
    """
    Update document status in Documents table
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
        
        logger.info(f"Document status updated: {document_id} -> {status}")
        
    except Exception as e:
        logger.error(f"Document status update failed: {str(e)}")

def ensure_bda_project() -> str:
    """
    Check and create BDA project
    """
    try:
        # Check existing project
        response = bda_client.list_data_automation_projects()

        print(response)
        
        for project in response.get('projects', []):
            if project['projectName'] == BDA_PROJECT_NAME:
                logger.info(f"Using existing BDA project: {project['projectArn']}")
                return project['projectArn']
        
        # Create new project if it doesn't exist
        logger.info(f"Creating new BDA project: {BDA_PROJECT_NAME}")
        
        # Standard output configuration (excluding LINE, WORD)
        standard_output_config = {
            "document": {
                "extraction": {
                    "granularity": {"types": ["DOCUMENT", "PAGE", "ELEMENT"]}, # ["DOCUMENT","PAGE", "ELEMENT","LINE","WORD"]
                    "boundingBox": {"state": "ENABLED"}
                },
                "generativeField": {"state": "ENABLED"},
                "outputFormat": {
                    "textFormat": {"types": ["MARKDOWN"]},  # ["PLAIN_TEXT", "MARKDOWN", "HTML", "CSV"]
                    "additionalFileFormat": {"state": "ENABLED"}
                }
            }
        }
        
        create_response = bda_client.create_data_automation_project(
            projectName=BDA_PROJECT_NAME,
            projectDescription="AWS IDP AI Analysis - Automated document processing",
            standardOutputConfiguration=standard_output_config
        )
        
        project_arn = create_response['projectArn']
        logger.info(f"BDA project created: {project_arn}")
        return project_arn
        
    except ClientError as e:
        logger.error(f"BDA project processing failed: {str(e)}")
        raise

def start_bda_processing(event: Dict[str, Any], bda_project_arn: str) -> BDAProcessingResult:
    """
    Start BDA asynchronous processing
    """
    try:
        # Get S3 URI from file_uri
        input_s3_uri = event['file_uri']
        
        # Configure BDA output path - same directory as input file, under bda/output/
        # s3://bucket/projects/project_id/documents/doc_id/file.pdf 
        # -> s3://bucket/projects/project_id/documents/doc_id/bda/output/
        file_dir = '/'.join(input_s3_uri.split('/')[:-1])  # Remove filename to get directory path
        bda_metadata_uri = f"{file_dir}/bda/output"
        
        logger.info(f"BDA input: {input_s3_uri}")
        logger.info(f"BDA output: {bda_metadata_uri}")
        
        # Get AWS account and region information
        import boto3
        session = boto3.Session()
        current_region = session.region_name
        sts_client = boto3.client('sts')
        account_id = sts_client.get_caller_identity()['Account']
        
        # boto3 version check is needed
        # The default boto3 version provided by Lambda may be outdated and cause issues
        # The version used here is 1.38.45
        logger.info(f"boto3 version: {boto3.__version__}")
        logger.info(f"BDA Project ARN: {bda_project_arn}")
        logger.info(f"Region: {current_region}, Account: {account_id}")
        
        # Update document status in Documents table to bda_analyzing
        update_document_status(event['document_id'], 'bda_analyzing')
        
        # Try with notebook-style parameters
        try:
            # First try: notebook-style parameters
            response = bda_runtime_client.invoke_data_automation_async(
                inputConfiguration={'s3Uri': input_s3_uri},
                outputConfiguration={'s3Uri': bda_metadata_uri},
                dataAutomationConfiguration={
                    'dataAutomationProjectArn': bda_project_arn,
                    'stage': 'LIVE'
                },
                dataAutomationProfileArn=f'arn:aws:bedrock:{current_region}:{account_id}:data-automation-profile/us.data-automation-v1'
            )
        except Exception as e1:
            logger.error(f"First try failed: {str(e1)}")
            # Second try: different parameter names
            try:
                response = bda_runtime_client.invoke_data_automation_async(
                    inputConfiguration={'s3Uri': input_s3_uri},
                    outputConfiguration={'s3Uri': bda_metadata_uri},
                    dataAutomationConfiguration={
                        'dataAutomationArn': bda_project_arn,
                        'stage': 'LIVE'
                    }
                )
            except Exception as e2:
                logger.error(f"Second try failed: {str(e2)}")
                raise e1  # Re-raise original error
        
        invocation_arn = response['invocationArn']
        logger.info(f"BDA asynchronous call started: {invocation_arn}")
        
        return BDAProcessingResult(
            success=True,
            index_id=event['index_id'],
            document_id=event['document_id'],
            bda_project_name=BDA_PROJECT_NAME,
            bda_invocation_arn=invocation_arn,
            status='STARTED'
        )
        
    except ClientError as e:
        error_message = f"BDA call failed: {str(e)}"
        logger.error(error_message)
        
        return BDAProcessingResult(
            success=False,
            index_id=event['index_id'],
            document_id=event['document_id'],
            bda_project_name=BDA_PROJECT_NAME,
            error=error_message,
            status='FAILED'
        ) 