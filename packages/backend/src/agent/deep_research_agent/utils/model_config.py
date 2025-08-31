"""
Model configuration utility for Deep Research Agent
"""
import os
import boto3
from typing import Optional

try:
    from strands.models import BedrockModel
except ImportError:
    # Mock for development
    class BedrockModel:
        def __init__(self, model_id: str, boto_session=None, max_tokens=None, **kwargs):
            self.model_id = model_id
            self.boto_session = boto_session
            self.max_tokens = max_tokens
            self.kwargs = kwargs


def get_bedrock_model(
    model_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    boto_session: Optional[boto3.Session] = None
) -> BedrockModel:
    """
    Create a Bedrock model with environment variable configuration
    
    Args:
        model_id: Model ID (defaults to env var or us.anthropic.claude-3-7-sonnet-20250219-v1:0)
        max_tokens: Maximum tokens (defaults to env var or 64000)
        temperature: Model temperature (defaults to env var or 0.3)
        boto_session: Custom boto3 session (defaults to default profile)
    
    Returns:
        BedrockModel instance
    """
    # Get configuration from environment variables with defaults
    model_id = model_id or os.getenv('DEEP_RESEARCH_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
    max_tokens = max_tokens or int(os.getenv('DEEP_RESEARCH_MAX_TOKENS', '2000'))  # 8000 → 2000으로 단축 (더 빠른 응답)
    temperature = temperature or float(os.getenv('DEEP_RESEARCH_TEMPERATURE', '0.8'))  # 0.3 → 0.8로 올려서 더 빠른 응답
    
    # Use provided session or default
    if boto_session is None:
        boto_session = boto3.Session()
    
    # Create Bedrock model
    bedrock_model = BedrockModel(
        model_id=model_id,
        boto_session=boto_session,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    return bedrock_model


def get_lead_researcher_model(boto_session: Optional[boto3.Session] = None) -> BedrockModel:
    """Get model configuration for Lead Researcher (optimized for speed)"""
    return get_bedrock_model(
        temperature=float(os.getenv('LEAD_RESEARCHER_TEMPERATURE', '0.7')),  # 0.3 → 0.7
        boto_session=boto_session
    )


def get_page_worker_model(boto_session: Optional[boto3.Session] = None) -> BedrockModel:
    """Get model configuration for Page Worker (optimized for speed)"""
    return get_bedrock_model(
        temperature=float(os.getenv('PAGE_WORKER_TEMPERATURE', '0.9')),  # 0.5 → 0.9
        boto_session=boto_session
    )


def print_model_configuration():
    """Print current model configuration information"""
    print("=" * 80)
    print("🤖 DEEP RESEARCH AGENT MODEL CONFIGURATION")
    print("=" * 80)
    
    # Get current configuration values
    model_id = os.getenv('DEEP_RESEARCH_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
    max_tokens = int(os.getenv('DEEP_RESEARCH_MAX_TOKENS', '2000'))
    base_temperature = float(os.getenv('DEEP_RESEARCH_TEMPERATURE', '0.8'))
    lead_temperature = float(os.getenv('LEAD_RESEARCHER_TEMPERATURE', '0.7'))
    worker_temperature = float(os.getenv('PAGE_WORKER_TEMPERATURE', '0.9'))
    
    print(f"📋 Model ID: {model_id}")
    print(f"🎯 Max Tokens: {max_tokens:,}")
    print(f"🌡️  Base Temperature: {base_temperature}")
    print(f"👔 Lead Researcher Temperature: {lead_temperature}")
    print(f"⚙️  Page Worker Temperature: {worker_temperature}")
    
    # Additional info
    region = os.getenv('AWS_DEFAULT_REGION', 'us-west-2')
    print(f"🌍 AWS Region: {region}")
    
    # Rate limiting info
    print(f"\n📊 Performance Settings:")
    print(f"   • Rate Limit: 1 request/second")
    print(f"   • Burst Capacity: 2 requests")
    print(f"   • Processing: Sequential (no parallel)")
    print(f"   • Estimated time for 101 segments: ~5-6 minutes")
    
    print("=" * 80)