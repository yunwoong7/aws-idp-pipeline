"""
Lead Researcher Agent - Orchestrates the research process
"""
from typing import Dict, Any, List, Optional
import sys
import os
import logging

try:
    from strands import Agent
    from strands.hooks import HookProvider, HookRegistry
except ImportError:
    # Add parent directory to import mock_strands
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    from mock_strands import Agent, HookProvider, HookRegistry

# Add utils to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, os.path.join(parent_dir, 'utils'))
from utils.prompt_loader import prompt_loader
from utils.model_config import get_lead_researcher_model

logger = logging.getLogger(__name__)


class LeadResearcher:
    """
    Lead Researcher that plans and orchestrates research
    Maintains minimal context to avoid token explosion
    """
    
    
    def __init__(self, memory, evidence_store, hooks: Optional[HookRegistry] = None):
        """
        Initialize Lead Researcher
        
        Args:
            memory: ResearchMemory instance for state tracking
            evidence_store: EvidenceStore instance for persistence
            hooks: Optional hooks for monitoring
        """
        self.memory = memory
        self.evidence_store = evidence_store
        
        # Load system prompt from YAML
        system_prompt = prompt_loader.get_system_prompt('lead_researcher')
        
        # Get Bedrock model configuration
        model = get_lead_researcher_model()
        
        # Create Strands agent with minimal tools
        self.agent = Agent(
            name="LeadResearcher",
            system_prompt=system_prompt,
            model=model,
            tools=[],  # Lead doesn't directly call tools
            hooks=hooks,
            callback_handler=None  # Disable streaming output
        )
        
        logger.info("Lead Researcher initialized")
    
    def create_research_plan(self, query: str, total_pages: int) -> str:
        """
        Create initial research plan
        
        Args:
            query: User's research query
            total_pages: Total number of pages in document
        
        Returns:
            Research plan as string
        """
        prompt = prompt_loader.format_prompt(
            'lead_researcher', 
            'research_plan_prompt',
            query=query,
            total_pages=total_pages
        )
        
        response = self.agent(prompt)
        plan = str(response)
        
        # Store plan in memory
        self.memory.update_plan(plan)
        logger.info(f"Research plan created: {plan[:200]}...")
        
        return plan
    
    def process_batch_results(self, batch_segments: List[str], summaries: List[str]) -> str:
        """
        Process results from a batch of segments
        
        Args:
            batch_segments: List of segment IDs processed
            summaries: Brief summaries from each segment
        
        Returns:
            Lead's assessment of the batch
        """
        # Update memory with batch results
        for segment_id, summary in zip(batch_segments, summaries):
            self.memory.add_page_completion(segment_id, summary, [])
        
        # Get compact progress header
        progress_header = self.memory.get_progress_header()
        
        batch_summaries_text = chr(10).join(f"- 세그먼트 {p}: {s[:100]}" for p, s in zip(batch_segments, summaries))
        
        prompt = prompt_loader.format_prompt(
            'lead_researcher',
            'batch_assessment_prompt', 
            progress_header=progress_header,
            batch_start=batch_segments[0] if batch_segments else "N/A",
            batch_end=batch_segments[-1] if batch_segments else "N/A",
            batch_summaries=batch_summaries_text
        )
        
        response = self.agent(prompt)
        assessment = str(response)
        
        logger.info(f"Batch assessment: {assessment[:200]}...")
        return assessment
    
    def should_continue(self, cost_so_far: Dict[str, Any]) -> bool:
        """
        Decide whether to continue research based on progress and cost
        
        Args:
            cost_so_far: Current token/cost metrics
        
        Returns:
            True if should continue, False if should stop
        """
        progress = self.memory.progress
        completed = progress["completed_pages"]
        total = progress["total_pages"]
        
        # Check completion
        if completed >= total:
            logger.info("All pages processed")
            return False
        
        # Check cost budget (example thresholds)
        if cost_so_far.get("total_cost", 0) > 10.0:  # $10 limit
            logger.warning("Cost budget exceeded")
            return False
        
        if cost_so_far.get("input_tokens", 0) > 500000:  # 500k token limit
            logger.warning("Token budget exceeded")
            return False
        
        return True
    
    def generate_final_summary(self, evidence_store=None, job_id=None) -> str:
        """
        Generate final research summary using both memory and evidence store
        
        Args:
            evidence_store: Optional evidence store to get detailed analysis
            job_id: Optional job ID to retrieve evidence
            
        Returns:
            Final summary for the research job
        """
        progress_header = self.memory.get_progress_header()
        
        # Get additional context from evidence store if available
        evidence_context = ""
        if evidence_store and job_id:
            try:
                all_evidence = evidence_store.get_all_evidence(job_id)
                if all_evidence:
                    evidence_context = "\n=== 주요 분석 내용 ===\n"
                    for i, evidence in enumerate(all_evidence[:10]):  # Top 10 pieces of evidence
                        segment_id = evidence.get("segment_id", f"segment_{i}")
                        analysis = evidence.get("analysis", "")[:200]  # First 200 chars
                        if analysis:
                            evidence_context += f"세그먼트 {segment_id}: {analysis}...\n"
                    
                    evidence_context += f"\n총 {len(all_evidence)}개 세그먼트 분석 완료\n"
                else:
                    evidence_context = "\n⚠️ 저장된 분석 결과가 없습니다.\n"
            except Exception as e:
                logger.warning(f"Could not retrieve evidence for final summary: {e}")
                evidence_context = "\n⚠️ 분석 결과 조회 중 오류가 발생했습니다.\n"
        
        # Combine progress header with evidence context
        full_context = progress_header + evidence_context
        
        prompt = prompt_loader.format_prompt(
            'lead_researcher',
            'final_summary_prompt',
            progress_header=full_context
        )
        
        response = self.agent(prompt)
        summary = str(response)
        
        logger.info("Final summary generated with evidence context")
        return summary
    
    def handle_failure(self, page_index: int, error: str):
        """
        Handle page processing failure
        
        Args:
            page_index: Failed page index
            error: Error message
        """
        self.memory.add_page_failure(page_index, error)
        logger.error(f"Page {page_index} failed: {error}")
        
        # Decide if critical
        if len(self.memory.progress["failed_pages"]) > 5:
            logger.warning("Too many failures, may need to adjust strategy")