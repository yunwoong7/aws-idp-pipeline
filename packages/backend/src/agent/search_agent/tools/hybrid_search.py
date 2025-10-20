"""
Hybrid Search Tool - Combines semantic and keyword search
"""
import uuid
import requests
import logging
from typing import Optional

from .base import BaseTool, ToolResult, Reference
from ..config import config
from ..utils.response_formatter import format_api_response

logger = logging.getLogger(__name__)

# Get API base URL from config
API_BASE_URL = config.api_base_url


class HybridSearchTool(BaseTool):
    """
    Hybrid Search Tool for document search

    Performs hybrid search using semantic and keyword search to find relevant documents.
    This search combines vector similarity with keyword matching for better results.
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the Hybrid Search Tool

        Args:
            verbose: Whether to enable verbose logging
        """
        super().__init__(verbose=verbose)
        self.api_base_url = API_BASE_URL

    def get_name(self) -> str:
        """Return the name of the tool"""
        return "hybrid_search"

    def get_description(self) -> str:
        """Return the description of the tool"""
        return (
            "Perform hybrid search using semantic and keyword search to find relevant documents. "
            "This search combines vector similarity with keyword matching for better results."
        )

    async def execute(
        self,
        query: str,
        index_id: str = "",
        session_id: Optional[str] = None,
        size: int = 3
    ) -> ToolResult:
        """
        Execute hybrid search

        Args:
            query: Search query string - what you want to find in the documents
            index_id: Index ID for access control (must be provided for search)
            session_id: Session ID for reference deduplication (optional, auto-generated if not provided)
            size: Number of results to return (default: 3)

        Returns:
            ToolResult: Standardized result format with search results and references
        """
        try:
            # Validate index_id
            if not index_id:
                return self.create_error_result("Index ID is required for search")

            # Generate session_id if not provided
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.debug(f"Auto-generated session_id: {session_id}")

            if self.verbose:
                logger.info(f"Performing hybrid search: query={query}, index_id={index_id}, session_id={session_id}")

            # Call API
            url = f"{self.api_base_url}/api/opensearch/search/hybrid"

            payload = {
                "index_id": index_id,
                "query": query,
                "size": size
            }

            response = requests.post(url, json=payload, timeout=30)

            if response.status_code != 200:
                return self.create_error_result(f"Search API failed: HTTP {response.status_code}")

            # Get API response
            api_response = response.json()
            if session_id:
                api_response['_session_id'] = session_id

            # Format response with references
            formatted = format_api_response(api_response, 'hybrid_search', session_id)

            # Check if formatting was successful
            if not formatted.get('success', True):
                error_msg = formatted.get('error', 'Unknown error occurred')
                return self.create_error_result(f"Search failed: {error_msg}")

            # Extract search results
            data = formatted.get('data', {})
            results = data.get('results', [])

            # Process results and create standardized output
            processed_results = []
            references = []
            result_texts = []

            for idx, result in enumerate(results, 1):
                # Get content from various possible fields
                content = (
                    result.get('content_combined', '') or
                    result.get('content', '') or
                    result.get('text', '') or
                    result.get('segment_content', '') or
                    result.get('page_content', '') or
                    ''
                )

                doc_id = result.get('document_id', 'unknown')
                page_idx = result.get('page_index', 0)
                segment_idx = result.get('segment_index', page_idx)
                score = result.get('score', 0)
                file_name = result.get('file_name', 'Unknown')

                # Create processed result
                processed_result = {
                    'query': query,
                    'document_id': doc_id,
                    'file_name': file_name,
                    'segment_index': segment_idx,
                    'page_index': page_idx,
                    'content': content,
                    'score': score
                }
                processed_results.append(processed_result)

                # Create reference
                ref = self.create_reference(
                    ref_type="document",
                    value=f"{doc_id}_{segment_idx}",
                    title=f"{file_name} - Segment {segment_idx + 1}",
                    description=f"Score: {score:.3f}",
                    document_id=doc_id,
                    file_name=file_name,
                    segment_index=segment_idx,
                    page_index=page_idx,
                    score=score
                )
                references.append(ref)

                # Build result text
                if content:
                    result_texts.append(
                        f"[Result {idx}] {file_name} - Segment {segment_idx + 1}\n"
                        f"(Score: {score:.3f})\n"
                        f"Content: {content}"
                    )
                else:
                    result_texts.append(
                        f"[Result {idx}] {file_name} - Segment {segment_idx + 1}\n"
                        f"(Score: {score:.3f})\n"
                        f"Document ID: {doc_id}, Page: {page_idx}"
                    )

            summary_text = "\n\n".join(result_texts) if result_texts else "No results found."

            # Also add formatted references from response
            formatted_refs = formatted.get('references', [])
            for ref in formatted_refs:
                # Check if reference already exists
                if not any(r.get('id') == ref.get('id') for r in references):
                    references.append(ref)

            # Return standardized result
            return {
                "success": True,
                "count": len(processed_results),
                "results": processed_results,
                "references": references,
                "llm_text": summary_text,
                "error": None
            }

        except requests.exceptions.Timeout:
            logger.error("API call timeout (30 seconds)")
            return self.create_error_result("API call timeout (30 seconds)")

        except Exception as e:
            logger.error(f"Error in hybrid_search: {e}")
            return self.create_error_result(f"Error occurred during search: {str(e)}")
