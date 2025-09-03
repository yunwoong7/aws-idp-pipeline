"""
Common utilities for backend routers.
"""

import re
import os


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for BDA compatibility and safe storage."""
    # Get file extension
    name, ext = os.path.splitext(filename)
    
    # Remove or replace unsafe characters for BDA compatibility
    # BDA requires strict S3 URI patterns, so we'll be very conservative
    # Allow only alphanumeric, dots, hyphens, and underscores
    name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)  # Extensions should be clean
    
    # Remove consecutive underscores
    name = re.sub(r'_{2,}', '_', name)
    
    # Remove leading/trailing underscores and dots
    name = name.strip('_.')
    
    # Ensure name is not empty
    if not name:
        name = "file"
    
    # Limit total length (BDA has URI length limits)
    max_length = 100  # Conservative limit for BDA
    if len(name + ext) > max_length:
        name = name[:max_length-len(ext)]
    
    # Ensure the name starts and ends with alphanumeric (BDA pattern requirement)
    if name and not name[0].isalnum():
        name = 'f' + name[1:]
    if name and not name[-1].isalnum():
        name = name[:-1] + 'e'
    
    return name + ext