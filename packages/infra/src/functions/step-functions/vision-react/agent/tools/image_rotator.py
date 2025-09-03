"""
Image rotation tool (180 degrees, overwrite in-place on S3)
"""

import os
import logging
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from PIL import Image
import io
import sys

# Common module imports
sys.path.append('/opt/python')
from common import S3Service

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class RotateImageInput(BaseModel):
    """Rotate images by given degrees and overwrite the originals on S3.
    
    - degree: Rotation angle in degrees (positive values rotate counter-clockwise)
    - image_paths: Optional list of S3 URIs or keys. If omitted, uses current segment image.
    """
    degree: int = Field(
        default=180,
        title="Rotation Degree",
        description="Rotation angle in degrees (e.g., 90, 180, 270)"
    )
    image_paths: Optional[List[str]] = Field(
        default=None,
        title="Image Path List",
        description="List of image file paths (S3 URI or key) to rotate"
    )


class ImageRotateTool(BaseTool):
    """Rotate image(s) by specified degrees and overwrite in-place on S3.

    Behavior:
    - Downloads each image from S3
    - Rotates by provided degrees
    - Saves with the SAME format
    - Uploads back to the SAME key (overwrite)
    """

    def __init__(self):
        super().__init__()
        try:
            self.s3_service = S3Service()
            logger.info("Completed AWS S3 service initialization for ImageRotateTool")
        except Exception as e:
            logger.error(f"Failed to initialize S3 service: {str(e)}")
            raise

    def get_schema(self) -> type:
        return RotateImageInput

    def _get_agent_context_info(self, **kwargs) -> Dict[str, Any]:
        return {
            "index_id": kwargs.get("index_id", "unknown"),
            "document_id": kwargs.get("document_id", "unknown"),
            "segment_id": kwargs.get("segment_id", "unknown"),
            "image_path": kwargs.get("image_path"),
            "file_path": kwargs.get("file_path"),
            "segment_index": kwargs.get("segment_index"),
            "thread_id": kwargs.get("thread_id", "unknown"),
            "user_query": kwargs.get("user_query", ""),
        }

    def _rotate_image_bytes(self, image_bytes: bytes, target_format: Optional[str], degree: int) -> bytes:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Use optimized transpose for common 180 rotation
            if degree % 360 == 180:
                rotated = image.transpose(Image.ROTATE_180)
            else:
                # PIL rotates counter-clockwise; expand to preserve full content
                rotated = image.rotate(degree % 360, expand=True)

            # Determine save format
            save_format = target_format or getattr(image, 'format', None) or 'PNG'
            save_format = save_format.upper()
            if save_format in ("JPG",):
                save_format = "JPEG"

            # Convert mode for JPEG if needed
            if save_format == "JPEG" and rotated.mode in ("RGBA", "P", "LA"):
                rotated = rotated.convert("RGB")

            buffer = io.BytesIO()
            if save_format == "PNG":
                rotated.save(buffer, format=save_format, optimize=True)
            elif save_format == "JPEG":
                rotated.save(buffer, format=save_format, quality=90, optimize=True)
            else:
                rotated.save(buffer, format=save_format)

            return buffer.getvalue()
        except Exception as e:
            logger.error(f"Failed to rotate image bytes: {str(e)}")
            raise

    def _infer_format_from_content_type(self, content_type: Optional[str]) -> Optional[str]:
        if not content_type:
            return None
        try:
            c = content_type.lower()
            if "png" in c:
                return "PNG"
            if "jpeg" in c or "jpg" in c:
                return "JPEG"
            if "webp" in c:
                return "WEBP"
            if "tiff" in c or "tif" in c:
                return "TIFF"
            if "bmp" in c:
                return "BMP"
            return None
        except Exception:
            return None

    def execute(self, image_paths: Optional[List[str]] = None, degree: int = 180, **kwargs) -> ToolResult:
        """Rotate one or more images by specified degrees and overwrite them on S3."""
        try:
            agent_context = self._get_agent_context_info(**kwargs)
            index_id = agent_context.get('index_id')
            document_id = agent_context.get('document_id')
            segment_id = agent_context.get('segment_id')

            # Determine image paths
            paths: List[str] = []
            if image_paths:
                paths = image_paths
            else:
                # Fallback to single path from context
                single_path = agent_context.get('image_path')
                if not single_path:
                    return self._create_error_response("No image path(s) provided")
                paths = [single_path]

            processed: List[Dict[str, Any]] = []
            references = []

            for p in paths:
                logger.info(f"Rotating image by {degree} degrees: {p}")
                # Get original object (to obtain content type and bytes)
                obj = self.s3_service.get_object(p)
                content_type = obj.get('ContentType')
                original_bytes = obj['Body'].read()

                # Determine save format
                target_format = self._infer_format_from_content_type(content_type)

                # Rotate
                rotated_bytes = self._rotate_image_bytes(original_bytes, target_format, degree)

                # Overwrite same key
                # Parse URI to get bucket/key if needed handled by service in upload_file()
                # Ensure content type preserved
                bucket_name = None  # let service use default if key provided
                # If p is s3://..., parse bucket and key for logging only
                try:
                    if isinstance(p, str) and p.startswith('s3://'):
                        bkt, key = self.s3_service.parse_s3_uri(p)
                        upload_key = key
                        bucket_name = bkt
                    else:
                        upload_key = p
                except Exception:
                    upload_key = p

                self.s3_service.upload_file(
                    file_content=rotated_bytes,
                    s3_key=upload_key,
                    bucket_name=bucket_name,
                    content_type=content_type
                )

                processed.append({
                    "image_path": p,
                    "content_type": content_type or "",
                    "operation": f"rotate_{degree}",
                    "overwritten": True
                })

                references.append(self.create_reference(
                    ref_type="image",
                    value=p,
                    title="Rotated Image (180°)",
                    description="Image rotated by 180 degrees and overwritten"
                ))

            llm_text = (
                f"Rotated {len(processed)} image(s) by {degree} degrees and overwrote the originals.\n"
                f"Examples: {', '.join([d['image_path'] for d in processed[:3]])}"
            )

            return {
                "success": True,
                "count": len(processed),
                "results": [{
                    "index_id": index_id,
                    "document_id": document_id,
                    "segment_id": segment_id,
                    "items": processed
                }],
                "references": references,
                "llm_text": llm_text,
                "error": None
            }

        except Exception as e:
            error_msg = f"Image rotation failed: {str(e)}"
            logger.error(error_msg)
            return self._create_error_response(error_msg)


