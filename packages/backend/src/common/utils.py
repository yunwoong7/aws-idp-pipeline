"""
MCP tools related utility module
"""
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
import aiofiles
import logging
import os
import mimetypes
from io import BytesIO
from PIL import Image
import math
import re

# logging setup
logger = logging.getLogger(__name__)

# attachment file support formats and limits
SUPPORTED_DOCUMENT_FORMATS = {'pdf', 'csv', 'doc', 'docx', 'xls', 'xlsx', 'html', 'txt', 'md'}
SUPPORTED_IMAGE_FORMATS = {'png', 'jpeg', 'jpg', 'gif', 'webp'}
MAX_INDIVIDUAL_FILE_SIZE = 4.5 * 1024 * 1024  # 4.5 MB
MAX_TOTAL_FILES_SIZE = 25 * 1024 * 1024  # 25 MB

# add MIME type and file extension mapping
mimetypes.add_type('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx')
mimetypes.add_type('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx')

async def load_mcp_config(config_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    load MCP tools config file
    
    Args:
        config_path: config file path (default: None, use environment variable or default path)
        
    Returns:
        Dict: MCP server config info
    
    Raises:
        FileNotFoundError: config file not found
        json.JSONDecodeError: config file is not valid JSON
    """
    # if path is not specified, check environment variable and use default path
    if not config_path:
        config_path = os.getenv("MCP_CONFIG_PATH", "mcp_config.json")
    
    # if relative path, convert to absolute path based on current file
    if not os.path.isabs(config_path):
        config_path = Path(__file__).parent.parent / config_path
    
    logger.info(f"load MCP config file: {config_path}")
    
    try:
        # read file asynchronously
        async with aiofiles.open(config_path, "r") as f:
            content = await f.read()
            config = json.loads(content)
        
        # check if mcpServers key exists
        if "mcpServers" not in config:
            logger.warning("mcpServers key not found in config file. return empty dictionary")
            return {}
        
        # set default value for transport field in each server config
        # stdio: if command is npx
        # sse: otherwise (or if url is specified)
        servers = config["mcpServers"]
        for server_name, server_config in servers.items():
            if "transport" not in server_config:
                if "url" in server_config:
                    server_config["transport"] = "sse"
                elif "command" in server_config and server_config["command"] == "npx":
                    server_config["transport"] = "stdio"
                else:
                    server_config["transport"] = "stdio"  # default value
        
        logger.debug(f"load {len(servers)} MCP servers")
        return config
    
    except FileNotFoundError:
        logger.error(f"MCP config file not found: {config_path}")
        raise FileNotFoundError(f"MCP config file not found: {config_path}")
    
    except json.JSONDecodeError as e:
        logger.error(f"MCP config file is not valid JSON: {str(e)}")
        raise json.JSONDecodeError(f"MCP config file is not valid JSON", e.doc, e.pos)

async def process_attachments(files: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    process attachments and convert to LLM format

    Args:
        files: list of attachments from client

    Returns:
        Tuple[List[Dict[str, Any]], List[str]]: 
            - list of attachments to send to LLM
            - list of error messages
    """
    attachments = []
    errors = []
    total_size = 0

    for file_info in files:
        try:
            file_data = file_info.get('data', '')
            file_name = file_info.get('name', 'unknown file')
            file_type = file_info.get('type', '')
            
            # calculate file size
            if isinstance(file_data, bytes):
                file_size = len(file_data)
            elif isinstance(file_data, str):
                file_size = len(file_data.encode('utf-8') if not file_data.startswith('data:') else file_data)
            else:
                file_size = 0
                
            logger.info(f"첨부 파일 처리: {file_name} (타입: {file_type}, 크기: {file_size / 1024:.2f} KB)")
            
            # check file extension
            extension = ''
            if '.' in file_name:
                extension = file_name.rsplit('.', 1)[1].lower()
            elif file_type:
                # guess extension from MIME type
                guess_ext = mimetypes.guess_extension(file_type)
                if guess_ext:
                    extension = guess_ext[1:]  # remove first '.'
            
            logger.info(f"detected file extension: {extension}, MIME type: {file_type}")
            
            # check if file extension is supported
            if extension in SUPPORTED_DOCUMENT_FORMATS:
                file_format = 'document'
            elif extension in SUPPORTED_IMAGE_FORMATS or file_type.startswith('image/'):
                file_format = 'image'
            else:
                errors.append(f"unsupported file format: {file_name}")
                continue
            
            # check file size
            if file_size > MAX_INDIVIDUAL_FILE_SIZE:
                errors.append(f"file size is too large (max 4.5MB): {file_name}")
                continue
            
            # check total attachment size
            total_size += file_size
            if total_size > MAX_TOTAL_FILES_SIZE:
                errors.append("total attachment file size exceeds limit (25MB)")
                break
            
            # process file
            if file_format == 'document':
                # process document
                # clean file name - remove inappropriate characters and consecutive spaces
                # Bedrock requirement: file name must contain only alphabets, numbers, spaces, hyphens, parentheses, and brackets, no consecutive spaces
                clean_file_name = file_name
                # filter special characters (only alphabets, numbers, spaces, hyphens, parentheses, and brackets are allowed)
                clean_file_name = re.sub(r'[^\w\s\-\(\)\[\]]', '_', clean_file_name)
                # remove consecutive spaces
                clean_file_name = re.sub(r'\s+', ' ', clean_file_name)
                
                if clean_file_name != file_name:
                    logger.info(f"cleaned file name: '{file_name}' -> '{clean_file_name}'")
                    file_name = clean_file_name
                
                attachment = {
                    "document": {
                        "name": file_name,
                        "format": extension,
                        "source": {
                            "bytes": file_data
                        }
                    }
                }
                attachments.append(attachment)
                logger.info(f"processed document attachment: {file_name} ({file_size / 1024:.2f} KB)")
            
            elif file_format == 'image':
                # process image (add debug info)
                logger.info(f"processing image: {file_name}, data type: {type(file_data)}")
                
                try:
                    # set max image size (pixel based)
                    MAX_IMAGE_DIMENSION = 1024  # max 1024x1024
                    MAX_IMAGE_SIZE = 4 * 1024 * 1024  # max 4MB
                    
                    # create image object
                    img = None
                    processed_data = file_data  # use original data by default
                    
                    if isinstance(file_data, str) and file_data.startswith('data:image/'):
                        # process base64 encoded data
                        logger.info("processing base64 encoded data")
                        try:
                            image_data = file_data.split(',')[1]
                            processed_data = base64.b64decode(image_data)
                            img = Image.open(BytesIO(processed_data))
                        except Exception as e:
                            logger.warning(f"failed to load image from base64 data: {str(e)}")
                    
                    elif isinstance(file_data, bytes):
                        # bytes 데이터인 경우 이미지로 로드
                        logger.info("processing binary data")
                        try:
                            img = Image.open(BytesIO(file_data))
                        except Exception as e:
                            logger.warning(f"failed to load image from binary data: {str(e)}")
                    
                    # if image object is created, process optimization
                    if img:
                        # check original size
                        original_width, original_height = img.size
                        
                        # check if size adjustment is needed
                        if original_width > MAX_IMAGE_DIMENSION or original_height > MAX_IMAGE_DIMENSION:
                            # adjust size while maintaining aspect ratio
                            aspect_ratio = original_width / original_height
                            
                            if original_width > original_height:
                                new_width = MAX_IMAGE_DIMENSION
                                new_height = int(new_width / aspect_ratio)
                            else:
                                new_height = MAX_IMAGE_DIMENSION
                                new_width = int(new_height * aspect_ratio)
                            
                            # resize image
                            img = img.resize((new_width, new_height), Image.LANCZOS)
                            logger.info(f"resized image: {original_width}x{original_height} -> {new_width}x{new_height}")
                        
                        # compress and convert to binary
                        output = BytesIO()
                        
                        # set compression quality based on image format
                        quality = 85  # default compression quality
                        format_name = img.format if img.format else "JPEG"
                        
                        # if not RGB mode and no alpha channel, convert to RGB
                        if img.mode not in ("RGB", "RGBA"):
                            img = img.convert("RGB")
                        
                        # save image (compress)
                        img.save(output, format=format_name, quality=quality, optimize=True)
                        
                        # convert to binary data
                        processed_data = output.getvalue()
                        
                        # check size and additional compression (if needed)
                        compression_attempts = 0
                        while len(processed_data) > MAX_IMAGE_SIZE and compression_attempts < 3 and quality > 50:
                            # lower quality
                            quality = max(quality - 15, 50)
                            compression_attempts += 1
                            
                            output = BytesIO()
                            img.save(output, format=format_name, quality=quality, optimize=True)
                            processed_data = output.getvalue()
                            
                            logger.info(f"additional compression (quality: {quality}%): {len(processed_data) / 1024:.2f} KB")
                        
                        logger.info(f"image processing complete: {len(processed_data) / 1024:.2f} KB")
                    else:
                        logger.info(f"no optimization needed: using original data ({file_size / 1024:.2f} KB)")
                
                except Exception as e:
                    logger.error(f"error during image optimization: {str(e)}")
                    import traceback
                    logger.error(f"detailed error: {traceback.format_exc()}")
                    # if error occurs, use original data
                    processed_data = file_data
                
                if not processed_data:
                    logger.error("image data is empty")
                    errors.append(f"image data is empty: {file_name}")
                    continue
                
                # determine image MIME type
                media_type = file_type if file_type.startswith('image/') else f"image/{extension if extension else 'png'}"
                
                logger.info(f"image MIME type: {media_type}")
                
                # change image attachment format - directly pass binary data
                attachment = {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(processed_data).decode('utf-8')
                    }
                }
                attachments.append(attachment)
                logger.info(f"processed image attachment: {file_name} ({len(processed_data) / 1024:.2f} KB)")
        
        except Exception as e:
            logger.error(f"error during attachment processing: {str(e)}")
            import traceback
            logger.error(f"detailed error: {traceback.format_exc()}")
            errors.append(f"error during file processing: {file_name}")
    
    logger.info(f"attachment processing complete: {len(attachments)} processed, {len(errors)} errors")
    return attachments, errors

def create_message_with_attachments(
    message_text: str, 
    attachments: List[Dict[str, Any]]
) -> Union[str, Dict[str, Any]]:
    """
    create message object with text and attachments

    Args:
        message_text: user message text
        attachments: processed attachment list

    Returns:
        Union[str, Dict[str, Any]]: 
            - if no attachments: original message text
            - if attachments: composite message object
    """
    # if no attachments, return original message text
    if not attachments:
        return message_text
    
    # if attachments, create composite message object
    content = []
    
    # add each attachment to content array
    for attachment in attachments:
        content.append(attachment)
    
    # add text message to content array
    if message_text.strip():
        content.append({"text": message_text})
    
    # convert to Claude API format
    message = {
        "role": "user",
        "content": content
    }
    
    logger.info(f"message format: content array {len(content)} items (attachments {len(attachments)})")
    return message