"""
Image analysis tool
"""

import os
import json
import base64
import sys
from botocore.config import Config
import logging
import time
from typing import Dict, List, Any, Optional, ClassVar
from pydantic import BaseModel, Field
from PIL import Image
import io

        # Common module imports
sys.path.append('/opt/python')
from common import AWSClientFactory, S3Service
        
from .base import BaseTool, ToolResult
from prompts import prompt_manager

logger = logging.getLogger(__name__)

class AnalyzeImageInput(BaseModel):
    """Analyze images using an AI model."""
    image_paths: List[str] = Field(
        title="Image Path List",
        description="List of image file paths to analyze"
    )
    query: str = Field(
        title="Analysis Query",
        description="Question about the information to extract from the images (AI model will analyze this question)"
    )

class ImageAnalyzerTool(BaseTool):
    """Image analysis tool with Agent context integration
    Analyze images using an AI model with conversation history context.
    
    Args:
        query: Question about the information to extract from the images (AI model will analyze this question)
        
    Returns:
        ToolResult: Result of the image analysis
    """
    
    
    def __init__(self):
        super().__init__()
        
        self.s3_bucket_name = os.environ.get('S3_BUCKET_NAME')
        self.model_id = os.environ.get('BEDROCK_IMAGE_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
        self.max_tokens = int(os.environ.get('BEDROCK_IMAGE_MAX_TOKENS', 64000))
        
        # Initialize Common module services
        try:
            self.s3_service = S3Service()
            self.bedrock_client = AWSClientFactory.get_bedrock_runtime_client()
            logger.info("Completed AWS service client initialization")
        except Exception as e:
            logger.error(f"Failed to initialize AWS service client: {str(e)}")
            raise
    
    def get_schema(self) -> type:
        return AnalyzeImageInput
    
    def _get_agent_context_info(self, **kwargs) -> Dict[str, Any]:
        """Get agent context information from kwargs"""
        return {
            "index_id": kwargs.get("index_id", "unknown"),
            "document_id": kwargs.get("document_id", "unknown"),
            "segment_id": kwargs.get("segment_id", "unknown"),
            "image_path": kwargs.get("image_path"),
            "file_path": kwargs.get("file_path"),
            "segment_index": kwargs.get("segment_index"),
            "thread_id": kwargs.get("thread_id", "unknown"),
            "user_query": kwargs.get("user_query", ""),
            "previous_analysis_context": kwargs.get("previous_analysis_context", ""),
            "image_understanding": kwargs.get("image_understanding", ""),
        }



    def _resize_image_if_needed(self, image_data: bytes, max_size_mb: float = 4.5) -> bytes:
        """
        Resize image if it exceeds Bedrock API limit (5MB)
        
        Args:
            image_data (bytes): Original image data
            max_size_mb (float): Maximum size (MB)
            
        Returns:
            bytes: Resized image data
        """
        try:
            current_size_mb = len(image_data) / (1024 * 1024)
            max_bytes = int(max_size_mb * 1024 * 1024)
            
            logger.info(f"Image size check: {current_size_mb:.2f}MB (limit: {max_size_mb}MB)")
            
            if len(image_data) <= max_bytes:
                logger.info("Image size is within the limit - no resize needed")
                return image_data
            
            logger.info("Image size exceeds the limit - starting resize")
            
            # Load image with PIL
            image = Image.open(io.BytesIO(image_data))
            original_size = image.size
            
            # Calculate ratio (set to 80% of target size to leave some space)
            target_ratio = (max_bytes * 0.8 / len(image_data)) ** 0.5
            new_width = int(original_size[0] * target_ratio)
            new_height = int(original_size[1] * target_ratio)
            
            # Resize
            resized_image = image.resize((new_width, new_height), Image.LANCZOS)
            
            # Convert to bytes
            output_buffer = io.BytesIO()
            if image.mode in ('RGBA', 'LA'):
                # Save image with transparency as PNG
                resized_image.save(output_buffer, format='PNG', optimize=True)
            else:
                # Save image as JPEG (smaller file size)
                resized_image.save(output_buffer, format='JPEG', quality=85, optimize=True)
            
            resized_data = output_buffer.getvalue()
            resized_size_mb = len(resized_data) / (1024 * 1024)
            
            logger.info(f"Image resize completed:")
            logger.info(f"  Original: {original_size[0]}x{original_size[1]} ({current_size_mb:.2f}MB)")
            logger.info(f"  Resized: {new_width}x{new_height} ({resized_size_mb:.2f}MB)")
            logger.info(f"  Compression ratio: {(1 - len(resized_data)/len(image_data))*100:.1f}%")
            
            return resized_data
            
        except Exception as e:
            logger.error(f"Image resize failed: {str(e)}")
            logger.warning("Using original image (API limit exceeded risk)")
            return image_data

    def _resize_image_with_ratio(self, image_data: bytes, ratio: float) -> bytes:
        """
        Resize image with a specific ratio
        
        Args:
            image_data (bytes): Image data to resize
            ratio (float): Resize ratio (e.g., 0.8 for 80% of original size)
            
        Returns:
            bytes: Resized image data
        """
        try:
            logger.info(f"Applying additional resize with ratio: {ratio:.3f}")
            
            # Load image with PIL
            image = Image.open(io.BytesIO(image_data))
            original_size = image.size
            
            # Calculate new dimensions
            new_width = int(original_size[0] * ratio)
            new_height = int(original_size[1] * ratio)
            
            # Resize
            resized_image = image.resize((new_width, new_height), Image.LANCZOS)
            
            # Convert to bytes
            output_buffer = io.BytesIO()
            if image.mode in ('RGBA', 'LA'):
                # Save image with transparency as PNG
                resized_image.save(output_buffer, format='PNG', optimize=True)
            else:
                # Save image as JPEG (smaller file size)
                resized_image.save(output_buffer, format='JPEG', quality=80, optimize=True)
            
            resized_data = output_buffer.getvalue()
            resized_size_mb = len(resized_data) / (1024 * 1024)
            
            logger.info(f"Additional resize completed:")
            logger.info(f"  Original: {original_size[0]}x{original_size[1]}")
            logger.info(f"  Resized: {new_width}x{new_height} ({resized_size_mb:.2f}MB)")
            
            return resized_data
            
        except Exception as e:
            logger.error(f"Additional image resize failed: {str(e)}")
            logger.warning("Using original image")
            return image_data

    def execute(self, query: str = None, **kwargs) -> ToolResult:
        """Execute image analysis"""
        start_time = time.time()
        
        try:
            # Get information from Agent context
            agent_context = self._get_agent_context_info(**kwargs)
            index_id = agent_context.get('index_id', 'unknown')
            document_id = agent_context.get('document_id', 'unknown')
            segment_id = agent_context.get('segment_id', 'unknown')
            image_path = agent_context.get('image_path')
            
            logger.info(f"Image analysis started")
            logger.info(f"Index ID: {index_id}")
            logger.info(f"Document ID: {document_id}")
            logger.info(f"Segment ID: {segment_id}")
            logger.info(f"Image path: {image_path}")
            
            # Debug: Log entire Agent context
            logger.info(f"🔍 Agent context contents:")
            for key, value in agent_context.items():
                if key != "tool_registry_instance":
                    logger.info(f"  - {key}: {value}")
            
            # Determine image path
            if image_path:
                actual_image_paths = [image_path]
            else:
                return self._create_error_response("No image path provided")
            
            # Use planned query if available, otherwise use default
            planned_query = kwargs.get('planned_query', '')
            if not query:
                if planned_query:
                    query = planned_query
                else:
                    query = f"인덱스 '{index_id}'의 문서 이미지를 상세히 분석해주세요."
            
            # Log query content
            logger.info(f"Image analysis query: {query}")
            logger.info(f"Query length: {len(query)} characters")
            
            # Encode images from S3 to base64
            images_data = []
            processed_images = []

            logger.info(f"actual_image_paths: {actual_image_paths}")
            
            for img_path in actual_image_paths:
                try:
                    # Download image from S3
                    image_data = self._download_image_from_s3(img_path)
                    images_data.append(image_data)
                    processed_images.append(os.path.basename(img_path))
                    
                except Exception as e:
                    logger.error(f"Failed to download image {img_path}: {str(e)}")
                    return self._create_error_response(f"Failed to download image: {str(e)}")
            
            if not images_data:
                return self._create_error_response("No image to process")
            
            # Get analysis context (LangGraph State based)
            agent_context = self._get_agent_context_info(**kwargs)
            
            # Get previous analysis context  
            previous_analysis_context = agent_context.get('previous_analysis_context', '')
            
            if previous_analysis_context:
                logger.info(f"🔍 Using previous analysis context: {len(previous_analysis_context)} characters")
            else:
                previous_analysis_context = "**Previous analysis context**: No previous analysis results"
                logger.info("🔍 No previous analysis context - using default")
            
            # Analyze images with Bedrock
            analysis_result = self._analyze_with_bedrock(
                images_data, query, index_id, previous_analysis_context
            )

            if not analysis_result:
                return self._create_error_response("Failed to analyze images")
            
            # Create references for processed images
            references = []
            for i, img_path in enumerate(actual_image_paths, 1):
                references.append(self.create_reference(
                    ref_type="image",
                    value=img_path,
                    title=f"Analyzed Image {i}",
                    description=f"Image analyzed: {os.path.basename(img_path)}"
                ))
            
            # Create result data
            results = [{
                "analysis_type": "image_analyzer",
                "index_id": index_id,
                "processed_images": len(processed_images),
                "image_names": processed_images,
                "image_paths": actual_image_paths,
                "query": query,
                "ai_response": analysis_result,
                "model_version": self.model_id,
                "token_usage": getattr(self, '_last_token_usage', None)
            }]
            
            logger.info(f"Image analysis successful: {len(processed_images)} images processed")
            logger.info(f"Image analysis result: {analysis_result}")
            
            # Return in new ToolResult format
            return {
                "success": True,
                "count": len(results),
                "results": results,
                "references": references,
                "llm_text": analysis_result,
                "error": None
            }
            
        except Exception as e:
            error_msg = f"Image analysis failed: {str(e)}"
            logger.error(error_msg)
            return self._create_error_response(error_msg)
    
    def _download_image_from_s3(self, image_path: str) -> str:
        """Download image from S3 and encode to base64"""
        logger.info(f"Download image from S3 and encode to base64")
        logger.info(f"image_path: {image_path}")
        try:
            # Extract bucket and key from S3 URL (handle s3://bucket/key format)
            if image_path.startswith('s3://'):
                # Split s3://bucket/key format into bucket and key
                url_parts = image_path[5:].split('/', 1)  # Remove s3:// and split on first /
                bucket_name = url_parts[0]
                key = url_parts[1] if len(url_parts) > 1 else ''
                
                logger.info(f"S3 URL parsing result - Bucket: {bucket_name}, Key: {key}")
            else:
                # General S3 key format
                bucket_name = self.s3_bucket_name
                key = image_path
                
                logger.info(f"Using general S3 key - Bucket: {bucket_name}, Key: {key}")
            
            # Get image data from S3
            # logger.info(f"Attempting to download image from S3: s3://{bucket_name}/{key}")
            response = self.s3_service.get_object(key, bucket_name)
            
            image_bytes = response['Body'].read()
            original_size_mb = len(image_bytes) / (1024 * 1024)
            logger.info(f"Image size downloaded from S3: {original_size_mb:.2f}MB")
            
            # Resize image if needed for Bedrock API limit (considering base64 encoding overhead)
            # Base64 encoding increases size by ~33%, so we use a more conservative limit
            resized_image_bytes = self._resize_image_if_needed(image_bytes, max_size_mb=3.5)
            final_size_mb = len(resized_image_bytes) / (1024 * 1024)
            
            if original_size_mb != final_size_mb:
                logger.info(f"Image resize applied: {original_size_mb:.2f}MB → {final_size_mb:.2f}MB")
            
            # Encode to base64
            image_base64 = base64.b64encode(resized_image_bytes).decode('utf-8')
            
            # Check final base64 size to ensure it's within Bedrock limits
            base64_size_mb = len(image_base64.encode('utf-8')) / (1024 * 1024)
            logger.info(f"Final base64 encoded size: {base64_size_mb:.2f}MB")
            
            # If base64 size still exceeds 5MB, apply additional resizing
            if base64_size_mb > 4.8:  # Leave some buffer
                logger.warning(f"Base64 size ({base64_size_mb:.2f}MB) still too large, applying additional resize")
                # Calculate compression ratio needed
                target_ratio = (4.8 / base64_size_mb) ** 0.5
                additional_resized_bytes = self._resize_image_with_ratio(resized_image_bytes, target_ratio)
                image_base64 = base64.b64encode(additional_resized_bytes).decode('utf-8')
                final_base64_size_mb = len(image_base64.encode('utf-8')) / (1024 * 1024)
                logger.info(f"After additional resize, base64 size: {final_base64_size_mb:.2f}MB")
            
            return image_base64
            
        except Exception as e:
            logger.error(f"Failed to download image from S3 {image_path}: {str(e)}")
            
            # Additional debugging information
            if "NoSuchKey" in str(e):
                logger.error(f"Image does not exist: s3://{bucket_name}/{key}")
                
                # Search for similar paths
                try:
                    # Check parent folder
                    key_parts = key.split('/')
                    if len(key_parts) > 1:
                        prefix = '/'.join(key_parts[:-1]) + '/'
                        logger.info(f"Checking folder {prefix} contents")
                        
                        response = self.s3_service.list_objects_v2(bucket_name, prefix, max_keys=10)
                        
                        if 'Contents' in response:
                            logger.info(f"Files found in folder {prefix}:")
                            for obj in response['Contents']:
                                logger.info(f"  - {obj['Key']} (Size: {obj['Size']})")
                        else:
                            logger.warning(f"Folder {prefix} is empty or does not exist.")
                            
                        # Check if it's not an image folder, then check images folder
                        if not 'images' in prefix:
                            images_prefix = prefix + 'images/'
                            logger.info(f"Checking image folder {images_prefix}")
                            response = self.s3_service.list_objects_v2(bucket_name, images_prefix, max_keys=10)
                            if 'Contents' in response:
                                logger.info(f"Files found in image folder:")
                                for obj in response['Contents']:
                                    logger.info(f"  - {obj['Key']} (Size: {obj['Size']})")
                            else:
                                logger.warning(f"Image folder {images_prefix} is empty or does not exist.")
                                
                except Exception as search_error:
                    logger.warning(f"File search error: {str(search_error)}")
            
            raise
    
    def _analyze_with_bedrock(self, images_data: List[str], query: str, 
                             index_id: str,
                             previous_analysis_context: str) -> str:
        """Analyze images with Bedrock"""
        try:
            # Construct image content
            content_blocks = []

            logger.info(f"Previous analysis context length: {len(previous_analysis_context)} chars")
            
            # Generate image list string
            image_names = [f"image_{i+1}" for i in range(len(images_data))]
            images_str = ', '.join(image_names)
            
            # Get current date for context
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # Get prompts from YAML
            prompts = prompt_manager.get_prompt(
                'image_analyzer',
                'deep_image_analysis',
                images_str=images_str,
                previous_analysis_context=previous_analysis_context,
                index_id=index_id,
                query=query,
                current_date=current_date
            )
            
            system_instruction = prompts['system_prompt']
            user_prompt = prompts['user_prompt']

            content_blocks.append({
                "type": "text",
                "text": user_prompt
            })
            
            # Add images
            for i, image_data in enumerate(images_data):
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data
                    }
                })
            
            # Bedrock request
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.max_tokens,
                "temperature": 0.1,
                "system": system_instruction,  # System instruction separated
                "messages": [
                    {
                        "role": "user",
                        "content": content_blocks
                    }
                ]
            }

            # user_prompt is now logged by prompt_manager
            
            logger.info(f"Bedrock API call (model: {self.model_id}, images: {images_str})")
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            
            # Extract response
            if 'content' in response_body and response_body['content']:
                # Log token usage (from headers or body.usage)
                try:
                    headers = response.get('ResponseMetadata', {}).get('HTTPHeaders', {}) or {}
                    input_tokens = headers.get('x-amzn-bedrock-input-token-count')
                    output_tokens = headers.get('x-amzn-bedrock-output-token-count')
                    total_tokens = headers.get('x-amzn-bedrock-total-token-count')
                    # Fallback to body usage if available
                    if (input_tokens is None or output_tokens is None) and isinstance(response_body, dict) and response_body.get('usage'):
                        usage = response_body['usage']
                        input_tokens = input_tokens or usage.get('input_tokens')
                        output_tokens = output_tokens or usage.get('output_tokens')
                        total_tokens = total_tokens or usage.get('total_tokens')
                    logger.info(f"🔢 Bedrock Token Usage (image): input={input_tokens}, output={output_tokens}, total={total_tokens}")
                    # Attach for upstream aggregation if needed
                    self._last_token_usage = {
                        'input_tokens': int(input_tokens) if input_tokens is not None and str(input_tokens).isdigit() else None,
                        'output_tokens': int(output_tokens) if output_tokens is not None and str(output_tokens).isdigit() else None,
                        'total_tokens': int(total_tokens) if total_tokens is not None and str(total_tokens).isdigit() else None,
                    }
                except Exception as token_log_err:
                    logger.debug(f"Token usage logging skipped (image): {str(token_log_err)}")
                return response_body['content'][0]['text']
            else:
                logger.error(f"Bedrock response format error: {response_body}")
                return "Failed to parse image analysis response."
                
        except Exception as e:
            logger.error(f"Bedrock image analysis failed: {str(e)}")
            raise