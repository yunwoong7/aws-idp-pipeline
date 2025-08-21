"""
LLM model service module
"""
import os
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from pathlib import Path
from langchain_aws.chat_models import ChatBedrockConverse
import logging
import boto3
import colorama

# logging configuration
logger = logging.getLogger(__name__)

# Load environment variables using path resolver
try:
    from ..utils.path_resolver import path_resolver
    env_path = path_resolver.project_root / '.env'
    load_dotenv(env_path)
    logger.info(f"Loaded environment from: {env_path}")
except ImportError:
    # Fallback to original logic
    root_dir = Path(__file__).resolve().parents[2]
    env_path = root_dir / '.env'
    load_dotenv(env_path)
    logger.warning("Path resolver not available, using fallback path logic")

# try to import OpenInference
try:
    from openinference.instrumentation.langchain import LangChainInstrumentor
    HAS_OPENINFERENCE = True
except ImportError:
    logger.warning("openinference package is not installed. tracing feature is disabled.")
    HAS_OPENINFERENCE = False



def get_llm(
        model_id: Optional[str] = None,
        region: Optional[str] = None, 
        temperature: Optional[float] = None, 
        max_tokens: Optional[int] = None,
        profile_name: Optional[str] = None,
        tracer_provider = None, 
        callbacks = None,
        model_kwargs: Optional[Dict[str, Any]] = None,
    ):
    """
    Initialize the BedrockChat class

    Args:
        model_id: Bedrock model ID (e.g., 'anthropic.claude-3-sonnet-20240229-v1:0')
        region: AWS region (default: environment variable or 'us-west-2')
        temperature: generation temperature (default: environment variable or 0.3)
        max_tokens: maximum number of tokens (default: environment variable or 4096)
        streaming: streaming support (default: True)
        profile_name: AWS profile name (default: environment variable or 'default')
        tracer_provider: OpenTelemetry tracer provider
        callbacks: list of LangChain callback handlers
        model_kwargs: additional arguments to pass to the model
    """
    if tracer_provider and HAS_OPENINFERENCE:
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
    
    # default parameter settings
    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    temp = temperature or float(os.environ.get("TEMPERATURE", 0.3))
    tokens = max_tokens or int(os.environ.get("MAX_TOKENS", 4096))
    region_name = region or os.environ.get("AWS_REGION", "us-west-2")
    profile_name = profile_name or os.environ.get("AWS_PROFILE", "default")
    role_arn = os.environ.get("AWS_BEDROCK_ROLE_ARN", "")

    logger.info(f"initialize Bedrock model: {colorama.Fore.CYAN}{model_id}{colorama.Style.RESET_ALL}, temperature={colorama.Fore.CYAN}{temp}{colorama.Style.RESET_ALL}, max_tokens={colorama.Fore.CYAN}{tokens}{colorama.Style.RESET_ALL}, region={colorama.Fore.CYAN}{region_name}{colorama.Style.RESET_ALL}")
    
    if role_arn:
        # Assume role
        sts_client = boto3.client('sts')
        assumed_role = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="BedrockSession"
        )

        # Create Bedrock client with assumed role credentials
        bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=region_name,
            aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
            aws_session_token=assumed_role['Credentials']['SessionToken']
        )

        model_params = {
            "client": bedrock_client,
            "model": model_id,
            "region_name": region_name,
            "temperature": temp,
            "max_tokens": tokens,
        }
    else:
        # model parameter configuration
        model_params = {
            "credentials_profile_name": profile_name,
            "model": model_id,
            "region_name": region_name,
            "temperature": temp,
            "max_tokens": tokens,
        }
    
    # add callbacks
    if callbacks:
        model_params["callbacks"] = callbacks
        
    # merge additional model parameters
    if model_kwargs:
        model_params.update(model_kwargs)      

    # initialize Bedrock model
    model = ChatBedrockConverse(**model_params)
    return model