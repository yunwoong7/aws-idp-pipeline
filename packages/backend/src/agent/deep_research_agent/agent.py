"""
Deep Research Agent - Main orchestration class
"""
import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from pathlib import Path
import sys
import os

# Add current package to path for absolute imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# from strands.hooks import HookProvider, HookRegistry  # Disabled for now

from agents.lead_researcher import LeadResearcher
from agents.page_worker import PageWorkerPool
from state.research_state import EvidenceStore, ResearchMemory
from tools.document_tool import get_document_overview_async

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """
    Main Deep Research Agent that orchestrates multi-agent research
    Inspired by Anthropic's architecture with Lead + Subagents
    """
    
    def __init__(
        self,
        num_workers: int = 3,       # Minimal workers 
        max_concurrent: int = 1,    # Sequential processing only
        evidence_path: str = "./research_data",
        enable_monitoring: bool = True
    ):
        """
        Initialize Deep Research Agent
        
        Args:
            num_workers: Number of PageWorker agents
            max_concurrent: Maximum concurrent page analysis
            evidence_path: Path for evidence storage
            enable_monitoring: Enable hooks for monitoring
        """
        self.num_workers = num_workers
        self.max_concurrent = max_concurrent
        
        # Initialize evidence store
        self.evidence_store = EvidenceStore(evidence_path)
        
        # Setup monitoring hooks if enabled
        self.hooks = self._setup_hooks() if enable_monitoring else None
        
        # Initialize worker pool
        self.worker_pool = PageWorkerPool(
            num_workers=num_workers,
            evidence_store=self.evidence_store,
            hooks=self.hooks
        )
        
        logger.info(f"DeepResearchAgent initialized with {num_workers} workers")
    
    def _setup_hooks(self):
        """Setup monitoring hooks for observability - Mock implementation"""
        logger.info("Hooks disabled (strands library not available)")
        return None
    
    async def research(
        self,
        document_id: str,
        query: str,
        index_id: Optional[str] = None,
        batch_size: int = 50,        # 50개 배치로 복원
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute deep research on a document
        
        Args:
            document_id: Document to research
            query: Research query
            index_id: Optional index ID for access
            batch_size: Pages per batch
            job_id: Optional job ID (auto-generated if not provided)
        
        Returns:
            Research results with job metadata
        """
        # Generate job ID if not provided
        if not job_id:
            job_id = f"research_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Starting research job {job_id}")
        logger.info(f"Document: {document_id}, Query: {query}")
        
        try:
            # Get document status from new status endpoint
            doc_overview = await get_document_overview_async(document_id, index_id)
            if not doc_overview.get("success"):
                raise ValueError(f"Failed to get document info: {doc_overview.get('error')}")
            
            total_pages = doc_overview.get("total_pages", 0)
            segment_ids = doc_overview.get("segment_ids", [])
            total_segments = len(segment_ids)
            
            if total_segments == 0:
                logger.warning("Document has no segments - proceeding anyway")
            
            logger.info(f"Document has {total_pages} pages and {total_segments} segments")
            logger.info(f"Segment IDs: {segment_ids}")
            
            # Create job in evidence store
            job = self.evidence_store.create_job(
                job_id=job_id,
                document_id=document_id,
                query=query,
                total_pages=total_pages
            )
            
            # Initialize memory and lead researcher
            memory = ResearchMemory()
            memory.progress["total_pages"] = total_pages
            
            lead = LeadResearcher(
                memory=memory,
                evidence_store=self.evidence_store,
                hooks=self.hooks
            )
            
            # Update job status to running
            self.evidence_store.update_job_status(job_id, "running")
            
            # Phase 1: Planning
            logger.info("Phase 1: Creating research plan")
            plan = lead.create_research_plan(query, total_segments)
            
            # Phase 2: Batch processing
            logger.info("Phase 2: Processing segments in batches")
            all_summaries = []
            
            for batch_start in range(0, total_segments, batch_size):
                batch_end = min(batch_start + batch_size, total_segments)
                batch_segment_ids = segment_ids[batch_start:batch_end]
                
                logger.info(f"Processing batch: segments {batch_start}-{batch_end-1}")
                logger.info(f"Segment IDs in batch: {batch_segment_ids}")
                memory.progress["current_batch"] = batch_segment_ids
                
                # Process batch with worker pool
                results = await self.worker_pool.process_segments_parallel(
                    job_id=job_id,
                    document_id=document_id,
                    segment_ids=batch_segment_ids,
                    query=query,
                    index_id=index_id,
                    max_concurrent=self.max_concurrent
                )
                
                # Extract summaries from results and update memory
                batch_summaries = []
                completed_count = 0
                for result in results:
                    if result.get("success"):
                        batch_summaries.append(result.get("summary", ""))
                        # Update memory with completed segment
                        memory.progress["completed_pages"] = memory.progress.get("completed_pages", 0) + 1
                        completed_count += 1
                    else:
                        # Handle failure
                        segment_id = result.get("segment_id")
                        error = result.get("error", "Unknown error")
                        lead.handle_failure(segment_id, error)
                        memory.progress.setdefault("failed_pages", []).append(segment_id)
                
                all_summaries.extend(batch_summaries)
                
                # Process batch results with Lead for better synthesis
                if batch_summaries:
                    assessment = lead.process_batch_results(batch_segment_ids, batch_summaries)
                    logger.debug(f"Lead assessment: {assessment[:100]}..." if assessment else "No assessment")
                
                logger.info(f"Batch {batch_start}-{batch_end-1} completed: {completed_count} successful, {len(results)-completed_count} failed")
                
                # Update job progress
                progress_pct = (batch_end / total_segments) * 100  # Changed from total_pages
                self.evidence_store.update_job_status(
                    job_id,
                    "running",
                    progress={
                        "completed_segments": batch_end,  # Changed from completed_pages
                        "total_segments": total_segments,  # Changed from total_pages
                        "total_pages": total_pages,  # Keep for backward compatibility
                        "percentage": progress_pct
                    }
                )
                
                # Check if should continue (budget/token limits)
                cost_summary = memory.get_cost_summary()
                if not lead.should_continue(cost_summary):
                    logger.warning("Stopping due to budget/token limits")
                    break
            
            # Phase 3: Final synthesis
            logger.info("Phase 3: Generating final report")
            final_summary = lead.generate_final_summary(
                evidence_store=self.evidence_store,
                job_id=job_id
            )
            
            # Generate report
            report = self._generate_report(
                job_id=job_id,
                document_id=document_id,
                query=query,
                plan=plan,
                final_summary=final_summary,
                total_pages=total_pages,
                completed_pages=memory.progress["completed_pages"],
                failed_pages=len(memory.progress["failed_pages"])
            )
            
            # Save report
            report_path = self.evidence_store.save_final_report(
                job_id, report, format="json"
            )
            
            # Also save markdown version
            markdown_report = self._generate_markdown_report(report)
            markdown_path = self.evidence_store.save_final_report(
                job_id, {"markdown": markdown_report}, format="markdown"
            )
            
            # Update job status to completed
            self.evidence_store.update_job_status(
                job_id,
                "completed",
                report_path=report_path,
                markdown_path=markdown_path,
                completed_at=datetime.now().isoformat()
            )
            
            logger.info(f"Research job {job_id} completed successfully")
            logger.info(f"Report saved to: {report_path}")
            
            return {
                "success": True,
                "job_id": job_id,
                "status": "completed",
                "report_path": report_path,
                "markdown_path": markdown_path,
                "summary": final_summary,
                "stats": {
                    "total_pages": total_pages,
                    "completed_pages": memory.progress["completed_pages"],
                    "failed_pages": len(memory.progress["failed_pages"]),
                    "cost": memory.get_cost_summary()
                }
            }
            
        except Exception as e:
            logger.error(f"Research job {job_id} failed: {e}")
            
            # Update job status to failed
            self.evidence_store.update_job_status(
                job_id,
                "failed",
                error=str(e),
                failed_at=datetime.now().isoformat()
            )
            
            return {
                "success": False,
                "job_id": job_id,
                "status": "failed",
                "error": str(e)
            }
    
    def _generate_report(
        self,
        job_id: str,
        document_id: str,
        query: str,
        plan: str,
        final_summary: str,
        total_pages: int,
        completed_pages: int,
        failed_pages: int
    ) -> Dict[str, Any]:
        """Generate structured research report"""
        
        # Collect all evidence
        all_evidence = self.evidence_store.get_all_evidence(job_id)
        
        # Extract key findings
        key_findings = []
        for evidence in all_evidence[:10]:  # Top 10 pages
            if evidence.get("findings"):
                for finding in evidence["findings"][:2]:  # Top 2 findings per page
                    key_findings.append({
                        "page": evidence.get("page_index"),
                        "text": finding.get("text", ""),
                        "type": finding.get("type", "analysis")
                    })
        
        # Build section map
        section_map = {}
        for evidence in all_evidence:
            sections = evidence.get("sections", [])
            if sections:
                section_map[evidence.get("page_index")] = [
                    s.get("title", "") for s in sections[:3]
                ]
        
        report = {
            "job_id": job_id,
            "document_id": document_id,
            "query": query,
            "generated_at": datetime.now().isoformat(),
            "research_plan": plan,
            "executive_summary": final_summary,
            "statistics": {
                "total_pages": total_pages,
                "analyzed_pages": completed_pages,
                "failed_pages": failed_pages,
                "coverage_percentage": (completed_pages / total_pages * 100) if total_pages > 0 else 0
            },
            "key_findings": key_findings[:20],  # Limit to 20 findings
            "section_map": section_map,
            "evidence_count": len(all_evidence)
        }
        
        return report
    
    def _generate_markdown_report(self, report: Dict[str, Any]) -> str:
        """Generate markdown version of report"""
        md = f"""# 문서 연구 분석 보고서

**작업 ID:** {report['job_id']}  
**문서:** {report['document_id']}  
**생성일시:** {report['generated_at']}

## 연구 질의
{report['query']}

## 연구 계획
{report['research_plan']}

## 종합 분석 결과
{report['executive_summary']}

## 분석 통계
- 총 페이지 수: {report['statistics']['total_pages']}
- 분석 완료 페이지: {report['statistics']['analyzed_pages']}
- 실패한 페이지: {report['statistics']['failed_pages']}
- 분석 커버리지: {report['statistics']['coverage_percentage']:.1f}%

## 주요 발견사항

"""
        
        for finding in report.get('key_findings', [])[:10]:
            md += f"- **세그먼트 {finding['page']}:** {finding['text']}\n"
        
        md += "\n## 문서 구조 분석\n\n"
        
        section_map = report.get('section_map', {})
        for page, sections in list(section_map.items())[:10]:
            if sections:
                md += f"**세그먼트 {page}:**\n"
                for section in sections:
                    md += f"  - {section}\n"
        
        md += f"\n---\n*수집된 총 증거 항목 수: {report.get('evidence_count', 0)}개*\n"
        
        return md
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of a research job"""
        job = self.evidence_store.get_job(job_id)
        
        if not job:
            return {
                "success": False,
                "error": f"Job {job_id} not found"
            }
        
        return {
            "success": True,
            "job": job
        }