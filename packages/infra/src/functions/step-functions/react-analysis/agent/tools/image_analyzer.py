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
from .state_aware_base import StateAwareBaseTool

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

class ImageAnalyzerTool(StateAwareBaseTool):
    """Image analysis tool with Agent context integration
    Analyze images using an AI model with conversation history context.
    
    Args:
        query: Question about the information to extract from the images (AI model will analyze this question)
        
    Returns:
        ToolResult: Result of the image analysis
    """
    
    supports_agent_context: ClassVar[bool] = True
    
    def __init__(self):
        super().__init__()
        # Use object.__setattr__ to bypass Pydantic field validation for instance attributes
        object.__setattr__(self, 's3_bucket_name', os.environ.get('S3_BUCKET_NAME'))
        object.__setattr__(self, 'model_id', os.environ.get('BEDROCK_IMAGE_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'))
        object.__setattr__(self, 'max_tokens', int(os.environ.get('BEDROCK_IMAGE_MAX_TOKENS', 8192)))
        
        # Initialize Common module services
        try:
            object.__setattr__(self, 's3_service', S3Service())
            object.__setattr__(self, 'bedrock_client', AWSClientFactory.get_bedrock_runtime_client())
            logger.info("Completed AWS service client initialization")
        except Exception as e:
            logger.error(f"Failed to initialize AWS service client: {str(e)}")
            raise
    
    def get_schema(self) -> type:
        return AnalyzeImageInput
    
    def _get_agent_context_info(self) -> Dict[str, Any]:
        """Get agent context information (LangGraph State based)"""
        try:
            # Use StateAwareBaseTool's get_agent_context
            agent_context = self.get_agent_context()
            
            # Check if necessary fields exist and set default values
            # Extract conversation_history from State's messages
            conversation_history = []
            if hasattr(self, '_state') and self._state and 'messages' in self._state:
                for msg in self._state['messages']:
                    if hasattr(msg, 'content') and hasattr(msg, '__class__'):
                        msg_type = msg.__class__.__name__
                        if msg_type == 'HumanMessage':
                            conversation_history.append({
                                "role": "user", 
                                "content": str(msg.content)
                            })
                        elif msg_type == 'AIMessage':
                            conversation_history.append({
                                "role": "assistant", 
                                "content": str(msg.content)
                            })
            
            return {
                "index_id": agent_context.get("index_id", "unknown"),
                "document_id": agent_context.get("document_id", "unknown"),
                "segment_id": agent_context.get("segment_id", "unknown"),
                "image_path": agent_context.get("image_path"),
                "file_path": agent_context.get("file_path"),
                "segment_index": agent_context.get("segment_index"),
                "thread_id": agent_context.get("thread_id", "unknown"),
                "user_query": agent_context.get("user_query", ""),
                "session_id": agent_context.get("session_id", ""),
                "conversation_history": conversation_history,
                "previous_analysis_context": agent_context.get("previous_analysis_context", ""),
                "combined_analysis_context": agent_context.get("combined_analysis_context", ""),
                "analysis_history": agent_context.get("analysis_history", []),
                "skip_opensearch_query": agent_context.get("skip_opensearch_query", False)
            }
            
        except Exception as e:
            logger.warning(f"Failed to get agent context: {str(e)}")
            return {
                "index_id": "unknown",
                "document_id": "unknown",
                "segment_id": "unknown",
                "image_path": None,
                "file_path": None,
                "segment_index": None,
                "thread_id": "unknown",
                "user_query": "",
                "session_id": "",
                "conversation_history": [],
                "previous_analysis_context": "",
                "combined_analysis_context": "",
                "analysis_history": [],
                "skip_opensearch_query": False,
                "error": f"Failed to get agent context: {str(e)}"
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
            agent_context = self._get_agent_context_info()
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
                return self._create_error_result("No image path provided", execution_time=time.time() - start_time)
            
            if not query:
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
                    return self._create_error_result(f"Failed to download image: {str(e)}", execution_time=time.time() - start_time)
            
            if not images_data:
                return self._create_error_result("No image to process", execution_time=time.time() - start_time)
            
            # Get analysis context (LangGraph State based)
            agent_context = self._get_agent_context_info()
            
            # Get combined analysis context
            combined_analysis_context = agent_context.get('combined_analysis_context', '')
            analysis_history = agent_context.get('analysis_history', [])
            
            if combined_analysis_context:
                # Use combined analysis context
                previous_analysis_context = combined_analysis_context
                logger.info(f"🔍 Using combined analysis context: {len(previous_analysis_context)} characters (history {len(analysis_history)} items)")
            else:
                # If no combined context, use default
                previous_analysis_context = "**Previous analysis context**: No previous analysis results"
                logger.info("🔍 No combined analysis context - using default")
            
            # Analyze images with Bedrock
            analysis_result = self._analyze_with_bedrock(
                images_data, query, index_id, previous_analysis_context
            )

            if not analysis_result:
                return self._create_error_result("Failed to analyze images", execution_time=time.time() - start_time)
            
            # Return success result (include query in analysis_query)
            result_data = {
                "analysis_type": "image_analyzer",
                "index_id": index_id,
                "processed_images": {
                    "total_processed": len(processed_images),
                    "image_names": processed_images,
                    "image_paths": actual_image_paths
                },
                "query": query,
                "analysis_query": query,
                "ai_response": analysis_result,
                "model_version": self.model_id,
                "token_usage": getattr(self, '_last_token_usage', None)
            }
            
            message = f"{analysis_result}"
            
            logger.info(f"Image analysis successful: {len(processed_images)} images processed")
            logger.info(f"Image analysis result: {analysis_result}")
            
            return self._create_success_result(message, result_data, execution_time=time.time() - start_time)
            
        except Exception as e:
            error_msg = f"Image analysis failed: {str(e)}"
            logger.error(error_msg)
            return self._create_error_result(error_msg, execution_time=time.time() - start_time)
    
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

            print(f"previous_analysis_context: {previous_analysis_context[:1000]}")
            
            # Analysis-focused prompt
            system_instruction = """You are a Technical Document Analysis Expert with deep expertise in interpreting complex technical documents, drawings, specifications, and engineering materials. Your role is to provide professional-level insights that go beyond surface-level observations to deliver meaningful technical and business value.

            ## Core Competencies:
            - Technical document interpretation (blueprints, specifications, manuals, reports, contracts)
            - Engineering and construction document analysis across all disciplines
            - Regulatory and compliance document review
            - Technical standards and code interpretation
            - Project documentation assessment and validation

            ## Document Types Expertise:
            - **Engineering Drawings**: Architectural, structural, MEP, civil, manufacturing drawings
            - **Technical Specifications**: Material specs, performance requirements, standards
            - **Project Documents**: Contracts, schedules, procedures, quality plans
            - **Regulatory Materials**: Codes, permits, inspection reports, compliance documents
            - **Manufacturing Documents**: Assembly instructions, quality control, maintenance manuals

            ## Analysis Approach:
            - Apply domain-specific expertise and industry knowledge
            - Focus on document intent, requirements, and practical implications
            - Consider regulatory compliance and industry best practices
            - Identify critical information, gaps, and potential issues
            - Provide actionable insights for decision-making

            ## Communication Standards:
            - Use appropriate technical terminology for the document type and audience
            - Support conclusions with evidence-based reasoning from the documents
            - Structure responses for maximum clarity and practical utility
            - Maintain objectivity while highlighting critical considerations and risks

            ## Key Responsibilities:
            1. **Content Interpretation**: Analyze the purpose, requirements, and implications of document content
            2. **Progressive Discovery**: Build knowledge incrementally across multiple analysis sessions
            3. **Quality Focus**: Prioritize novel insights and avoid redundant observations
            4. **Professional Value**: Deliver insights that support informed decision-making and project success

            Remember: Your expertise should provide sophisticated analysis that helps users understand the technical story, requirements, and implications behind the documented information."""
            
            # Generate image list string
            image_names = [f"image_{i+1}" for i in range(len(images_data))]
            images_str = ', '.join(image_names)
            
                        # User prompt (separate from system instruction)
            user_prompt = f"""
            You are an AI Technical Document Analysis Expert. Analyze the provided technical documents and deliver professional insights.

            <analysis_target_images>{images_str}</analysis_target_images>
            <previous_analysis_context>{previous_analysis_context}</previous_analysis_context>
            <index_id>{index_id}</index_id>
            <user_query>{query}</user_query>

            ## Analysis Guidelines:

            **Progressive Strategy**: Build upon previous findings, focus on NEW information not yet covered.

            **Key Priorities**:
            1. Identify document type and context
            2. Extract technical specifications and requirements  
            3. Analyze professional implications
            4. Highlight potential issues or optimization opportunities

            ## Output Structure:

            1. **Previous Findings Summary** (brief)
            2. **New Analysis Results**:
            - Technical specifications discovered
            - Design/requirements insights
            - Implementation considerations
            3. **Issues & Recommendations**

            **Focus**: Provide actionable professional insights, avoid redundancy with previous analysis, use appropriate technical terminology."""

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

            logger.info(f"user_prompt: {user_prompt}")
            
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