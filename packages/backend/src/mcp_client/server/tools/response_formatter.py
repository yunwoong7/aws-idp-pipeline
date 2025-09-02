"""
Standardized response formatter for MCP server
- Preserve original API response as much as possible
- Optional references addition
- LLM guide for Agent
- Ensure consistent response structure
"""
import uuid
from typing import Dict, Any, List, Optional, Union
from urllib.parse import unquote


class ResponseFormatter:
    """Response formatter class"""
    
    def __init__(self):
        self.session_cache = {}  # Session-based cache for duplicate prevention
    
    def format(self, api_response: Dict[str, Any], tool_name: str, 
               session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert API response to standardized format
        
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
                'data': api_response.get('data', api_response),  # Unwrap nested data if present
                'error': api_response.get('error', None)
            }
            
            # References creation (optional)
            if kwargs.get('include_references', True):
                references = self._create_references(api_response, tool_name, session_id)
                if references:
                    formatted_response['references'] = references
            
            # LLM Guide creation (optional)
            if kwargs.get('include_llm_guide', True):
                llm_guide = self._create_llm_guide(tool_name, api_response)
                if llm_guide:
                    formatted_response['llm_guide'] = llm_guide
            
            # Lightweight enhancement for summary-only document analysis
            # Expose 'summary' at top-level for easy consumption by tools/UI
            if tool_name == 'get_document_analysis':
                try:
                    data = api_response.get('data', api_response)
                    summary_text = ''
                    if isinstance(data, dict):
                        # Prefer direct 'summary' key
                        summary_text = data.get('summary', '')
                        # Fallback: nested document object
                        if not summary_text and isinstance(data.get('document'), dict):
                            summary_text = data['document'].get('summary', '')
                    if summary_text:
                        formatted_response['summary'] = summary_text
                        # Avoid showing summary twice by removing from inner data
                        if isinstance(formatted_response.get('data'), dict) and 'summary' in formatted_response['data']:
                            try:
                                # Create a shallow copy and drop summary to keep other fields
                                inner = dict(formatted_response['data'])
                                inner.pop('summary', None)
                                formatted_response['data'] = inner
                            except Exception:
                                pass
                except Exception:
                    # Do not block formatting on summary extraction failures
                    pass

            return formatted_response
            
        except Exception as e:
            return {
                'success': False,
                'data': api_response,
                'error': f"Error occurred during response formatting: {str(e)}",
                'references': [],
                'llm_guide': "An error occurred. Please try another tool."
            }
    
    def _create_references(self, api_response: Dict[str, Any], 
                          tool_name: str, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Create references array from API response"""
        references = []
        
        try:
            # Branching based on tool_name
            if tool_name in ['get_document_analysis', 'get_page_analysis_details', 'get_document_info']:
                references = self._create_document_references(api_response, session_id)
            elif tool_name == 'hybrid_search':
                references = self._create_search_references(api_response, session_id)
            elif tool_name == 'get_documents_list':
                references = self._create_document_list_references(api_response)
            # Other tools can be added as needed
            
        except Exception as e:
            print(f"Error occurred during references creation: {str(e)}")
        
        return references
    
    def _create_document_references(self, api_response: Dict[str, Any], 
                                   session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Create references from document analysis results"""
        references = []
        
        try:
            # Extract data from successful response
            if not api_response.get('success', True):
                return references
            
            data = api_response.get('data', {})
            
            # If it's a page-by-page analysis result ('page' key exists)
            if 'page' in data:
                page_data = data['page']
                page_ref = self._create_page_reference_from_page_data(page_data, session_id)
                if page_ref:
                    references.append(page_ref)
                    
                # Add PDF reference
                pdf_ref = self._create_pdf_reference_from_page_data(page_data)
                if pdf_ref:
                    references.append(pdf_ref)
                    
            # If it's a document-wide analysis result with pages array
            elif 'pages' in data and isinstance(data['pages'], list):
                pages = data['pages']
                print(f"📄 Processing document analysis with {len(pages)} pages")
                
                # Create references from page data
                for page_info in pages:
                    if isinstance(page_info, dict):
                        # Create image reference for each page
                        image_ref = self._create_page_reference_from_page_data(page_info, session_id)
                        if image_ref:
                            references.append(image_ref)
                            print(f"📄 Added image reference for page {image_ref.get('page_number', 'unknown')}")
                        else:
                            print(f"📄 Failed to create image reference for page {page_info.get('page_index', 'unknown')}")
                
                # Add PDF reference using first page data
                if pages and len(pages) > 0:
                    first_page = pages[0]
                    pdf_ref = self._create_pdf_reference_from_page_data(first_page)
                    if pdf_ref:
                        references.append(pdf_ref)
                        print(f"📄 Added PDF reference: {pdf_ref.get('file_name', 'unknown')}")
                
                print(f"📄 Total references created: {len(references)}")
            
            # If it's a document-wide analysis result with document object
            elif 'document' in data:
                document = data['document']
                
                # Create references from page images
                page_images = document.get('page_images', [])
                if isinstance(page_images, list):
                    for page_info in page_images:
                        if isinstance(page_info, dict):
                            image_ref = self._create_image_reference(
                                page_info, document, session_id
                            )
                            if image_ref:
                                references.append(image_ref)
                
                # Add PDF reference for the document itself
                pdf_ref = self._create_pdf_reference(document)
                if pdf_ref:
                    references.append(pdf_ref)
            
            # If page_index or page_number exists in the data
            elif 'page_index' in data or 'page_number' in data:
                page_ref = self._create_page_specific_reference(data, session_id)
                if page_ref:
                    references.append(page_ref)
                
        except Exception as e:
            print(f"Error occurred during document references creation: {str(e)}")
        
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
    
    def _create_document_list_references(self, api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create references from document list - Add show_document_panel signal"""
        references = []
        
        try:
            if not api_response.get('success', True):
                return references
            
            # Add show_document_panel signal as the first reference
            references.append({
                'type': 'show_document_panel',
                'title': 'Document List Panel',
                'display_name': 'Open Document List Panel',
                'value': 'show_document_panel',
                'metadata': {
                    'action': 'open_document_panel',
                    'description': 'Signal to open the document list panel in the UI'
                }
            })
            
            data = api_response.get('data', {})
            documents = data.get('documents', [])
            
            if not isinstance(documents, list):
                return references
            
            for doc in documents:
                if isinstance(doc, dict):
                    pdf_ref = self._create_pdf_reference(doc)
                    if pdf_ref:
                        references.append(pdf_ref)
                        
        except Exception as e:
            print(f"Error occurred during document list references creation: {str(e)}")
        
        return references
    
    def _create_image_reference(self, page_info: Dict[str, Any], 
                               document: Dict[str, Any], 
                               session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create image reference from page information (return S3 URI, remove Pre-signed URL)"""
        try:
            # Basic fields
            page_number = page_info.get('page_number', 0)
            # Use pure S3 URI instead of Pre-signed URL
            image_uri = page_info.get('image_uri') or page_info.get('image_url')
            
            if not image_uri:
                return None
            
            # Create page identifier
            page_id = page_info.get('page_id') or f"page_{page_number}"
            
            reference = {
                'type': 'image',
                'title': f"Page {page_number}",
                'display_name': f"Page {page_number} of {document.get('file_name', 'Unknown')}",
                'file_name': document.get('file_name', 'Unknown'),
                'page_number': int(page_number) if str(page_number).isdigit() else page_number,
                'value': image_uri,  # Return S3 URI
                'image_uri': image_uri,  # Pure S3 URI
                'page_id': page_id,
                'document_id': document.get('document_id', ''),
                'project_id': document.get('project_id', ''),
                'created_at': page_info.get('analysis_completed_at', ''),
            }
            
            # Add PDF information (linked_document) - Use S3 URI
            file_uri = document.get('file_uri')
            if file_uri:
                reference['file_uri'] = file_uri  # Pure S3 URI
                reference['linked_document'] = {
                    'document_id': document.get('document_id', ''),
                    'file_name': document.get('file_name', ''),
                    'file_uri': file_uri  # S3 URI
                }
            
            # Add metadata
            reference['metadata'] = {
                'page_index': page_info.get('page_index', page_number),
                'analysis_status': page_info.get('page_status', 'unknown'),
                'session_id': session_id
            }
            
            return reference
            
        except Exception as e:
            print(f"Error occurred during image reference creation: {str(e)}")
            return None
    
    def _create_search_image_reference(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create image reference from search results (return S3 URI, remove Pre-signed URL)"""
        try:
            # Use pure S3 URI instead of Pre-signed URL
            image_uri = result.get('image_uri') or result.get('image_presigned_url')
            if not image_uri:
                return None
            
            page_number = result.get('page_index', 0)
            
            reference = {
                'type': 'image',
                'title': f"Search Result - Page {page_number}",
                'display_name': f"Page {page_number}",
                'file_name': 'Search Result',
                'page_number': int(page_number) if str(page_number).isdigit() else page_number,
                'value': image_uri,  # Return S3 URI
                'image_uri': image_uri,  # Pure S3 URI  
                'page_id': result.get('page_id', ''),
                'document_id': result.get('document_id', ''),
                'project_id': result.get('project_id', ''),
                'created_at': '',
            }
            
            # Add PDF information - Use S3 URI
            file_uri = result.get('file_uri') or result.get('file_presigned_url')
            if file_uri:
                reference['file_uri'] = file_uri  # Pure S3 URI
                reference['linked_document'] = {
                    'document_id': result.get('document_id', ''),
                    'file_name': 'Search Document',
                    'file_uri': file_uri  # S3 URI
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
    
    def _create_page_reference_from_page_data(self, page_data: Dict[str, Any], 
                                             session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create image reference from page data (get_page_analysis_details, return S3 URI)"""
        try:
            # Find page image URI - Use pure S3 URI instead of Pre-signed URL
            image_uri = page_data.get('image_uri') or page_data.get('image_presigned_url')
            if not image_uri:
                return None
            
            # Extract page information
            page_index = page_data.get('page_index', 0)
            page_number = page_index + 1
            
            # Extract document information
            document_id = page_data.get('document_id', '')
            project_id = page_data.get('project_id', '')
            
            # Extract file name from file_uri
            file_uri = page_data.get('file_uri', '')
            file_name = 'Unknown Document'
            if file_uri:
                # Extract file name from S3 URI
                if '/' in file_uri:
                    file_name = unquote(file_uri.split('/')[-1])
            
            reference = {
                'type': 'image',
                'title': f"Page {page_number}",
                'display_name': f"Page {page_number} of {file_name}",
                'file_name': file_name,
                'page_number': int(page_number),
                'value': image_uri,  # Return S3 URI
                'image_uri': image_uri,  # Pure S3 URI
                'page_id': page_data.get('page_id', f"page_{page_index}"),
                'document_id': document_id,
                'project_id': project_id,
                'created_at': page_data.get('created_at', ''),
                'metadata': {
                    'page_index': page_index,
                    'analysis_status': 'completed',
                    'session_id': session_id,
                    'vector_content_available': page_data.get('vector_content_available', False)
                }
            }
            
            # Add PDF link - Use S3 URI
            if file_uri:
                reference['file_uri'] = file_uri  # Pure S3 URI
                reference['linked_document'] = {
                    'document_id': document_id,
                    'file_name': file_name,
                    'file_uri': file_uri  # S3 URI
                }
            
            return reference
            
        except Exception as e:
            print(f"Error occurred during page reference creation: {str(e)}")
            return None

    def _create_pdf_reference_from_page_data(self, page_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create PDF reference from page data (return S3 URI, remove Pre-signed URL)"""
        try:
            # Use pure S3 URI instead of Pre-signed URL
            file_uri = page_data.get('file_uri')
            if not file_uri:
                return None
            
            # Extract file name
            file_name = 'Unknown Document'
            if file_uri:
                if '/' in file_uri:
                    file_name = unquote(file_uri.split('/')[-1])
            
            return {
                'type': 'document',
                'title': file_name,
                'display_name': file_name,
                'file_name': file_name,
                'value': file_uri,  # Return S3 URI
                'file_uri': file_uri,  # Pure S3 URI
                'document_id': page_data.get('document_id', ''),
                'project_id': page_data.get('project_id', ''),
                'created_at': page_data.get('created_at', ''),
                'metadata': {
                    'file_type': 'pdf',
                    'vector_content_available': page_data.get('vector_content_available', False)
                }
            }
            
        except Exception as e:
            print(f"Error occurred during PDF reference creation: {str(e)}")
            return None

    def _create_page_specific_reference(self, data: Dict[str, Any], 
                                       session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create reference from page-specific analysis result (legacy, return S3 URI)"""
        try:
            # Find page image URI - Use pure S3 URI instead of Pre-signed URL
            image_uri = data.get('image_uri') or data.get('image_presigned_url') or data.get('image_url')
            if not image_uri:
                return None
            
            # Extract page information
            page_index = data.get('page_index', 0)
            page_number = data.get('page_number', page_index + 1)
            
            # Extract document information
            document_id = data.get('document_id', '')
            project_id = data.get('project_id', '')
            file_name = data.get('file_name', 'Unknown Document')
            
            reference = {
                'type': 'image',
                'title': f"Page {page_number}",
                'display_name': f"Page {page_number} of {file_name}",
                'file_name': file_name,
                'page_number': int(page_number) if str(page_number).isdigit() else page_number,
                'value': image_uri,  # Return S3 URI
                'image_uri': image_uri,  # Pure S3 URI
                'page_id': f"page_{page_index}",
                'document_id': document_id,
                'project_id': project_id,
                'created_at': data.get('created_at', ''),
                'metadata': {
                    'page_index': page_index,
                    'analysis_status': 'completed',
                    'session_id': session_id
                }
            }
            
            # Add PDF link (if exists) - Use S3 URI
            file_uri = data.get('file_uri') or data.get('file_presigned_url') or data.get('download_url')
            if file_uri:
                reference['file_uri'] = file_uri  # Pure S3 URI
                reference['linked_document'] = {
                    'document_id': document_id,
                    'file_name': file_name,
                    'file_uri': file_uri  # S3 URI
                }
            
            return reference
            
        except Exception as e:
            print(f"Error occurred during page-specific reference creation: {str(e)}")
            return None

    def _create_pdf_reference(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create PDF reference from document (return S3 URI, remove Pre-signed URL)"""
        try:
            # Use pure S3 URI instead of Pre-signed URL
            file_uri = document.get('file_uri') or document.get('download_url')
            if not file_uri:
                return None
            
            file_name = document.get('file_name', 'Unknown Document')
            
            return {
                'type': 'document',
                'title': file_name,
                'display_name': file_name,
                'file_name': file_name,
                'value': file_uri,  # Return S3 URI
                'file_uri': file_uri,  # Pure S3 URI
                'document_id': document.get('document_id', ''),
                'project_id': document.get('project_id', ''),
                'created_at': document.get('created_at', ''),
                'metadata': {
                    'file_type': document.get('file_type', 'pdf'),
                    'file_size': document.get('file_size', 0),
                    'total_pages': document.get('total_pages', 0)
                }
            }
            
        except Exception as e:
            print(f"Error occurred during PDF reference creation: {str(e)}")
            return None
    
    def _create_llm_guide(self, tool_name: str, api_response: Dict[str, Any]) -> Optional[str]:
        """Create appropriate LLM guide for each tool"""
        try:
            # Provide guide only for successful responses
            if not api_response.get('success', True):
                return "An error occurred. Please try another method."
            
            guide_templates = {
                'get_documents_list': (
                    "문서 조회가 완료되었습니다. 화면에서 문서 목록을 확인하세요. "
                    "특정 문서나 상세한 분석이 필요하면 이야기해 주세요."
                ),
                'get_document_info': (
                    "I checked the document basic information. If you want to analyze the document in detail, "
                    "use the 'get_document_analysis' tool."
                ),
                'get_document_analysis': (
                    "The document analysis is complete. If you need detailed analysis of a specific page, "
                    "use the 'get_page_analysis_details' tool, or "
                    "use the 'hybrid_search' tool to search for other content."
                ),
                'get_page_analysis_details': (
                    "I checked the page detailed analysis. If you want to find related content, "
                    "use the 'hybrid_search' tool to search for keywords."
                ),
                'hybrid_search': (
                    "I checked the search results. If you want to see the entire content of a specific document, "
                    "use the 'get_document_analysis' tool, or "
                    "use the 'hybrid_search' tool to search for additional keywords."
                ),
                'get_project_info': (
                    "I checked the project information. If you want to see the documents in the project, "
                    "use the 'get_documents_list' tool, or "
                    "use the 'hybrid_search' tool to search for specific documents."
                ),
                'add_user_content_to_page': (
                    "The user content addition request has been received. It is being processed in the background. "
                    "Please check again later. When the processing is complete, it will be reflected in the search results of the corresponding document."
                )
            }
            
            return guide_templates.get(tool_name, 
                "The task has been completed. If you need additional information, please use another tool.")
            
        except Exception as e:
            print(f"Error occurred during LLM guide creation: {str(e)}")
            return "The tool execution has been completed."


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
        result = format_api_response(api_response, 'get_document_analysis')
    """
    formatter = get_formatter()
    return formatter.format(api_response, tool_name, session_id, **kwargs)

