#!/usr/bin/env python3
"""
CLI for testing Deep Research Agent
"""
import asyncio
import argparse
import logging
import json
from pathlib import Path
import sys
import os

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, parent_dir)

from agent.deep_research_agent.agent import DeepResearchAgent
from utils.model_config import print_model_configuration

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('deep_research.log')
    ]
)

logger = logging.getLogger(__name__)


async def run_research(args):
    """Run a research job"""
    # Print model configuration first
    print_model_configuration()
    
    logger.info("=" * 80)
    logger.info("DEEP RESEARCH AGENT - Starting Research")
    logger.info("=" * 80)
    logger.info(f"Document ID: {args.document_id}")
    logger.info(f"Query: {args.query}")
    logger.info(f"Workers: {args.workers}")
    logger.info(f"Batch Size: {args.batch_size}")
    logger.info(f"Max Concurrent: {args.max_concurrent}")
    logger.info(f"Index ID: {args.index_id}")
    logger.info("=" * 80)
    
    # Initialize agent
    agent = DeepResearchAgent(
        num_workers=args.workers,
        max_concurrent=args.max_concurrent,
        evidence_path=args.evidence_path,
        enable_monitoring=True
    )
    
    # Run research
    result = await agent.research(
        document_id=args.document_id,
        query=args.query,
        index_id=args.index_id,
        batch_size=args.batch_size,
        job_id=args.job_id
    )
    
    # Display results
    logger.info("=" * 80)
    logger.info("RESEARCH COMPLETED")
    logger.info("=" * 80)
    
    if result.get("success"):
        logger.info(f"✅ Job ID: {result['job_id']}")
        logger.info(f"📄 Report: {result.get('report_path')}")
        logger.info(f"📝 Markdown: {result.get('markdown_path')}")
        logger.info("\n📊 Statistics:")
        stats = result.get('stats', {})
        logger.info(f"  - Total Pages: {stats.get('total_pages')}")
        logger.info(f"  - Completed: {stats.get('completed_pages')}")
        logger.info(f"  - Failed: {stats.get('failed_pages')}")
        
        logger.info("\n💭 Summary:")
        logger.info(result.get('summary', 'No summary available'))
        
        # Save result summary
        if args.output:
            output_file = Path(args.output)
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            logger.info(f"\n💾 Result saved to: {output_file}")
    else:
        logger.error(f"❌ Research failed: {result.get('error')}")
    
    return result


async def check_status(args):
    """Check status of a research job"""
    logger.info(f"Checking status for job: {args.job_id}")
    
    agent = DeepResearchAgent(evidence_path=args.evidence_path)
    status = await agent.get_job_status(args.job_id)
    
    if status.get("success"):
        job = status['job']
        logger.info("=" * 60)
        logger.info(f"Job ID: {job['job_id']}")
        logger.info(f"Status: {job['status']}")
        logger.info(f"Document: {job['document_id']}")
        logger.info(f"Query: {job['query']}")
        
        progress = job.get('progress', {})
        logger.info(f"Progress: {progress.get('percentage', 0):.1f}% "
                   f"({progress.get('completed_pages')}/{progress.get('total_pages')} pages)")
        
        if job['status'] == 'completed':
            logger.info(f"Report: {job.get('report_path')}")
        elif job['status'] == 'failed':
            logger.info(f"Error: {job.get('error')}")
        
        logger.info("=" * 60)
    else:
        logger.error(f"Failed to get status: {status.get('error')}")
    
    return status


async def list_jobs(args):
    """List all research jobs"""
    evidence_path = Path(args.evidence_path)
    jobs_dir = evidence_path / "jobs"
    
    if not jobs_dir.exists():
        logger.info("No jobs found")
        return
    
    logger.info("=" * 80)
    logger.info("RESEARCH JOBS")
    logger.info("=" * 80)
    
    job_files = sorted(jobs_dir.glob("*.json"))
    
    for job_file in job_files:
        with open(job_file, 'r') as f:
            job = json.load(f)
        
        progress = job.get('progress', {})
        logger.info(f"\n📋 {job['job_id']}")
        logger.info(f"   Status: {job['status']}")
        logger.info(f"   Document: {job['document_id']}")
        logger.info(f"   Progress: {progress.get('percentage', 0):.1f}%")
        logger.info(f"   Created: {job.get('created_at', 'Unknown')}")
    
    logger.info("\n" + "=" * 80)
    logger.info(f"Total jobs: {len(job_files)}")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Deep Research Agent CLI - Multi-agent document research system"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Research command
    research_parser = subparsers.add_parser('research', help='Run a research job')
    research_parser.add_argument('document_id', help='Document ID to research')
    research_parser.add_argument('query', help='Research query')
    research_parser.add_argument('--index-id', required=True, help='Index ID for access control (required)')
    research_parser.add_argument('--job-id', help='Job ID (auto-generated if not provided)')
    research_parser.add_argument('--workers', type=int, default=6, help='Number of worker agents')          # Balanced: 6 workers
    research_parser.add_argument('--batch-size', type=int, default=25, help='Pages per batch')              # Balanced: 25 batch  
    research_parser.add_argument('--max-concurrent', type=int, default=4, help='Max concurrent workers')   # Balanced: 4 concurrent
    research_parser.add_argument('--evidence-path', default='./research_data', help='Evidence storage path')
    research_parser.add_argument('--output', '-o', help='Output file for results')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check job status')
    status_parser.add_argument('job_id', help='Job ID to check')
    status_parser.add_argument('--index-id', help='Index ID for access control')
    status_parser.add_argument('--evidence-path', default='./research_data', help='Evidence storage path')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all jobs')
    list_parser.add_argument('--evidence-path', default='./research_data', help='Evidence storage path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Run async command
    if args.command == 'research':
        result = asyncio.run(run_research(args))
        sys.exit(0 if result.get('success') else 1)
    elif args.command == 'status':
        result = asyncio.run(check_status(args))
        sys.exit(0 if result.get('success') else 1)
    elif args.command == 'list':
        asyncio.run(list_jobs(args))
        sys.exit(0)


if __name__ == '__main__':
    main()