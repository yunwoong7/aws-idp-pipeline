<h2 align="center">
 AWS IDP AI Analysis - Infrastructure
</h2>
<div align="center">
  <img src="https://img.shields.io/badge/AWS-Cloud-FF9900?logo=amazon-aws&logoColor=white"/>
  <img src="https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white"/>
  <img src="https://img.shields.io/badge/Bedrock-Generative_AI-FF9900?logo=amazonaws&logoColor=white"/>
  <img src="https://img.shields.io/badge/S3-Storage-FF9900?logo=amazons3&logoColor=white"/>
  <img src="https://img.shields.io/badge/Lambda-Serverless-FF9900?logo=awslambda&logoColor=white"/>
  <img src="https://img.shields.io/badge/DynamoDB-NoSQL_DB-FF9900?logo=amazondynamodb&logoColor=white"/>
  <img src="https://img.shields.io/badge/OpenSearch-Vector_Search-005EB8?logo=opensearch&logoColor=white"/>
  <img src="https://img.shields.io/badge/Step_Functions-Workflow_Orchestration-FF9900?logo=awsstepfunctions&logoColor=white"/>
</div>


## Overview

**AWS IDP AI Analysis Infrastructure** is a comprehensive AWS cloud infrastructure built with CDK for the document processing and analysis system. It provides a scalable serverless architecture supporting the entire workflow from document upload to AI analysis using an Infrastructure as Code (IaC) approach for reliable and repeatable deployments.

## Architecture Overview

<div align="center">
  <img src="../../docs/assets/architecture.png" alt=" AWS IDP AI Analysis Architecture" width="900"/>
</div>

## Data Schema: OpenSearch

The core data, including analysis results and vector embeddings, is stored in OpenSearch. The index is structured to support hybrid search and detailed data retrieval for various media types.

```json
{
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
        "knn": true,
        "knn.algo_param.ef_search": 100
    },
    "mappings": {
        "properties": {
            "document_id": {"type": "keyword"},
            "segment_id": {"type": "keyword"},
            "segment_index": {"type": "integer"},
            "media_type": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "content_combined": {"type": "text"},
            "user_content": {
                "type": "nested",
                "properties": {
                    "content": {"type": "text"},
                    "created_at": {"type": "date"}
                }
            },
            "tools": {
                "type": "object",
                "properties": {
                    "bda_indexer": {"type": "nested"},
                    "pdf_text_extractor": {"type": "nested"},
                    "ai_analysis": {"type": "nested"}
                }
            },
            "vector_content": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib"
                }
            }
        }
    }
}
```

## Project Structure

```bash
infra/
├── config/
│   └── dev.toml                # Environment-specific configurations
├── src/
│   ├── main.ts                 # CDK app entry point, initializes all stacks
│   ├── stacks/                 # Core infrastructure stack definitions
│   ├── functions/              # Lambda function source code for each stack
│   ├── constructs/             # Reusable custom CDK constructs
│   └── lambda_layer/           # Shared Lambda Layer code and dependencies
├── deploy-infra.sh             # Script for core infrastructure deployment
└── deploy-services.sh          # Script for optional ECS services deployment
```

## Workflow Execution Flow

The document processing pipeline is orchestrated by AWS Step Functions. The following diagram illustrates the state transitions based on the logic in `workflow-stack.ts`.

```mermaid
stateDiagram-v2
    [*] --> StartBdaProcessing
    StartBdaProcessing --> CheckBdaStatus
    CheckBdaStatus --> BdaStatusChoice

    BdaStatusChoice --> WaitForBdaCompletion: status == Created / Processing
    WaitForBdaCompletion --> CheckBdaStatus

    BdaStatusChoice --> BdaProcessingFailed: status == ServiceError or Failed

    BdaStatusChoice --> DocumentIndexerTask: status == Success
    DocumentIndexerTask --> PdfTextExtractorTask
    PdfTextExtractorTask --> GetDocumentPagesTask
    GetDocumentPagesTask --> ReactAnalysisParallelMap

    state ReactAnalysisParallelMap {
        direction LR
        ReactAnalysisParallelMapStart: ReactAnalysisParallelMap
        ReactAnalysisParallelMapStart --> SinglePageReactAnalysis
        SinglePageReactAnalysis --> ReactAnalysisFinalizerTask
    }

    ReactAnalysisParallelMap --> DocumentSummarizerTask
    DocumentSummarizerTask --> ProcessingSucceeded


    %% End States
    ProcessingSucceeded --> [*]
    BdaProcessingFailed --> [*]

```

# Deployment

For detailed deployment instructions, please refer to the setup guides in the root `docs` folder:
- [**Devcontainer Setup Guide**](../../docs/devcontainer_setup.md) (Recommended)
- [**Manual Local Setup Guide**](../../docs/manual_setup.md)