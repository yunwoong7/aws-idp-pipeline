"""
Research State Management - Evidence Store and Job State
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import hashlib


class EvidenceStore:
    """
    Local file-based evidence store for development
    In production, use DynamoDB + S3
    """
    
    def __init__(self, base_path: str = "./research_data"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.jobs_dir = self.base_path / "jobs"
        self.evidence_dir = self.base_path / "evidence"
        self.reports_dir = self.base_path / "reports"
        
        for dir_path in [self.jobs_dir, self.evidence_dir, self.reports_dir]:
            dir_path.mkdir(exist_ok=True)
    
    def create_job(self, job_id: str, document_id: str, query: str, total_pages: int) -> Dict[str, Any]:
        """Create a new research job"""
        job = {
            "job_id": job_id,
            "document_id": document_id,
            "query": query,
            "total_pages": total_pages,
            "status": "queued",
            "progress": {
                "completed_pages": 0,
                "total_pages": total_pages,
                "percentage": 0
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "cost": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_cost": 0.0
            }
        }
        
        job_file = self.jobs_dir / f"{job_id}.json"
        with open(job_file, 'w') as f:
            json.dump(job, f, indent=2)
        
        # Create evidence directory for this job
        (self.evidence_dir / job_id).mkdir(exist_ok=True)
        
        return job
    
    def update_job_status(self, job_id: str, status: str, **kwargs) -> Dict[str, Any]:
        """Update job status and metadata"""
        job_file = self.jobs_dir / f"{job_id}.json"
        
        # Check if job file exists
        if not job_file.exists():
            print(f"Warning: Job file {job_file} not found. Cannot update status.")
            return {"success": False, "error": "Job file not found"}
        
        with open(job_file, 'r') as f:
            job = json.load(f)
        
        job["status"] = status
        job["updated_at"] = datetime.now().isoformat()
        
        for key, value in kwargs.items():
            if key == "progress":
                job["progress"].update(value)
            elif key == "cost":
                job["cost"]["input_tokens"] += value.get("input_tokens", 0)
                job["cost"]["output_tokens"] += value.get("output_tokens", 0)
                job["cost"]["total_cost"] += value.get("total_cost", 0.0)
            else:
                job[key] = value
        
        with open(job_file, 'w') as f:
            json.dump(job, f, indent=2)
        
        return job
    
    def save_page_evidence(self, job_id: str, page_index, evidence: Dict[str, Any]) -> str:
        """Save evidence for a specific page or segment"""
        # Handle both integer page_index and string segment_id
        if isinstance(page_index, str):
            evidence_file = self.evidence_dir / job_id / f"segment_{page_index}.json"
        else:
            evidence_file = self.evidence_dir / job_id / f"page_{page_index:04d}.json"
        
        # Ensure directory exists
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Add metadata
        evidence["saved_at"] = datetime.now().isoformat()
        evidence["hash"] = hashlib.md5(
            json.dumps(evidence, sort_keys=True).encode()
        ).hexdigest()
        
        with open(evidence_file, 'w') as f:
            json.dump(evidence, f, indent=2)
        
        return str(evidence_file)
    
    def get_page_evidence(self, job_id: str, page_index: int) -> Optional[Dict[str, Any]]:
        """Retrieve evidence for a specific page"""
        evidence_file = self.evidence_dir / job_id / f"page_{page_index:04d}.json"
        
        if evidence_file.exists():
            with open(evidence_file, 'r') as f:
                return json.load(f)
        return None
    
    def get_all_evidence(self, job_id: str) -> List[Dict[str, Any]]:
        """Get all evidence for a job"""
        evidence_dir = self.evidence_dir / job_id
        evidence_list = []
        
        if evidence_dir.exists():
            for evidence_file in sorted(evidence_dir.glob("page_*.json")):
                with open(evidence_file, 'r') as f:
                    evidence_list.append(json.load(f))
        
        return evidence_list
    
    def save_final_report(self, job_id: str, report: Dict[str, Any], format: str = "json") -> str:
        """Save final research report"""
        report_dir = self.reports_dir / job_id
        report_dir.mkdir(exist_ok=True)
        
        if format == "json":
            report_file = report_dir / "final.json"
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
        elif format == "markdown":
            report_file = report_dir / "final.md"
            with open(report_file, 'w') as f:
                f.write(report.get("markdown", ""))
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        return str(report_file)
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job metadata"""
        job_file = self.jobs_dir / f"{job_id}.json"
        
        if job_file.exists():
            with open(job_file, 'r') as f:
                return json.load(f)
        return None


class ResearchMemory:
    """
    Lightweight memory for maintaining research context
    Keeps only essential headers to avoid token explosion
    """
    
    def __init__(self, max_highlights: int = 5):
        self.max_highlights = max_highlights
        self.reset()
    
    def reset(self):
        """Reset memory to initial state"""
        self.plan = None
        self.progress = {
            "total_pages": 0,
            "completed_pages": 0,
            "failed_pages": [],
            "current_batch": []
        }
        self.recent_highlights = []  # Keep only last N highlights
        self.section_map = {}  # Page -> section titles mapping
        self.cost_tracker = {
            "input_tokens": 0,
            "output_tokens": 0,
            "api_calls": 0
        }
    
    def update_plan(self, plan: str):
        """Update research plan"""
        self.plan = plan
    
    def add_page_completion(self, page_index: int, summary: str, sections: List[str]):
        """Record page completion with minimal context"""
        self.progress["completed_pages"] += 1
        
        # Update section map
        self.section_map[page_index] = sections
        
        # Keep only recent highlights
        self.recent_highlights.append({
            "page": page_index,
            "summary": summary[:200]  # Max 200 chars
        })
        
        if len(self.recent_highlights) > self.max_highlights:
            self.recent_highlights.pop(0)
    
    def add_page_failure(self, page_index: int, error: str):
        """Record page processing failure"""
        self.progress["failed_pages"].append({
            "page": page_index,
            "error": error[:100]  # Keep error message short
        })
    
    def get_progress_header(self) -> str:
        """Generate compact progress header for context"""
        completed = self.progress["completed_pages"]
        total = self.progress["total_pages"]
        percentage = (completed / total * 100) if total > 0 else 0
        
        header = f"""
=== Research Progress ===
Status: {percentage:.1f}% ({completed}/{total} pages)
Current batch: {self.progress.get('current_batch', [])}
Failed pages: {len(self.progress['failed_pages'])}
"""
        
        if self.recent_highlights:
            header += "\n=== Recent Highlights ===\n"
            for h in self.recent_highlights[-3:]:  # Show only last 3
                header += f"- Page {h['page']}: {h['summary']}\n"
        
        return header
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary"""
        return self.cost_tracker.copy()