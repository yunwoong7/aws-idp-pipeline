# src/agent/tools/hybrid_search.py
import json
import logging
import os
import time
import requests
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from pathlib import Path
from dotenv import load_dotenv

from src.chat_agent.tools.base import BaseTool, ToolResult, Reference

# Path setup and environment variables loading
root_dir = Path(__file__).resolve().parents[3]
env_path = root_dir / '.env'
load_dotenv(env_path)

# Logging configuration
logger = logging.getLogger("HybridSearchTool")
logger.setLevel(logging.INFO)

# Load settings from environment variables
API_URL = os.environ.get("API_URL", "")
print(f"API_URL: {API_URL}")
SEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX_NAME", "construction-site-analysis")
MIN_SCORE = float(os.environ.get("MIN_SCORE", "0.1"))
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "5"))

# Define search input schema
class SearchInput(BaseModel):
   """Hybrid search input schema"""
   query: str = Field(
       title="Search Query",
       description="The query string to search for. It is a keyword or sentence to find relevant information in construction site data."
   )
   start_date: Optional[str] = Field(
       None,
       title="Search Start Date",
       description="The start date of the search (YYYYMMDD)"
   )
   end_date: Optional[str] = Field(
       None,
       title="Search End Date",
       description="The end date of the search (YYYYMMDD)"
   )
   limit: Optional[int] = Field(
       MAX_RESULTS,
       title="Result Limit",
       description="Maximum number of results to return"
   )
   index: Optional[str] = Field(
       SEARCH_INDEX,
       title="Search Index",
       description="Name of the search index to query"
   )

class HybridSearchTool(BaseTool):
    """
    OpenSearch Hybrid Search Tool
    
    This tool performs hybrid search on construction site image analysis data,
    combining keyword search and semantic search techniques.
    
    Usage:
    - query: Add keywords or phrases to search for in construction site data
    - start_date & end_date: Always use both parameters for date filtering
        - Format dates as YYYYMMDD (e.g., "20221111" for November 11, 2022)
        - For single day search, set both start_date and end_date to the same value
        - Example: For November 11, 2022, use start_date="20221111", end_date="20221111"
    - limit: Control the maximum number of results (default: 5)
    
    When searching for data from a specific date, it's critical to use the start_date
    and end_date parameters rather than adding date filters in the query text.
    """
   
    def __init__(self, api_url: str = API_URL, verbose: bool = False):
        """
        Initialize the Hybrid Search Tool
        
        Args:
            api_url: API URL for the search endpoint
            verbose: Whether to enable verbose logging
        """
        super().__init__(verbose=verbose)
        self.api_url = api_url.rstrip("/")
        
        if not self.api_url:
            logger.warning("API_URL is not set.")
    
    def get_schema(self) -> type:
        """
        Return the input schema for this tool
        
        Returns:
            Type: The input schema class
        """
        return SearchInput
    
    def execute(self, query: str, limit: int = MAX_RESULTS, start_date: Optional[str] = None, 
                end_date: Optional[str] = None, index: str = SEARCH_INDEX) -> ToolResult:
        """
        Execute the search with the given parameters
        
        Args:
            query: Search query
            limit: Maximum number of results
            start_date: Search start date
            end_date: Search end date
            index: Search index name
            
        Returns:
            ToolResult: Standardized result format
        """
        if not self.api_url:
            return self._create_error_response("API URL is not set.")
        
        try:
            # Configure the search API endpoint
            search_url = f"{self.api_url}/hybrid-search"
            
            # Configure the search parameters
            params = {
                "query": query,
                "limit": limit,
                "index": index,
                "min_score": MIN_SCORE,
                "start_date": start_date,
                "end_date": end_date
            }
            
            if self.verbose:
                logger.info(f"API call: URL={search_url}, params={json.dumps(params, ensure_ascii=False)}")
            
            # Call the API
            response = requests.post(search_url, json=params, timeout=10)
            response.raise_for_status()
            
            # Process the response
            raw_result = response.json()
            
            # Extract results based on the response structure
            results = []
            timing = {}
            
            # Handle different API response formats
            if isinstance(raw_result, dict):
                # Handle nested API Gateway response format
                if 'messageVersion' in raw_result and 'response' in raw_result:
                    if 'responseBody' in raw_result['response']:
                        response_body = raw_result['response']['responseBody']
                        if 'application/json' in response_body:
                            json_body = response_body['application/json']
                            if 'body' in json_body:
                                body = json_body['body']
                                results = body.get('results', [])
                                timing = body.get('timing', {})
                else:
                    # Handle direct API response format
                    results = raw_result.get('results', [])  
                    timing = raw_result.get('timing', {})
                    # Also check for 'items' key which might be used instead
                    if not results and 'items' in raw_result:
                        results = raw_result['items']
            
            # Process results and create references
            processed_results = []
            references = []
            text_parts = [f"# Search Results: '{query}' (Total: {len(results)} items)\n"]
            
            for i, result in enumerate(results, 1):
                # Create structured result
                processed_result = {
                    'query': query,
                    'filename': result.get('filename', ''),
                    'capture_date': result.get('capture_date', ''),
                    'analysis_text': result.get('analysis_text', ''),
                    'score': result.get('score', 0.0),
                    'id': result.get('id', '')
                }
                processed_results.append(processed_result)
                
                # Create reference information
                if 'filename' in result:
                    ref = self.create_reference(
                        ref_type="image",
                        value=result.get('filename', ''),
                        title=f"Image #{i}",
                        description=f"Capture Date: {result.get('capture_date', '')}"
                    )
                    references.append(ref)
                
                # Add text summary
                text_parts.extend([
                    f"## Image #{i} (Filename: {result.get('filename', '')}, Capture Date: {result.get('capture_date', '')})",
                    result.get('analysis_text', ''),
                    ""
                ])
            
            # Return standardized result
            return {
                "success": True,
                "count": len(processed_results),
                "results": processed_results,
                "references": references,
                "llm_text": "\n".join(text_parts),
                "error": None
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API call error: {str(e)}")
            return self._create_error_response(f"Search API error: {str(e)}")
        
        except Exception as e:
            logger.error(f"Unexpected error during search: {str(e)}")
            return self._create_error_response(f"Unexpected error: {str(e)}")
    
    def _create_error_response(self, error_message: str) -> ToolResult:
        """
        Create a standardized error response
        
        Args:
            error_message: The error message
            
        Returns:
            ToolResult: Error response in the standard format
        """
        return {
            "success": False,
            "count": 0,
            "results": [],
            "references": [],
            "llm_text": f"Error during search: {error_message}",
            "error": error_message
        }