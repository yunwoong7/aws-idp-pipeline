"""
Utility functions for VerificationAgent
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Configuration constants
class VerificationConfig:
    """Configuration constants for verification agent"""
    MIN_CONTENT_LENGTH = 50
    MAX_CLAIMS_LIMIT = 20
    MIN_CLAIM_LENGTH = 20
    DEFAULT_CONFIDENCE = 0.0
    VALID_STATUSES = {"VERIFIED", "CONTRADICTED", "NOT_FOUND"}


def parse_json_response(response_text: str, expected_type: str = "object") -> Optional[Union[Dict[str, Any], List[Any]]]:
    """
    Parse JSON response with fallback handling
    
    Args:
        response_text: Raw response text from model
        expected_type: Expected type ("object" or "array")
        
    Returns:
        Parsed JSON or None if parsing fails
    """
    if not response_text:
        logger.warning("Empty response text provided for JSON parsing")
        return None
    
    try:
        # Find JSON in response based on expected type
        if expected_type == "array":
            start_char, end_char = '[', ']'
        else:
            start_char, end_char = '{', '}'
            
        start_idx = response_text.find(start_char)
        end_idx = response_text.rfind(end_char) + 1
        
        if start_idx != -1 and end_idx != -1:
            json_str = response_text[start_idx:end_idx]
            parsed_json = json.loads(json_str)
            
            # Validate type
            if expected_type == "array" and not isinstance(parsed_json, list):
                logger.warning(f"Expected array but got {type(parsed_json)}")
                return None
            elif expected_type == "object" and not isinstance(parsed_json, dict):
                logger.warning(f"Expected object but got {type(parsed_json)}")
                return None
                
            return parsed_json
        else:
            logger.warning(f"No JSON {expected_type} found in response")
            return None
            
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing JSON: {e}")
        return None


def extract_claims_fallback(response_text: str) -> List[str]:
    """
    Extract claims from text when JSON parsing fails
    
    Args:
        response_text: Raw response text
        
    Returns:
        List of extracted claims
    """
    claims = []
    lines = response_text.split('\n')
    
    for line in lines:
        line = line.strip()
        # Skip metadata lines
        if line and not line.startswith(('```', 'json', '{', '}', '#', '*')):
            # Remove numbering and quotes
            clean_line = line.lstrip('0123456789.- "').rstrip('"')
            if len(clean_line) >= VerificationConfig.MIN_CLAIM_LENGTH:
                claims.append(clean_line)
    
    logger.info(f"Extracted {len(claims)} claims using fallback method")
    return claims[:VerificationConfig.MAX_CLAIMS_LIMIT]


def validate_content_length(content: str, content_type: str) -> bool:
    """
    Validate content has sufficient length
    
    Args:
        content: Content to validate
        content_type: Type of content for logging
        
    Returns:
        True if content is valid
    """
    if not content or len(content.strip()) < VerificationConfig.MIN_CONTENT_LENGTH:
        logger.warning(f"{content_type} has insufficient content (length: {len(content) if content else 0})")
        return False
    return True


def validate_verification_status(status: str) -> str:
    """
    Validate and normalize verification status
    
    Args:
        status: Status to validate
        
    Returns:
        Valid status or NOT_FOUND if invalid
    """
    if status in VerificationConfig.VALID_STATUSES:
        return status
    
    logger.warning(f"Invalid status '{status}', defaulting to NOT_FOUND")
    return "NOT_FOUND"


def safe_float_conversion(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value or default
    """
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        logger.warning(f"Failed to convert '{value}' to float, using default {default}")
        return default