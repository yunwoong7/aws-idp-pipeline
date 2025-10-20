"""
Image Analyzer Agent - Analyzes images for document search
"""
import logging
from typing import Dict, Any, List
from datetime import datetime
from io import BytesIO
from strands import Agent

from ..prompt import prompt_manager
from ..config import config

logger = logging.getLogger(__name__)


class ImageAnalyzerAgent:
    """
    Image analyzer agent that processes images to extract information for search
    """

    def __init__(self, model_id: str = None):
        """Initialize image analyzer agent"""
        self.model_id = model_id or config.get_user_model()
        self.agent = None

    def _create_agent(self):
        """Create Strands agent for image analysis"""
        # Get system prompt
        system_prompt = prompt_manager.format_system_prompt(
            'image_analyzer',
            variables={
                'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        )

        # Create agent
        self.agent = Agent(
            name="image_analyzer",
            system_prompt=system_prompt,
            tools=[],  # No tools for image analyzer
            model=self.model_id,
            callback_handler=None
        )

    def _preprocess_images(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Preprocess images: optimize size and format for LLM input

        Args:
            files: List of file dicts with 'data', 'type', 'name', 'size'

        Returns:
            List of ContentBlock dicts for Strands Agent
        """
        content_blocks = []

        try:
            from PIL import Image
        except ImportError:
            logger.error("PIL not available for image processing")
            return content_blocks

        for f in files:
            try:
                content_type = (f.get("type") or "").lower()
                raw_bytes = f.get("data")

                if not raw_bytes or not isinstance(raw_bytes, (bytes, bytearray)):
                    continue

                if content_type.startswith("image/"):
                    # Determine image format
                    image_format = "png"
                    if "jpeg" in content_type or "jpg" in content_type:
                        image_format = "jpeg"
                    elif "png" in content_type:
                        image_format = "png"

                    # Optimize image
                    processed = raw_bytes
                    try:
                        img = Image.open(BytesIO(raw_bytes))

                        # Resize if too large (max 1024px)
                        MAX_DIM = 1024
                        MAX_SIZE = 4 * 1024 * 1024  # 4MB
                        w, h = img.size

                        if w > MAX_DIM or h > MAX_DIM:
                            ar = w / h
                            if w >= h:
                                nw = MAX_DIM
                                nh = int(nw / ar)
                            else:
                                nh = MAX_DIM
                                nw = int(nh * ar)
                            img = img.resize((nw, nh), Image.LANCZOS)

                        # Save optimized image
                        out = BytesIO()
                        if image_format == "png":
                            img.save(out, format="PNG", optimize=True)
                        else:
                            if img.mode not in ("RGB", "L"):
                                img = img.convert("RGB")
                            img.save(out, format="JPEG", quality=85, optimize=True)

                        processed = out.getvalue()

                        # Further compress if still too large
                        if len(processed) > MAX_SIZE:
                            out = BytesIO()
                            if image_format == "png":
                                img.save(out, format="PNG", optimize=True, compress_level=9)
                            else:
                                if img.mode not in ("RGB", "L"):
                                    img = img.convert("RGB")
                                img.save(out, format="JPEG", quality=70, optimize=True)
                            processed = out.getvalue()

                    except Exception as e:
                        logger.warning(f"Image optimization failed, using original: {e}")
                        processed = raw_bytes

                    # Add to content blocks in Strands format
                    content_blocks.append({
                        "image": {
                            "format": image_format,
                            "source": {"bytes": processed}
                        }
                    })

                    logger.info(f"Preprocessed image: {f.get('name')} ({len(processed)} bytes)")

            except Exception as e:
                logger.error(f"Error preprocessing image {f.get('name')}: {e}")
                continue

        return content_blocks

    async def analyze(self, files: List[Dict[str, Any]]) -> str:
        """
        Analyze uploaded images and extract useful information for search

        Args:
            files: List of file dicts with image data

        Returns:
            Analysis text describing the images
        """
        if not files:
            logger.warning("No files provided to analyze")
            return ""

        try:
            # Create agent if not exists
            if not self.agent:
                self._create_agent()

            # Preprocess images to ContentBlocks
            image_blocks = self._preprocess_images(files)

            if not image_blocks:
                logger.warning("No valid images after preprocessing")
                return ""

            # Get instruction
            instruction = prompt_manager.format_instruction(
                'image_analyzer',
                variables={
                    'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            )

            # Combine: images first, then request
            multimodal_input = image_blocks + [{"text": instruction}]

            logger.info(f"Analyzing {len(image_blocks)} image(s)...")

            # Invoke image analyzer
            result = await self.agent.invoke_async(multimodal_input)

            # Extract analysis text from result
            analysis_text = ""
            if result:
                # Check if result has a 'content' attribute (Strands Message object)
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list) and len(content) > 0:
                        # Content is a list of content blocks
                        text_item = content[0]
                        if isinstance(text_item, dict):
                            analysis_text = text_item.get('text', '')
                        elif hasattr(text_item, 'text'):
                            analysis_text = text_item.text
                        else:
                            analysis_text = str(text_item)
                    elif isinstance(content, str):
                        analysis_text = content
                    else:
                        analysis_text = str(content)
                # Check if result is a dict
                elif isinstance(result, dict):
                    content = result.get('content', [])
                    if isinstance(content, list) and len(content) > 0:
                        text_item = content[0]
                        if isinstance(text_item, dict):
                            analysis_text = text_item.get('text', '')
                        else:
                            analysis_text = str(text_item)
                    elif isinstance(content, str):
                        analysis_text = content
                    else:
                        analysis_text = str(result)
                else:
                    analysis_text = str(result)

            logger.info(f"Image analysis completed: {len(analysis_text)} characters")
            return analysis_text

        except Exception as e:
            logger.error(f"Error analyzing images: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return ""
