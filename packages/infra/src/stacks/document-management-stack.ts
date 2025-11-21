import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { getBedrockConfig, getSearchConfig } from '../../config/loader.js';
import { StandardLambda } from '../constructs/standard-lambda.js';
import { ApiGatewayRoutes } from '../constructs/api-gateway-routes.js';

export interface DocumentManagementStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly httpApi?: apigw.IHttpApi;
  readonly documentsBucket?: s3.IBucket;
  readonly documentsTable?: dynamodb.ITable;
  readonly segmentsTable?: dynamodb.ITable;
  readonly indicesTable?: dynamodb.ITable;
  readonly opensearchEndpoint?: string;
  readonly opensearchIndex?: string;
  readonly opensearchDomain?: any; // OpenSearch 도메인에 대한 권한 부여용
  readonly vpc?: ec2.IVpc; // VPC 추가
  readonly commonLayer?: lambda.ILayerVersion; // 공통 레이어 추가
  readonly lambdaConfig?: {
    timeout?: cdk.Duration;
    memorySize?: number;
    retryAttempts?: number;
  };
  // Cognito configuration for logout
  readonly cognitoUserPoolDomain?: string;
  readonly cognitoClientId?: string;
}

/**
 * AWS IDP AI Analysis - Document Management Stack
 *
 * Stack providing document management API and OpenSearch management API:
 *
 * Document management features:
 * - Drawing upload and document registration (Pre-signed URL generation)
 * - Upload completion processing and workflow initiation
 * - Document list retrieval and detail retrieval
 * - Document deletion
 * - Page detail retrieval (OpenSearch-based)
 * - S3 file storage and DynamoDB metadata management
 *
 * OpenSearch management features:
 * - Check OpenSearch cluster status
 * - Create, delete, and recreate index
 * - Retrieve OpenSearch documents by project/document
 * - Hybrid search (keyword + vector)
 * - Vector search, keyword search
 */
export class DocumentManagementStack extends cdk.Stack {
  public readonly documentManagementLambda: lambda.Function;
  public documentProcessingQueue!: sqs.Queue;
  public documentProcessingDlq!: sqs.Queue;

  constructor(
    scope: Construct,
    id: string,
    props: DocumentManagementStackProps,
  ) {
    super(scope, id, props);

    const stage = props.stage || 'prod';

    // Load settings
    const bedrockConfig = getBedrockConfig();
    const searchConfig = getSearchConfig();

    // Get required resources from props
    const httpApi = props.httpApi;
    const documentsBucket = props.documentsBucket;
    const documentsTable = props.documentsTable;
    const segmentsTable = props.segmentsTable;
    const indicesTable = props.indicesTable;

    if (
      !httpApi ||
      !documentsBucket ||
      !documentsTable ||
      !segmentsTable ||
      !indicesTable
    ) {
      throw new Error(
        'HttpApi, documentsBucket, and DynamoDB tables must be provided in props',
      );
    }

    // Create SQS queue (for document processing)
    this.createSqsQueues(stage);

    // Create Document Management Lambda function
    const documentManagementLambdaConstruct = new StandardLambda(this, 'DocumentManagement', {
      functionName: 'aws-idp-ai-document-management',
      codePath: 'api/document-management',
      description: 'AWS IDP AI Document Management API Lambda Function',
      environment: {
        DOCUMENTS_TABLE_NAME: props.documentsTable!.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable!.tableName,
        INDICES_TABLE_NAME: indicesTable!.tableName,
        DOCUMENTS_BUCKET_NAME: props.documentsBucket!.bucketName,
        DOCUMENT_PROCESSING_QUEUE_URL: this.documentProcessingQueue.queueUrl,
        OPENSEARCH_ENDPOINT: props.opensearchEndpoint || '',
        OPENSEARCH_INDEX_NAME: props.opensearchIndex || '',
        OPENSEARCH_REGION: cdk.Stack.of(this).region,
        SEARCH_THRESHOLD_SCORE: bedrockConfig.searchThresholdScore?.toString() || '0.4',
        HYBRID_SEARCH_SIZE: searchConfig.hybridSearchSize?.toString() || '25',
        RERANK_TOP_N: searchConfig.rerankTopN?.toString() || '3',
        MAX_SEARCH_SIZE: searchConfig.maxSearchSize?.toString() || '100',
        RERANK_SCORE_THRESHOLD: searchConfig.rerankScoreThreshold?.toString() || '0.07',
        RERANK_MODEL_ID: bedrockConfig.rerankModelId || 'cohere.rerank-v3-5:0',
        // Bedrock settings (for incremental content processing)
        BEDROCK_AGENT_MODEL_ID: bedrockConfig.analysisAgentModelId || 'us.anthropic.claude-3-7-sonnet-20250219-v1:0',
        BEDROCK_AGENT_MAX_TOKENS: bedrockConfig.analysisAgentMaxToken?.toString() || '8192',
        EMBEDDINGS_MODEL_ID: bedrockConfig.embeddingsModelId || 'amazon.titan-embed-text-v2:0',
        EMBEDDINGS_DIMENSIONS: bedrockConfig.embeddingsDimensions?.toString() || '1024',
        STAGE: props.stage || 'dev',
        AUTH_DISABLED: 'false',  // 배포 환경에서는 실제 Cognito 인증 사용
        // Cognito configuration for logout
        ...(props.cognitoUserPoolDomain && { COGNITO_USER_POOL_DOMAIN: props.cognitoUserPoolDomain }),
        ...(props.cognitoClientId && { COGNITO_CLIENT_ID: props.cognitoClientId }),
      },
      deadLetterQueueEnabled: false,
      vpc: props.vpc,
      commonLayer: props.commonLayer,
      timeout: cdk.Duration.seconds(900), // 15 minutes - for user content LLM processing
      memorySize: props.lambdaConfig?.memorySize || 1024,
      stage: stage, // Add stage parameter
    });

    this.documentManagementLambda = documentManagementLambdaConstruct.function;

    // Grant permissions to Lambda
    this.grantPermissions(
      documentsTable,
      segmentsTable,
      documentsBucket,
      props.opensearchDomain,
      indicesTable,
    );

    // Add API Gateway routes
    this.addApiRoutes(httpApi);

    // CDK Nag suppression settings
    this.addNagSuppressions();

    // Grant read/write access to OpenSearch domain
    if (props.opensearchDomain) {
      props.opensearchDomain.grantReadWrite(this.documentManagementLambda);
    }

    // OpenSearch access is handled through VPC endpoints and security groups
    // No additional egress rules needed as allowAllOutbound is true by default
  }

  /**
   * Grant permissions
   */
  private grantPermissions(
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    documentsBucket: s3.IBucket,
    opensearchDomain?: any,
    indicesTable?: dynamodb.ITable,
  ): void {
    // Grant permissions to DynamoDB tables
    documentsTable.grantReadWriteData(this.documentManagementLambda);
    segmentsTable.grantReadWriteData(this.documentManagementLambda);
    if (indicesTable) {
      indicesTable.grantReadWriteData(this.documentManagementLambda);
    }

    // Grant permissions to S3 bucket
    documentsBucket.grantReadWrite(this.documentManagementLambda);

    // Grant permissions to SQS queues
    this.documentProcessingQueue.grantSendMessages(
      this.documentManagementLambda,
    );
    this.documentProcessingDlq.grantSendMessages(this.documentManagementLambda);

    // Grant permissions to OpenSearch domain (if present)
    if (opensearchDomain) {
      // Grant HTTP access permission to OpenSearch domain
      this.documentManagementLambda.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'es:ESHttpPost',
            'es:ESHttpPut',
            'es:ESHttpGet',
            'es:ESHttpDelete',
            'es:ESHttpHead',
          ],
          resources: [`${opensearchDomain.domainArn}/*`],
        }),
      );
    }

    // Grant Bedrock permissions (for hybrid search embedding and reranking)
    this.documentManagementLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ],
        resources: [
          // Titan Embed model (for embedding generation)
          'arn:aws:bedrock:*::foundation-model/amazon.titan-embed-*',
          // Cohere embedding and reranking models
          'arn:aws:bedrock:*::foundation-model/cohere.embed-*',
          'arn:aws:bedrock:*::foundation-model/cohere.rerank-*',
          // Claude models (for incremental user content processing)
          'arn:aws:bedrock:*::foundation-model/anthropic.claude-*',
          // Inference Profiles (Cross-region)
          `arn:aws:bedrock:*:${this.account}:inference-profile/*`,
          // Application Inference Profiles
          `arn:aws:bedrock:*:${this.account}:application-inference-profile/*`,
        ],
      }),
    );

  }

  /**
   * Add API Gateway routes
   */
  private addApiRoutes(httpApi: apigw.IHttpApi): void {
    // Define Document Management API Routes
    const documentRoutes = [
      // POST /api/documents/upload - Direct file upload (small files)
      {
        path: '/api/documents/upload',
        methods: [apigw.HttpMethod.POST],
      },
      // POST /api/documents/upload-large - Generate Pre-signed URL for large file upload
      {
        path: '/api/documents/upload-large',
        methods: [apigw.HttpMethod.POST],
      },
      // POST /api/documents/{document_id}/upload-complete - Complete large file upload
      {
        path: '/api/documents/{document_id}/upload-complete',
        methods: [apigw.HttpMethod.POST],
      },
      // POST /api/documents/upload/complete - Upload completion processing (legacy compatibility)
      {
        path: '/api/documents/upload/complete',
        methods: [apigw.HttpMethod.POST],
      },
      // GET /api/documents/{document_id}/status - Retrieve document status
      {
        path: '/api/documents/{document_id}/status',
        methods: [apigw.HttpMethod.GET],
      },
      // GET /api/documents - Retrieve document list
      {
        path: '/api/documents',
        methods: [apigw.HttpMethod.GET],
      },
      // GET /api/documents/{document_id} - Retrieve specific document details
      {
        path: '/api/documents/{document_id}',
        methods: [apigw.HttpMethod.GET],
      },
      // DELETE /api/documents/{document_id} - Delete document
      {
        path: '/api/documents/{document_id}',
        methods: [apigw.HttpMethod.DELETE],
      },
      // GET /api/documents/{document_id}/segments/{segment_id} - Retrieve specific segment details (OpenSearch-based)
      {
        path: '/api/documents/{document_id}/segments/{segment_id}',
        methods: [apigw.HttpMethod.GET],
      },
      // POST /api/documents/presigned-url - Generate pre-signed URL for S3 URI
      {
        path: '/api/documents/presigned-url',
        methods: [apigw.HttpMethod.POST],
      },
      
      // OpenSearch management API routes
      // GET /api/opensearch/status - Check OpenSearch cluster status (supports ?index_id=xxx parameter)
      {
        path: '/api/opensearch/status',
        methods: [apigw.HttpMethod.GET],
      },
      // POST /api/opensearch/indices/{index_name}/create - Create index
      {
        path: '/api/opensearch/indices/{index_name}/create',
        methods: [apigw.HttpMethod.POST],
      },
      // DELETE /api/opensearch/indices/{index_name} - Delete index
      {
        path: '/api/opensearch/indices/{index_name}',
        methods: [apigw.HttpMethod.DELETE],
      },
      // POST /api/opensearch/indices/recreate - Recreate index
      {
        path: '/api/opensearch/indices/recreate',
        methods: [apigw.HttpMethod.POST],
      },
      // GET /api/opensearch/documents/{document_id} - Retrieve specific document
      {
        path: '/api/opensearch/documents/{document_id}',
        methods: [apigw.HttpMethod.GET],
      },
      // GET /api/opensearch/projects/{project_id}/documents/{document_id}/segments/{segment_index} - Retrieve specific document+segment
      {
        path: '/api/opensearch/projects/{project_id}/documents/{document_id}/segments/{segment_index}',
        methods: [apigw.HttpMethod.GET],
      },
      // POST /api/opensearch/search/hybrid - Hybrid search
      {
        path: '/api/opensearch/search/hybrid',
        methods: [apigw.HttpMethod.POST],
      },
      // POST /api/opensearch/search/vector - Vector search
      {
        path: '/api/opensearch/search/vector',
        methods: [apigw.HttpMethod.POST],
      },
      // POST /api/opensearch/search/keyword - Keyword search
      {
        path: '/api/opensearch/search/keyword',
        methods: [apigw.HttpMethod.POST],
      },
      // GET /api/opensearch/data/sample - Retrieve sample data for testing (5 items)
      {
        path: '/api/opensearch/data/sample',
        methods: [apigw.HttpMethod.GET],
      },
      // POST /api/opensearch/user-content/add - Add user content
      {
        path: '/api/opensearch/user-content/add',
        methods: [apigw.HttpMethod.POST],
      },
      // POST /api/opensearch/user-content/remove - Remove user content
      {
        path: '/api/opensearch/user-content/remove',
        methods: [apigw.HttpMethod.POST],
      },
      // POST /api/get-presigned-url - Generate Pre-signed URL (project-independent)
      {
        path: '/api/get-presigned-url',
        methods: [apigw.HttpMethod.POST],
      },
      // GET /api/segments/{segment_id}/image - Retrieve segment image (base64)
      {
        path: '/api/segments/{segment_id}/image',
        methods: [apigw.HttpMethod.GET],
      },
    ];

    // Add routes using ApiGatewayRoutes construct
    new ApiGatewayRoutes(this, 'DocumentManagementRoutes', {
      httpApi,
      integrationLambda: this.documentManagementLambda,
      routePaths: documentRoutes,
      constructIdPrefix: 'DocumentRoute',
      authSuppressionReason: [
        'MVP development environment requires unauthenticated API access for rapid prototyping and testing.',
        'This is a development/testing environment where API endpoints need to be accessible without authentication.',
        'Production deployment will implement proper authentication using AWS Cognito User Pools or IAM authorization.',
        'Current API endpoints are used for internal development and integration testing only.',
      ].join(' '),
    });
  }

  /**
   * CDK Nag suppression settings
   */
  private addNagSuppressions(): void {
    // Suppressions for Lambda function service role
    NagSuppressions.addResourceSuppressions(
      this.documentManagementLambda,
      [
        {
          id: 'AwsSolutions-IAM4',
          reason: [
            'AWS Lambda Basic Execution Role and VPC Access Execution Role are required for Lambda function execution.',
            'These managed policies provide necessary CloudWatch logging and VPC networking permissions.',
            'Cannot be replaced with custom policies for basic Lambda execution requirements.',
          ].join(' '),
          appliesTo: [
            'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
            'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole',
          ],
        },
        {
          id: 'AwsSolutions-L1',
          reason: [
            'Lambda function uses Python 3.13 runtime.',
            'Maintaining Python 3.13 for stability and consistency across customer deployments.',
            'Will be updated to Python 3.14 after thorough testing and customer environment considerations.',
          ].join(' '),
        },
      ],
      true,
    );

    // Suppressions for Lambda execution role default policy
    if (this.documentManagementLambda.role) {
      NagSuppressions.addResourceSuppressions(
        this.documentManagementLambda.role,
        [
          {
            id: 'AwsSolutions-IAM5',
            reason: [
              'Wildcard permissions are required for dynamic resource access patterns.',
              'DynamoDB GSI access requires wildcard patterns as index names are dynamically generated.',
              'S3 object operations require wildcard access for document storage and retrieval.',
              'Bedrock model access requires wildcard patterns for different model versions.',
              'OpenSearch domain access requires wildcard for index operations.',
            ].join(' '),
          },
        ],
        true,
      );
    }

  }

  /**
   * Create SQS queue (for document processing)
   */
  private createSqsQueues(stage: string): void {
    // Create Dead Letter Queue
    this.documentProcessingDlq = new sqs.Queue(this, 'DocumentProcessingDlq', {
      queueName: `aws-idp-ai-document-processing-dlq-${stage}`,
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
    });

    // Create main processing queue
    this.documentProcessingQueue = new sqs.Queue(
      this,
      'DocumentProcessingQueue',
      {
        queueName: `aws-idp-ai-document-processing-${stage}`,
        visibilityTimeout: cdk.Duration.minutes(3), // Retry after 3 minutes if processing
        retentionPeriod: cdk.Duration.days(7),
        encryption: sqs.QueueEncryption.SQS_MANAGED,
        enforceSSL: true,
        deadLetterQueue: {
          queue: this.documentProcessingDlq,
          maxReceiveCount: 3, // Move to DLQ after 3 retries
        },
      },
    );
  }
}
