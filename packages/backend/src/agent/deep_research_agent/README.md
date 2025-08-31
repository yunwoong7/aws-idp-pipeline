# Deep Research Agent

Multi-agent research system inspired by Anthropic's architecture for deep document analysis.

## Architecture

The system implements a **Lead Researcher + PageWorkers** pattern to efficiently analyze documents while managing token limits:

- **Lead Researcher**: Orchestrates research, maintains minimal context
- **PageWorkers**: Analyze individual pages in parallel
- **Evidence Store**: Persists detailed findings outside model context
- **Token Management**: Keeps only essential headers in memory

## Key Features

- ✅ **Token-efficient**: Evidence stored externally, not in context
- ✅ **Parallel processing**: Multiple workers analyze pages concurrently  
- ✅ **Progress tracking**: Real-time status updates
- ✅ **Cost monitoring**: Token and API call tracking
- ✅ **Fault tolerance**: Handles page failures gracefully
- ✅ **Structured reports**: JSON and Markdown output formats

## Installation

```bash
# Install required packages
pip install strands-agents asyncio

# Optional: for real web search integration
pip install httpx
```

## Usage

### Command Line Interface

```bash
# Navigate to the agent directory
cd packages/backend/src/agent/deep_research_agent

# Run a research job
python cli.py research <document_id> "Your research query" \
  --workers 4 \
  --batch-size 8 \
  --output results.json

# Check job status
python cli.py status <job_id>

# List all jobs
python cli.py list
```

### Python API

```python
from agent.deep_research_agent import DeepResearchAgent

# Initialize agent
agent = DeepResearchAgent(
    num_workers=4,
    max_concurrent=3,
    evidence_path="./research_data"
)

# Run research
result = await agent.research(
    document_id="doc123",
    query="Analyze technical specifications and compliance requirements",
    batch_size=8
)

# Check results
if result["success"]:
    print(f"Report saved to: {result['report_path']}")
    print(f"Summary: {result['summary']}")
```

## Configuration

### Environment Variables

```bash
# API Configuration (optional)
export API_BASE_URL="http://localhost:8000"

# AWS Configuration (if using real document storage)
export AWS_REGION="us-west-2"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

### Agent Parameters

- `num_workers`: Number of PageWorker agents (default: 4)
- `max_concurrent`: Maximum concurrent page analysis (default: 3)
- `batch_size`: Pages processed per batch (default: 8)
- `evidence_path`: Local storage path (default: "./research_data")

## Output Structure

### Evidence Store Layout

```
research_data/
├── jobs/
│   └── research_xxxxx.json      # Job metadata
├── evidence/
│   └── research_xxxxx/
│       ├── page_0000.json       # Page evidence
│       ├── page_0001.json
│       └── ...
└── reports/
    └── research_xxxxx/
        ├── final.json            # Structured report
        └── final.md              # Markdown report
```

### Report Format

```json
{
  "job_id": "research_12345",
  "document_id": "doc123",
  "query": "Research query",
  "executive_summary": "High-level findings...",
  "statistics": {
    "total_pages": 100,
    "analyzed_pages": 95,
    "failed_pages": 5,
    "coverage_percentage": 95.0
  },
  "key_findings": [...],
  "section_map": {...}
}
```

## Token Management Strategy

The system implements several strategies to avoid token limits:

1. **Evidence Separation**: Detailed findings stored in files, not context
2. **Header Summaries**: Only progress headers maintained in memory
3. **Batch Processing**: Pages processed in manageable chunks
4. **Context Reset**: Conversation reset between batches
5. **Cost Guards**: Automatic stopping on budget limits

## Extending the System

### Adding New Tools

Create new tools in `tools/` directory:

```python
from strands import tool

@tool
async def custom_analysis(data: str) -> Dict[str, Any]:
    """Your custom analysis tool"""
    # Implementation
    return {"result": "..."}
```

### Custom Evidence Processing

Override `_generate_report` in `DeepResearchAgent` to customize report generation.

### Integration with Production Storage

Replace `EvidenceStore` with DynamoDB/S3 implementation for production use.

## Troubleshooting

### Common Issues

1. **Token limit exceeded**: Reduce batch_size or max_concurrent
2. **API timeouts**: Increase timeout in tool implementations
3. **Memory issues**: Reduce num_workers for large documents
4. **Failed pages**: Check API access and document permissions

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Performance Considerations

- **Concurrency**: Balance between speed and API rate limits
- **Batch Size**: Larger batches = fewer Lead interventions
- **Worker Count**: More workers ≠ always faster (API limits)
- **Evidence Size**: Monitor disk usage for large research jobs

## License

MIT License - See LICENSE file for details