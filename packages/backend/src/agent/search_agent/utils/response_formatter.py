"""
Standardized response formatter for Search Agent
Adapted from MCP server response_formatter.py
"""
import uuid
from typing import Dict, Any, List, Optional
from urllib.parse import unquote


class ResponseFormatter:
    """Response formatter for creating standardized responses with references"""

    def __init__(self):
        self.session_cache = {}  # Session-based cache for duplicate prevention

    def format(self, api_response: Dict[str, Any], tool_name: str,
               session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert API response to standardized format with references

        Args:
            api_response: Original API response
            tool_name: Name of the called tool
            session_id: Session ID (for duplicate prevention)
            **kwargs: Additional formatting options

        Returns:
            Standardized response dictionary
        """
        try:
            # Basic response structure
            formatted_response = {
                'success': api_response.get('success', True),
                'data': api_response.get('data', api_response),
                'error': api_response.get('error', None)
            }

            # References creation (optional)
            if kwargs.get('include_references', True):
                references = self._create_references(api_response, tool_name, session_id)
                if references:
                    formatted_response['references'] = references

            return formatted_response

        except Exception as e:
            return {
                'success': False,
                'data': api_response,
                'error': f"Error occurred during response formatting: {str(e)}",
                'references': []
            }

    def _create_references(self, api_response: Dict[str, Any],
                          tool_name: str, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Create references array from API response"""
        references = []

        try:
            if tool_name == 'hybrid_search':
                references = self._create_search_references(api_response, session_id)
        except Exception as e:
            print(f"Error occurred during references creation: {str(e)}")

        return references

    def _create_search_references(self, api_response: Dict[str, Any],
                                 session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Create references from search results"""
        references = []

        try:
            if not api_response.get('success', True):
                return references

            data = api_response.get('data', {})
            results = data.get('results', [])

            if not isinstance(results, list):
                return references

            # Session-based duplicate prevention
            session_key = session_id or 'default'
            if session_key not in self.session_cache:
                self.session_cache[session_key] = set()

            for result in results:
                if isinstance(result, dict):
                    # Check for duplicates
                    page_id = result.get('page_id', '')
                    if page_id and page_id in self.session_cache[session_key]:
                        continue

                    image_ref = self._create_search_image_reference(result)
                    if image_ref:
                        references.append(image_ref)
                        if page_id:
                            self.session_cache[session_key].add(page_id)

        except Exception as e:
            print(f"Error occurred during search references creation: {str(e)}")

        return references

    def _create_search_image_reference(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create image reference from search results"""
        try:
            # Use S3 URI
            image_uri = result.get('image_uri') or result.get('image_presigned_url')
            if not image_uri:
                return None

            page_index = result.get('page_index', 0)
            segment_index = result.get('segment_index', page_index)

            # Extract file name from various possible fields
            file_name = (result.get('file_name', '') or
                        result.get('filename', '') or
                        result.get('name', '') or
                        result.get('document_name', '') or
                        'Unknown File')

            reference = {
                'type': 'image',
                'title': f"Page {page_index}",
                'display_name': f"{file_name} - Segment {segment_index + 1}",
                'file_name': file_name,
                'page_number': int(page_index) if str(page_index).isdigit() else page_index,
                'page_index': page_index,
                'segment_index': segment_index,
                'value': image_uri,
                'image_uri': image_uri,
                'page_id': result.get('page_id', ''),
                'document_id': result.get('document_id', ''),
                'project_id': result.get('project_id', ''),
                'score': result.get('score', 0),
            }

            # Add PDF information
            file_uri = result.get('file_uri') or result.get('file_presigned_url')
            if file_uri:
                reference['file_uri'] = file_uri
                reference['linked_document'] = {
                    'document_id': result.get('document_id', ''),
                    'file_name': file_name,
                    'file_uri': file_uri
                }

            # Add highlight information
            highlight = result.get('highlight', {})
            if highlight:
                reference['metadata'] = {
                    'highlight': highlight,
                    'search_relevance': 'high'
                }

            return reference

        except Exception as e:
            print(f"Error occurred during search image reference creation: {str(e)}")
            return None


# Global formatter instance
_formatter_instance = None

def get_formatter() -> ResponseFormatter:
    """Return global formatter instance"""
    global _formatter_instance
    if _formatter_instance is None:
        _formatter_instance = ResponseFormatter()
    return _formatter_instance

def format_api_response(api_response: Dict[str, Any], tool_name: str,
                       session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Convenience function: Convert API response to standardized format

    Usage:
        result = format_api_response(api_response, 'hybrid_search')
    """
    formatter = get_formatter()
    return formatter.format(api_response, tool_name, session_id, **kwargs)
