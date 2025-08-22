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
from datetime import datetime, timezone, timedelta
from threading import Lock

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
    # --- Instrumentation guard (prevent duplicate instrumentation) ---
    global _INSTRUMENTED
    if tracer_provider and HAS_OPENINFERENCE and not _INSTRUMENTED:
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        _INSTRUMENTED = True
    
    # default parameter settings
    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    temp = temperature or float(os.environ.get("TEMPERATURE", 0.3))
    tokens = max_tokens or int(os.environ.get("MAX_TOKENS", 64000))
    region_name = region or os.environ.get("AWS_REGION", "us-west-2")
    # ECS에서는 AWS_PROFILE이 없음 (Task Role 사용)
    profile_name = profile_name or os.environ.get("AWS_PROFILE")
    role_arn = os.environ.get("AWS_BEDROCK_ROLE_ARN", "")

    logger.info(f"initialize Bedrock model: {colorama.Fore.CYAN}{model_id}{colorama.Style.RESET_ALL}, temperature={colorama.Fore.CYAN}{temp}{colorama.Style.RESET_ALL}, max_tokens={colorama.Fore.CYAN}{tokens}{colorama.Style.RESET_ALL}, region={colorama.Fore.CYAN}{region_name}{colorama.Style.RESET_ALL}")
    
    if role_arn:
        # Assume role
        bedrock_client = _get_or_create_bedrock_client_with_role(role_arn, region_name)

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
            "model": model_id,
            "region_name": region_name,
            "temperature": temp,
            "max_tokens": tokens,
        }

        # ECS/컨테이너 환경 감지 (여러 환경 변수 확인)
        container_env_checks = {
            'AWS_EXECUTION_ENV': os.environ.get('AWS_EXECUTION_ENV'),
            'ECS_CONTAINER_METADATA_URI': os.environ.get('ECS_CONTAINER_METADATA_URI'),
            'ECS_CONTAINER_METADATA_URI_V4': os.environ.get('ECS_CONTAINER_METADATA_URI_V4'),
            'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI': os.environ.get('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI'),
            'dockerenv_exists': os.path.exists('/.dockerenv'),
        }
        
        is_container_env = any(container_env_checks.values())
        logger.info(f"Container environment check: {container_env_checks}")
        logger.info(f"Is container environment: {is_container_env}")
        logger.info(f"Profile name: {profile_name}")
        
        if is_container_env:
            logger.info("Using container credentials (Task Role or Instance Profile)")
            # Explicitly create (and cache) a client to prevent boto3 from using AWS_PROFILE from env
            bedrock_client = _get_or_create_container_bedrock_client(region_name)
            model_params["client"] = bedrock_client
        elif profile_name:
            model_params["credentials_profile_name"] = profile_name
            logger.info(f"Using AWS profile: {profile_name}")
        else:
            logger.info("Using default AWS credentials chain (no profile specified)")
    
    # add callbacks
    if callbacks:
        model_params["callbacks"] = callbacks
        
    # merge additional model parameters
    if model_kwargs:
        model_params.update(model_kwargs)      

    # --- LLM instance caching ---
    # Do NOT cache when role_arn is used because assumed credentials expire and boto3 client won't auto-refresh
    if os.environ.get("AWS_BEDROCK_ROLE_ARN"):
        logger.info("Skipping LLM cache due to role-based explicit credentials (short-lived)")
        return ChatBedrockConverse(**model_params)

    # Build cache key using stable parameters (ignore callbacks/tracer)
    cache_key = _build_llm_cache_key(
        model_id=model_id,
        region_name=region_name,
        temperature=temp,
        max_tokens=tokens,
        profile_name=profile_name,
        model_kwargs=model_kwargs or {},
        has_explicit_client="client" in model_params,
    )

    with _CACHE_LOCK:
        cached = _LLM_CACHE.get(cache_key)
        if cached is not None:
            logger.info(f"Reusing cached Bedrock model for key: {cache_key}")
            return cached

        model = ChatBedrockConverse(**model_params)
        _LLM_CACHE[cache_key] = model
        logger.info(f"Cached Bedrock model for key: {cache_key}")
        return model


# ---------------------------------
# Internal caching utilities
# ---------------------------------

_LLM_CACHE: Dict[str, ChatBedrockConverse] = {}
_BEDROCK_CLIENT_CACHE: Dict[str, Any] = {}
_ASSUMED_ROLE_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK: Lock = Lock()
_INSTRUMENTED: bool = False


def _build_llm_cache_key(
    model_id: str,
    region_name: str,
    temperature: float,
    max_tokens: int,
    profile_name: Optional[str],
    model_kwargs: Dict[str, Any],
    has_explicit_client: bool,
) -> str:
    # model_kwargs may be non-hashable; convert to sorted tuple of items for stability
    try:
        kwargs_part = ";".join([f"{k}={model_kwargs[k]}" for k in sorted(model_kwargs.keys())]) if model_kwargs else ""
    except Exception:
        kwargs_part = "unstable_kwargs"

    profile_part = profile_name or ""
    client_part = "client" if has_explicit_client else "no_client"
    # callbacks/tracer intentionally excluded to maximize reuse
    key = f"model={model_id}|region={region_name}|temp={temperature}|tokens={max_tokens}|profile={profile_part}|{client_part}|{kwargs_part}"
    return key


def _get_or_create_container_bedrock_client(region_name: str):
    client_key = f"container:{region_name}"
    with _CACHE_LOCK:
        client = _BEDROCK_CLIENT_CACHE.get(client_key)
        if client is not None:
            logger.info(f"Reusing cached container Bedrock client: {client_key}")
            return client

        session = boto3.Session()
        client = session.client("bedrock-runtime", region_name=region_name)
        _BEDROCK_CLIENT_CACHE[client_key] = client
        logger.info(f"Cached container Bedrock client: {client_key}")
        return client


def _get_or_create_bedrock_client_with_role(role_arn: str, region_name: str):
    """Create or reuse a Bedrock client using STS AssumeRole credentials with simple expiration handling."""
    cred_key = f"assumed:{role_arn}:{region_name}"
    now = datetime.now(timezone.utc)
    refresh_margin = timedelta(minutes=2)

    with _CACHE_LOCK:
        cached_cred = _ASSUMED_ROLE_CACHE.get(cred_key)
        if cached_cred is not None:
            exp: datetime = cached_cred.get("Expiration")
            if isinstance(exp, datetime) and exp - now > refresh_margin:
                client = _BEDROCK_CLIENT_CACHE.get(cred_key)
                if client is not None:
                    logger.info(f"Reusing cached Bedrock client (assumed role): {cred_key}")
                    return client
                # Rebuild client from cached credentials
                creds = cached_cred["Credentials"]
                client = boto3.client(
                    "bedrock-runtime",
                    region_name=region_name,
                    aws_access_key_id=creds["AccessKeyId"],
                    aws_secret_access_key=creds["SecretAccessKey"],
                    aws_session_token=creds["SessionToken"],
                )
                _BEDROCK_CLIENT_CACHE[cred_key] = client
                logger.info(f"Recreated Bedrock client from cached credentials: {cred_key}")
                return client

        # Assume new role credentials
        sts_client = boto3.client("sts")
        assumed_role = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="BedrockSession")

        # Normalize expiration to aware datetime
        exp = assumed_role["Credentials"].get("Expiration")
        if isinstance(exp, datetime):
            expiration = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        else:
            expiration = now + timedelta(hours=1)

        _ASSUMED_ROLE_CACHE[cred_key] = {
            "Credentials": assumed_role["Credentials"],
            "Expiration": expiration,
        }

        client = boto3.client(
            "bedrock-runtime",
            region_name=region_name,
            aws_access_key_id=assumed_role["Credentials"]["AccessKeyId"],
            aws_secret_access_key=assumed_role["Credentials"]["SecretAccessKey"],
            aws_session_token=assumed_role["Credentials"]["SessionToken"],
        )
        _BEDROCK_CLIENT_CACHE[cred_key] = client
        logger.info(f"Created and cached Bedrock client with assumed role: {cred_key}")
        return client