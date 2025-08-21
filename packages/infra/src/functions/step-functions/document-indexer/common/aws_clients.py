"""
AWS Client Factory for unified client management across services.
"""

import boto3
import os
from typing import Optional
from botocore.config import Config
from opensearchpy import OpenSearch, AWSV4SignerAuth, RequestsHttpConnection
import logging

logger = logging.getLogger(__name__)


class AWSClientFactory:
    """Factory class for creating and managing AWS service clients."""
    
    _instances = {}
    
    @classmethod
    def get_dynamodb_resource(cls, region: Optional[str] = None) -> boto3.resource:
        """Get DynamoDB resource with singleton pattern."""
        key = f"dynamodb_{region or 'default'}"
        if key not in cls._instances:
            cls._instances[key] = boto3.resource(
                'dynamodb',
                region_name=region or os.environ.get('AWS_REGION', 'us-west-2')
            )
        return cls._instances[key]
    
    @classmethod
    def get_dynamodb_client(cls, region: Optional[str] = None) -> boto3.client:
        """Get DynamoDB client with singleton pattern."""
        key = f"dynamodb_client_{region or 'default'}"
        if key not in cls._instances:
            cls._instances[key] = boto3.client(
                'dynamodb',
                region_name=region or os.environ.get('AWS_REGION', 'us-west-2')
            )
        return cls._instances[key]
    
    @classmethod
    def get_s3_client(cls, region: Optional[str] = None, timeout: int = 3600) -> boto3.client:
        """Get S3 client with configurable timeout."""
        key = f"s3_{region or 'default'}_{timeout}"
        if key not in cls._instances:
            config = Config(
                read_timeout=timeout,
                connect_timeout=60,
                retries={'max_attempts': 3}
            )
            cls._instances[key] = boto3.client(
                's3',
                region_name=region or os.environ.get('AWS_REGION', 'us-west-2'),
                config=config
            )
        return cls._instances[key]
    
    @classmethod
    def get_opensearch_client(cls, 
                            endpoint: Optional[str] = None,
                            region: Optional[str] = None,
                            timeout: int = 30) -> OpenSearch:
        """Get OpenSearch client with AWS authentication."""
        endpoint = endpoint or os.environ.get('OPENSEARCH_ENDPOINT')
        region = region or os.environ.get('AWS_REGION', 'us-west-2')
        
        if not endpoint:
            raise ValueError("OpenSearch endpoint not provided")
        
        # Extract host from endpoint
        host = endpoint.replace('https://', '').replace('http://', '')
        
        key = f"opensearch_{host}_{region}_{timeout}"
        if key not in cls._instances:
            try:
                # Get AWS credentials
                credentials = boto3.Session().get_credentials()
                auth = AWSV4SignerAuth(credentials, region, 'es')
                
                # Create OpenSearch client
                client = OpenSearch(
                    hosts=[{'host': host, 'port': 443}],
                    http_auth=auth,
                    use_ssl=True,
                    verify_certs=True,
                    connection_class=RequestsHttpConnection,
                    timeout=timeout,
                    max_retries=3,
                    retry_on_timeout=True
                )
                
                cls._instances[key] = client
                logger.info(f"OpenSearch client created for {host}")
                
            except Exception as e:
                logger.error(f"Failed to create OpenSearch client: {str(e)}")
                raise
        
        return cls._instances[key]
    
    @classmethod
    def get_bedrock_runtime_client(cls, region: Optional[str] = None) -> boto3.client:
        """Get Bedrock Runtime client for embeddings."""
        key = f"bedrock_runtime_{region or 'default'}"
        if key not in cls._instances:
            cls._instances[key] = boto3.client(
                'bedrock-runtime',
                region_name=region or os.environ.get('AWS_REGION', 'us-west-2')
            )
        return cls._instances[key]
    
    @classmethod
    def get_sqs_client(cls, region: Optional[str] = None) -> boto3.client:
        """Get SQS client."""
        key = f"sqs_{region or 'default'}"
        if key not in cls._instances:
            cls._instances[key] = boto3.client(
                'sqs',
                region_name=region or os.environ.get('AWS_REGION', 'us-west-2')
            )
        return cls._instances[key]
    
    @classmethod
    def get_stepfunctions_client(cls, region: Optional[str] = None) -> boto3.client:
        """Get Step Functions client."""
        key = f"stepfunctions_{region or 'default'}"
        if key not in cls._instances:
            cls._instances[key] = boto3.client(
                'stepfunctions',
                region_name=region or os.environ.get('AWS_REGION', 'us-west-2')
            )
        return cls._instances[key]
    
    @classmethod
    def clear_cache(cls):
        """Clear all cached clients (useful for testing)."""
        cls._instances.clear()
    
    @classmethod
    def get_table_name(cls, table_type: str) -> str:
        """Get table names from environment variables."""
        table_env_vars = {
            'documents': 'DOCUMENTS_TABLE_NAME',
            'segments': 'SEGMENTS_TABLE_NAME',
            'indices': 'INDICES_TABLE_NAME',
        }
        
        if table_type not in table_env_vars:
            raise ValueError(f"Unknown table type: {table_type}")
        
        env_var = table_env_vars[table_type]
        table_name = os.environ.get(env_var)
        
        if not table_name:
            raise ValueError(f"Environment variable {env_var} is not set")
        
        return table_name
    
    @classmethod
    def get_bucket_name(cls, bucket_type: str = 'documents') -> str:
        """Get standardized bucket names."""
        if bucket_type == 'documents':
            return os.environ.get('DOCUMENTS_BUCKET_NAME', 
                                os.environ.get('S3_BUCKET_NAME', ''))
        else:
            raise ValueError(f"Unknown bucket type: {bucket_type}")