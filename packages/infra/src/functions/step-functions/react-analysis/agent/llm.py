"""
Lambda environment LLM module
Optimized for Lambda environment based on Backend common/llm.py
"""

import os
import logging
import boto3
from typing import Dict, Optional, Any
from langchain_aws.chat_models import ChatBedrockConverse

logger = logging.getLogger(__name__)

def get_llm(
    model_id: Optional[str] = None,
    region: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model_kwargs: Optional[Dict[str, Any]] = None,
):
    """
    Initialize Bedrock model for Lambda environment
    
    Args:
        model_id: Bedrock model ID
        region: AWS region
        temperature: Generation temperature
        max_tokens: Maximum number of tokens
        model_kwargs: Additional arguments to pass to the model
    """
    # Set default parameters
    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    temp = temperature or float(os.environ.get("TEMPERATURE", "0.3"))
    tokens = max_tokens or int(os.environ.get("MAX_TOKENS", "64000"))
    region_name = region or os.environ.get("MODEL_REGION", "us-west-2")
    
    # Detailed model setup logging
    logger.info("🤖 BEDROCK LLM model initialization")
    logger.info("-" * 50)
    logger.info(f"Model ID: {model_id}")
    logger.info(f"Temperature: {temp}")
    logger.info(f"Max Tokens: {tokens}")
    logger.info(f"AWS Region: {region_name}")
    
    if model_kwargs:
        logger.info(f"Additional model parameters: {model_kwargs}")
    
    logger.info("-" * 50)
    
    # Configure model parameters
    model_params = {
        "model": model_id,
        "region_name": region_name,
        "temperature": temp,
        "max_tokens": tokens,
    }
    
    # Merge additional model parameters
    if model_kwargs:
        model_params.update(model_kwargs)
    
    try:
        # Initialize Bedrock model
        model = ChatBedrockConverse(**model_params)
        logger.info(f"✅ Bedrock model initialization successful!")
        return model
    except Exception as e:
        logger.error(f"❌ Bedrock model initialization failed: {str(e)}")
        raise 