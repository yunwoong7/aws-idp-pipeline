"""
PageWorker Agent - Analyzes individual document pages
"""
from typing import Dict, Any, Optional, List
try:
    from strands import Agent
    from strands.hooks import HookProvider, HookRegistry
except ImportError:
    import sys
    import os
    # Add parent directory to import mock_strands  
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    from mock_strands import Agent, HookProvider, HookRegistry
import logging
import asyncio
import sys
import os

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from tools.document_tool import get_segment_detail

# Add utils to path
sys.path.insert(0, os.path.join(parent_dir, 'utils'))
from utils.prompt_loader import prompt_loader
from utils.model_config import get_page_worker_model
from utils.rate_limiter import bedrock_rate_limiter

logger = logging.getLogger(__name__)


class PageWorker:
    """
    PageWorker that analyzes individual pages
    Returns only brief summaries to Lead, evidence saved via hooks
    """
    
    
    def __init__(self, worker_id: int, evidence_store, hooks: Optional[HookRegistry] = None):
        """
        Initialize PageWorker
        
        Args:
            worker_id: Unique worker identifier
            evidence_store: EvidenceStore instance for saving evidence
            hooks: Optional hooks for monitoring
        """
        self.worker_id = worker_id
        self.evidence_store = evidence_store
        
        # Add evidence-saving hook
        if hooks is None:
            hooks = HookRegistry()
        
        # Add custom hook to save evidence
        self._add_evidence_hook(hooks)
        
        # Load system prompt from YAML
        system_prompt = prompt_loader.get_system_prompt('page_worker')
        
        # Get Bedrock model configuration
        model = get_page_worker_model()
        
        # Create Strands agent with document tool
        # Convert hooks to iterable format if needed
        hooks_list = []
        if hooks is not None:
            if hasattr(hooks, 'providers'):
                hooks_list = hooks.providers
            elif hasattr(hooks, '__iter__'):
                hooks_list = list(hooks)
        
        self.agent = Agent(
            name=f"PageWorker_{worker_id}",
            system_prompt=system_prompt,
            model=model,
            tools=[get_segment_detail],  # Document analysis tool
            hooks=hooks_list,
            callback_handler=None  # Disable streaming
        )
        
        self.current_job_id = None
        logger.info(f"PageWorker {worker_id} initialized")
    
    def _add_evidence_hook(self, hooks):
        """Add hook to automatically save evidence"""
        if hooks is None:
            logger.info("No hooks registry provided, skipping evidence hook setup")
            return
        
        # Create a proper HookProvider class
        class EvidenceHookProvider:
            def __init__(self, worker):
                self.worker = worker
            
            def register_hooks(self, registry):
                """Register hooks with the registry"""
                logger.info(f"Evidence hook provider registered for worker {self.worker.worker_id}")
                # For now, we'll implement the evidence saving manually in analyze_segment
                # to avoid the complexity of hooking into tool events
        
        # Add the hook provider to registry if possible
        try:
            provider = EvidenceHookProvider(self)
            if hasattr(hooks, 'add_hook'):
                hooks.add_hook(provider)
                logger.debug(f"Evidence hook added for worker {self.worker_id}")
            else:
                logger.info("Hook registry does not support add_hook method")
        except Exception as e:
            logger.warning(f"Could not add evidence hook: {e}")
    
    async def analyze_segment(
        self,
        job_id: str,
        document_id: str,
        segment_index: str,  # This is actually segment_id now
        query: str,
        index_id: str
    ) -> Dict[str, Any]:
        """
        Analyze a specific segment
        
        Args:
            job_id: Research job ID
            document_id: Document ID
            segment_index: Segment index to analyze
            query: Research query for context
            index_id: Index ID for access control (required)
        
        Returns:
            Analysis result with brief summary
        """
        self.current_job_id = job_id
        
        try:
            prompt = prompt_loader.format_prompt(
                'page_worker',
                'segment_analysis_prompt',
                document_id=document_id,
                segment_id=segment_index,
                query=query,
                index_id=index_id
            )
            
            # Wait for rate limiter before calling Bedrock
            await bedrock_rate_limiter.acquire()
            
            # Execute analysis
            response = self.agent(prompt)
            
            # Extract actual analysis from agent response
            analysis_text = str(response)
            
            # Parse the analysis to extract key information
            # For now, use the full response as summary but we should extract structured data
            summary = analysis_text
            
            # Try to extract tool call results if available
            tool_results = None
            if hasattr(response, 'tool_calls') and response.tool_calls:
                tool_results = response.tool_calls
            elif hasattr(response, 'content') and 'get_segment_detail' in str(response.content):
                # The agent likely called the tool - extract results from content
                tool_results = analysis_text
            
            # Create evidence record
            evidence = {
                "job_id": job_id,
                "document_id": document_id,
                "segment_id": segment_index,
                "query": query,
                "worker_id": self.worker_id,
                "analysis": analysis_text,
                "summary": summary[:500] if summary else "",  # Increase summary length
                "tool_results": tool_results,
                "timestamp": asyncio.get_event_loop().time(),
                "relevance": "high" if len(analysis_text) > 100 else "low"
            }
            
            # Save evidence to store
            try:
                self.evidence_store.save_page_evidence(job_id, segment_index, evidence)
                logger.debug(f"Saved evidence for segment {segment_index}")
            except Exception as e:
                logger.warning(f"Failed to save evidence for segment {segment_index}: {e}")
            
            return {
                "success": True,
                "worker_id": self.worker_id,
                "segment_id": segment_index,
                "summary": summary[:300] if summary else "No analysis generated",
                "relevance": evidence["relevance"],
                "analysis_length": len(analysis_text)
            }
            
        except Exception as e:
            logger.error(f"Worker {self.worker_id} failed on segment {segment_index}: {e}")
            return {
                "success": False,
                "worker_id": self.worker_id,
                "segment_id": segment_index,  # segment_index variable contains segment_id value
                "error": str(e)
            }
        finally:
            self.current_job_id = None
    
    async def analyze_batch(
        self,
        job_id: str,
        document_id: str,
        page_indices: List[int],
        query: str,
        index_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple pages in sequence
        
        Args:
            job_id: Research job ID
            document_id: Document ID
            page_indices: List of page indices to analyze
            query: Research query
            index_id: Optional index ID
        
        Returns:
            List of analysis results
        """
        results = []
        
        for page_index in page_indices:
            result = await self.analyze_segment(
                job_id=job_id,
                document_id=document_id,
                segment_index=page_index,  # For now, treating page_index as segment_index
                query=query,
                index_id=index_id
            )
            results.append(result)
            
            # Minimal delay for API rate limiting  
            await asyncio.sleep(0.01)  # 0.1초 → 0.01초로 극단축
        
        return results


class PageWorkerPool:
    """
    Manages a pool of PageWorker agents for parallel processing
    """
    
    def __init__(self, num_workers: int, evidence_store, hooks: Optional[HookRegistry] = None):
        """
        Initialize worker pool
        
        Args:
            num_workers: Number of workers in the pool
            evidence_store: Shared evidence store
            hooks: Optional shared hooks
        """
        self.workers = [
            PageWorker(i, evidence_store, hooks)
            for i in range(num_workers)
        ]
        self.num_workers = num_workers
        logger.info(f"PageWorkerPool initialized with {num_workers} workers")
    
    async def process_pages_parallel(
        self,
        job_id: str,
        document_id: str,
        page_indices: List[int],
        query: str,
        index_id: Optional[str] = None,
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Process pages in parallel with concurrency limit
        
        Args:
            job_id: Research job ID
            document_id: Document ID
            page_indices: List of page indices
            query: Research query
            index_id: Optional index ID
            max_concurrent: Maximum concurrent workers
        
        Returns:
            List of all results
        """
        results = []
        
        # Process in chunks to limit concurrency
        for i in range(0, len(page_indices), max_concurrent):
            chunk = page_indices[i:i+max_concurrent]
            
            # Assign pages to workers
            tasks = []
            for j, page_index in enumerate(chunk):
                worker = self.workers[j % self.num_workers]
                task = worker.analyze_segment(
                    job_id=job_id,
                    document_id=document_id,
                    segment_index=page_index,  # For now, treating page_index as segment_index
                    query=query,
                    index_id=index_id
                )
                tasks.append(task)
            
            # Wait for chunk to complete
            chunk_results = await asyncio.gather(*tasks)
            results.extend(chunk_results)
            
            logger.info(f"Completed chunk: pages {chunk[0]}-{chunk[-1]}")
        
        return results
    
    async def process_segments_parallel(
        self,
        job_id: str,
        document_id: str,
        segment_ids: List[str],
        query: str,
        index_id: str,
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Process multiple segments in parallel using worker pool
        
        Args:
            job_id: Research job ID
            document_id: Document ID
            segment_ids: List of segment IDs to process
            query: Research query
            index_id: Index ID for access control (required)
            max_concurrent: Maximum concurrent workers
        
        Returns:
            List of analysis results
        """
        if not segment_ids:
            return []
        
        logger.info(f"Processing {len(segment_ids)} segments with {self.num_workers} workers")
        
        # Process segments with controlled concurrency to avoid rate limits
        logger.info(f"Processing {len(segment_ids)} segments with {self.num_workers} workers")
        
        all_results = []
        
        # Process sequentially to completely avoid throttling
        chunk_size = 1  # Sequential processing only
        
        for i in range(0, len(segment_ids), chunk_size):
            chunk = segment_ids[i:i + chunk_size]
            logger.info(f"Processing chunk: {len(chunk)} segments (indices {i}-{min(i+chunk_size-1, len(segment_ids)-1)})")
            
            tasks = []
            for j, segment_id in enumerate(chunk):
                worker = self.workers[j % self.num_workers]
                task = worker.analyze_segment(
                    job_id=job_id,
                    document_id=document_id,
                    segment_index=segment_id,
                    query=query,
                    index_id=index_id
                )
                tasks.append(task)
            
            # Execute chunk in parallel
            chunk_results = await asyncio.gather(*tasks)
            all_results.extend(chunk_results)
            
            logger.info(f"Completed chunk with {len(chunk_results)} results")
            
            # No wait needed since we process sequentially with rate limiter
        
        logger.info(f"✅ Processed {len(all_results)} segments total")
        return all_results