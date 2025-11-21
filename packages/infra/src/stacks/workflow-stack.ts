import * as cdk from 'aws-cdk-lib';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as sfnTasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as eventsources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as oss from 'aws-cdk-lib/aws-opensearchservice';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';
import { StandardLambda } from '../constructs/standard-lambda.js';
import { getStepFunctionsConfig, getSqsConfig } from '../../config/loader.js';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export interface WorkflowStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly bedrock?: {
    analysisAgentModelId?: string;
    analysisAgentMaxToken?: number;
    analysisImageModelId?: string;
    analysisImageMaxToken?: number;
    analysisSummarizerModelId?: string;
    analysisSummarizerMaxToken?: number;
    pageSummaryModelId?: string;
    pageSummaryMaxToken?: number;
  };
  readonly analysis?: {
    previousAnalysisMaxCharacters?: number;
    maxIterations?: number;
  };
  readonly stepfunctions?: {
    documentProcessingTimeout?: number;
  };
  readonly documentProcessingQueue?: sqs.Queue;
  readonly databaseServiceLambda?: lambda.Function;
  readonly opensearchDomain?: oss.IDomain;
  readonly opensearchEndpoint?: string;
  readonly documentsTable?: dynamodb.ITable;
  readonly segmentsTable?: dynamodb.ITable;
  readonly indicesTable?: dynamodb.ITable;
  readonly documentsBucket?: s3.IBucket;
  readonly vpc?: ec2.IVpc;
  readonly commonLayer?: lambda.ILayerVersion;
  readonly lambdaConfig?: {
    timeout?: cdk.Duration;
    memorySize?: number;
    retryAttempts?: number;
  };
  readonly sqsBatchSize?: number;
}

/**
 * AWS IDP AI Analysis - Workflow Stack
 *
 * Step Functions:
 * - BDA Processing
 * - BDA Status Checker
 * - Document Indexer
 * - PDF Text Extractor
 * - Vision ReAct Analysis (NEW - iterative image-based analysis)
 * - ReAct Analysis Finalizer
 * - Get Document Pages
 * - SQS Trigger
 */
export class WorkflowStack extends cdk.Stack {
  public readonly documentProcessingWorkflow?: sfn.StateMachine;
  public readonly stepFunctionTriggerLambda?: lambda.Function;
  public readonly bdaProcessorLambda: lambda.Function;
  public readonly bdaStatusCheckerLambda: lambda.Function;
  // public readonly relatedPagesAnalysisLambda: lambda.Function;
  public readonly pdfTextExtractorLambda: lambda.Function;
  public readonly documentIndexerLambda: lambda.Function;
  public readonly reactAnalysisLambda: lambda.Function;
  public readonly reactAnalysisFinalizerLambda: lambda.Function;
  public readonly documentSummarizerLambda: lambda.Function;
  public readonly getDocumentPagesLambda: lambda.Function;
  private readonly props: WorkflowStackProps;

  constructor(scope: Construct, id: string, props: WorkflowStackProps) {
    super(scope, id, props);
    
    this.props = props;
    const stage = props.stage || 'prod';

    // Get required resources from Props
    const documentsTable = props.documentsTable;
    const segmentsTable = props.segmentsTable;
    const indicesTable = props.indicesTable;

    const documentsBucket = props.documentsBucket;
    const opensearchEndpoint = props.opensearchEndpoint;
    const bedrock = props.bedrock;
    const analysis = props.analysis;
    const commonLayer = props.commonLayer;

    if (!documentsTable || !segmentsTable || !documentsBucket || !indicesTable) {
      throw new Error('Required tables and bucket must be provided in props');
    }

    // 1. Create BDA Processor Lambda
    this.bdaProcessorLambda = this.createBdaProcessorLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      documentsBucket,
      commonLayer,
    );

    // 2. Create BDA Status Checker Lambda
    this.bdaStatusCheckerLambda = this.createBdaStatusCheckerLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      commonLayer,
    );

    // 3. Create PDF Text Extractor Lambda
    this.pdfTextExtractorLambda = this.createPdfTextExtractorLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      documentsBucket,
      opensearchEndpoint,
      props.opensearchDomain,
      props.vpc,
      commonLayer,
    );

    // 4. Create Document Indexer Lambda
    this.documentIndexerLambda = this.createDocumentIndexerLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      documentsBucket,
      opensearchEndpoint,
      props.opensearchDomain,
      props.vpc,
      commonLayer,
    );

    // 5. Create ReAct Analysis Lambda (commenting out to replace with Vision Plan Execute)
    // this.reactAnalysisLambda = this.createReactAnalysisLambda(
    //   stage,
    //   indicesTable,
    //   documentsTable,
    //   segmentsTable,
    //   documentsBucket,
    //   opensearchEndpoint,
    //   props.opensearchDomain,
    //   props.vpc,
    //   bedrock,
    //   analysis,
    // );

    // 5-NEW. Create Vision Plan Execute Analysis Lambda (commented out for Vision ReAct)
    // this.reactAnalysisLambda = this.createVisionPlanExecuteAnalysisLambda(
    //   stage,
    //   indicesTable,
    //   documentsTable,
    //   segmentsTable,
    //   documentsBucket,
    //   opensearchEndpoint,
    //   props.opensearchDomain,
    //   props.vpc,
    //   bedrock,
    //   analysis,
    // );

    // 5-REACT. Create Vision ReAct Analysis Lambda
    this.reactAnalysisLambda = this.createVisionReactAnalysisLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      documentsBucket,
      opensearchEndpoint,
      props.opensearchDomain,
      props.vpc,
      bedrock,
      analysis,
    );

    // 6. Create ReAct Analysis Finalizer Lambda
    this.reactAnalysisFinalizerLambda = this.createReactAnalysisFinalizerLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      commonLayer,
      props,
    );

    // 7. Create Document Summarizer Lambda
    this.documentSummarizerLambda = this.createDocumentSummarizerLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      opensearchEndpoint,
      props.opensearchDomain,
      props.vpc,
      bedrock,
      commonLayer,
    );

    // 8. Create GetDocumentPages Lambda
    this.getDocumentPagesLambda = this.createGetDocumentPagesLambda(
      stage,
      indicesTable,
      documentsTable,
      segmentsTable,
      commonLayer,
    );

    // 9. Create Workflow
    this.documentProcessingWorkflow = this.createBdaBasedDocumentProcessingWorkflow(
      stage,
      this.bdaProcessorLambda,
      this.bdaStatusCheckerLambda,
      this.reactAnalysisLambda,
      this.reactAnalysisFinalizerLambda,
      this.documentSummarizerLambda,
      this.getDocumentPagesLambda,
    );

    // 10. Create SQS Trigger Lambda
    if (props.documentProcessingQueue) {
      this.stepFunctionTriggerLambda = this.createStepFunctionTriggerLambda(
        stage,
        props.documentProcessingQueue,
        props.sqsBatchSize,
      );
    }

    // 11. CDK Nag suppression settings
    this.addNagSuppressions();
  }

  /**
   * Create BDA Processor Lambda
   */
  private createBdaProcessorLambda(
    stage: string,
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    documentsBucket: s3.IBucket,
    commonLayer?: lambda.ILayerVersion,
  ): lambda.Function {
    const bdaProcessorConstruct = new StandardLambda(this, 'BdaProcessor', {
      functionName: 'aws-idp-ai-bda-processor',
      codePath: 'step-functions/bda-processor',
      description: 'AWS IDP AI BDA Processor Lambda Function',
      environment: {
        STAGE: stage,
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
        BDA_PROJECT_NAME: 'aws-idp-ai-bda-project',
      },
      deadLetterQueueEnabled: false,
      commonLayer: commonLayer,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      stage: stage,
    });

    const lambdaFunction = bdaProcessorConstruct.function;

    // DynamoDB table access permission
    documentsTable.grantReadWriteData(lambdaFunction);

    // S3 bucket access permission
    documentsBucket.grantReadWrite(lambdaFunction);

    // Bedrock Data Automation permission
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeDataAutomationAsync',
          'bedrock:GetDataAutomationStatus',
          'bedrock:ListDataAutomationProjects',
          'bedrock:CreateDataAutomationProject',
        ],
        resources: ['*'],
      }),
    );

    return lambdaFunction;
  }

  /**
   * Create BDA Status Checker Lambda
   */
  private createBdaStatusCheckerLambda(
    stage: string, 
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    commonLayer?: lambda.ILayerVersion,
  ): lambda.Function {
    const bdaStatusCheckerConstruct = new StandardLambda(this, 'BdaStatusChecker', {
      functionName: 'aws-idp-ai-bda-status-checker',
      codePath: 'step-functions/bda-status-checker',
      description: 'AWS IDP AI BDA Status Checker Lambda Function',
      environment: {
        STAGE: stage,
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
      },
      deadLetterQueueEnabled: false,
      commonLayer: commonLayer,
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      stage: stage,
    });

    const lambdaFunction = bdaStatusCheckerConstruct.function;

    // Bedrock Data Automation permission
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:GetDataAutomationStatus',
        ],
        resources: ['*'],
      }),
    );

    // DynamoDB Documents table access permission
    documentsTable.grantReadWriteData(lambdaFunction);

    return lambdaFunction;
  }

  /**
   * Create PDF Text Extractor Lambda
   */
  private createPdfTextExtractorLambda(
    stage: string,
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    documentsBucket: s3.IBucket,
    opensearchEndpoint?: string,
    opensearchDomain?: oss.IDomain,
    vpc?: ec2.IVpc,
    commonLayer?: lambda.ILayerVersion,
  ): lambda.Function {
    const pdfTextExtractorConstruct = new StandardLambda(this, 'PdfTextExtractor', {
      functionName: 'aws-idp-ai-pdf-text-extractor',
      codePath: 'step-functions/pdf-text-extractor',
      description: 'AWS IDP AI PDF Text Extractor Lambda Function - Extract text from PDF and index to OpenSearch',
      environment: {
        STAGE: stage,
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
        ...(opensearchEndpoint && {
          OPENSEARCH_ENDPOINT: opensearchEndpoint,
          OPENSEARCH_INDEX_NAME: 'aws-idp-ai-analysis',
          OPENSEARCH_REGION: cdk.Stack.of(this).region,
        }),
      },
      deadLetterQueueEnabled: false,
      commonLayer: commonLayer,
      timeout: cdk.Duration.minutes(10),
      memorySize: 2048,
      // VPC setup (deployed in the same VPC as the OpenSearch domain)
      vpc: (vpc && opensearchDomain) ? vpc : undefined,
      stage: stage,
    });

    const lambdaFunction = pdfTextExtractorConstruct.function;

    // DynamoDB table access permission
    documentsTable.grantReadWriteData(lambdaFunction);
    segmentsTable.grantReadData(lambdaFunction);

    // S3 bucket access permission
    documentsBucket.grantRead(lambdaFunction);

    // OpenSearch permission (optional)
    if (opensearchEndpoint && opensearchDomain) {
      lambdaFunction.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'es:ESHttpPost',
            'es:ESHttpPut',
            'es:ESHttpGet',
            'es:ESHttpDelete',
            'es:ESHttpHead',
          ],
          resources: [
            opensearchDomain.domainArn,
            `${opensearchDomain.domainArn}/*`
          ],
        }),
      );
    }

    // Bedrock permission
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ],
        resources: [
          // Titan Embedding model
          'arn:aws:bedrock:*::foundation-model/amazon.titan-embed-*',
          // Cohere Embedding model
          'arn:aws:bedrock:*::foundation-model/cohere.embed-*',
        ],
      }),
    );

    return lambdaFunction;
  }

  /**
   * Create Document Indexer Lambda
   */
  private createDocumentIndexerLambda(
    stage: string,
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    documentsBucket: s3.IBucket,
    opensearchEndpoint?: string,
    opensearchDomain?: oss.IDomain,
    vpc?: ec2.IVpc,
    commonLayer?: lambda.ILayerVersion,
  ): lambda.Function {
    const documentIndexerConstruct = new StandardLambda(this, 'DocumentIndexer', {
      functionName: 'aws-idp-ai-document-indexer',
      codePath: 'step-functions/document-indexer',
      description: 'AWS IDP AI Document Indexer Lambda Function - Process BDA results and index to OpenSearch',
      environment: {
        STAGE: stage,
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
        ...(opensearchEndpoint && {
          OPENSEARCH_ENDPOINT: opensearchEndpoint,
          OPENSEARCH_INDEX_NAME: 'aws-idp-ai-analysis',
          OPENSEARCH_REGION: cdk.Stack.of(this).region,
        }),
      },
      deadLetterQueueEnabled: false,
      commonLayer: commonLayer,
      timeout: cdk.Duration.minutes(10),
      memorySize: 2048,
      // VPC setup (deployed in the same VPC as the OpenSearch domain)
      vpc: (vpc && opensearchDomain) ? vpc : undefined,
      stage: stage,
    });

    const lambdaFunction = documentIndexerConstruct.function;

    // DynamoDB table access permission
    documentsTable.grantReadWriteData(lambdaFunction);
    segmentsTable.grantReadWriteData(lambdaFunction);


    // S3 bucket access permission (for BDA results)
    documentsBucket.grantRead(lambdaFunction);

    // Bedrock permission (for embedding model)
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ],
        resources: [
          // Titan Embedding model
          'arn:aws:bedrock:*::foundation-model/amazon.titan-embed-*',
          // Cohere Embedding model
          'arn:aws:bedrock:*::foundation-model/cohere.embed-*',
        ],
      }),
    );

    // OpenSearch permission
    if (opensearchEndpoint && opensearchDomain) {
      lambdaFunction.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'es:ESHttpPost',
            'es:ESHttpPut',
            'es:ESHttpGet',
            'es:ESHttpDelete',
            'es:ESHttpHead',
          ],
          resources: [
            opensearchDomain.domainArn,
            `${opensearchDomain.domainArn}/*`
          ],
        }),
      );
    }

    return lambdaFunction;
  }

  /**
   * Create React Analysis Lambda
   */
  // private createReactAnalysisLambda(
  //   stage: string,
  //   indicesTable: dynamodb.ITable,
  //   documentsTable: dynamodb.ITable,
  //   segmentsTable: dynamodb.ITable,
  //   documentsBucket: s3.IBucket,
  //   opensearchEndpoint?: string,
  //   opensearchDomain?: oss.IDomain,
  //   vpc?: ec2.IVpc,
  //   bedrock?: {
  //     analysisAgentModelId?: string;
  //     analysisAgentMaxToken?: number;
  //     analysisImageModelId?: string;
  //     analysisImageMaxToken?: number;
  //     analysisVideoModelId?: string;
  //   },
  //   analysis?: {
  //     previousAnalysisMaxCharacters?: number;
  //     maxIterations?: number;
  //   },
  // ): lambda.Function {
  //   // Create Analysis Package Lambda Layer
  //   const analysisPackageLayer = new lambda.LayerVersion(
  //     this,
  //     'AnalysisPackageLayer',
  //     {
  //       code: lambda.Code.fromAsset(
  //         path.join(
  //           __dirname,
  //           '../lambda_layer/custom_layer_analysis_package.zip',
  //         ),
  //       ),
  //       compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
  //       description: 'Analysis package dependencies for Lambda functions',
  //     },
  //   );

  //   // Create Image Processing Lambda Layer (for ReAct analysis)
  //   const imageProcessingLayerForReact = new lambda.LayerVersion(
  //     this,
  //     'ImageProcessingLayerForReact',
  //     {
  //       layerVersionName: `aws-idp-ai-image-processing-layer-react-${stage}`,
  //       code: lambda.Code.fromAsset(
  //         'src/lambda_layer/custom_layer_image_processing.zip',
  //       ),
  //       compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
  //       description:
  //         'Image processing libraries including PyMuPDF (fitz) for ReAct analysis image processing',
  //     },
  //   );

  //   const reactAnalysisConstruct = new StandardLambda(this, 'ReactAnalysis', {
  //     functionName: 'aws-idp-ai-react-analysis',
  //     codePath: 'step-functions/react-analysis',
  //     description: 'AWS IDP AI ReAct Analysis Lambda Function',
  //     environment: {
  //       STAGE: stage,
  //       BEDROCK_AGENT_MODEL_ID: bedrock?.analysisAgentModelId || '',
  //       BEDROCK_AGENT_MAX_TOKENS:
  //         bedrock?.analysisAgentMaxToken?.toString() || '8192',
  //       BEDROCK_IMAGE_MODEL_ID: bedrock?.analysisImageModelId || '',
  //       BEDROCK_IMAGE_MAX_TOKENS:
  //         bedrock?.analysisImageMaxToken?.toString() || '8192',
  //       BEDROCK_VIDEO_MODEL_ID: bedrock?.analysisVideoModelId || '',
  //       PREVIOUS_ANALYSIS_MAX_CHARACTERS:
  //         analysis?.previousAnalysisMaxCharacters?.toString() || '100000',
  //       MAX_ITERATIONS:
  //         analysis?.maxIterations?.toString() || '10',
  //       DOCUMENTS_TABLE_NAME: documentsTable.tableName,
  //       SEGMENTS_TABLE_NAME: segmentsTable.tableName,
  //       INDICES_TABLE_NAME: indicesTable.tableName,
  //       BUCKET_OWNER_ACCOUNT_ID: cdk.Stack.of(this).account, // VideoAnalyzerTool용 계정 ID
  //       ...(opensearchEndpoint && {
  //         OPENSEARCH_ENDPOINT: opensearchEndpoint,
  //         OPENSEARCH_INDEX_NAME: 'aws-idp-ai-analysis',
  //         OPENSEARCH_REGION: cdk.Stack.of(this).region,
  //       }),
  //     },
  //     deadLetterQueueEnabled: false,
  //     layers: [analysisPackageLayer, imageProcessingLayerForReact],
  //     timeout: cdk.Duration.minutes(15),
  //     memorySize: 3008,
  //     vpc: vpc,
  //     stage: stage,
  //   });

  //   const lambdaFunction = reactAnalysisConstruct.function;

  //   // DynamoDB table access permission
  //   documentsTable.grantReadData(lambdaFunction);
  //   segmentsTable.grantReadWriteData(lambdaFunction);

  //   // S3 bucket access permission
  //   documentsBucket.grantReadWrite(lambdaFunction);

  //   // Additional S3 permission (explicit permission for image access)
  //   lambdaFunction.addToRolePolicy(
  //     new iam.PolicyStatement({
  //       effect: iam.Effect.ALLOW,
  //       actions: [
  //         's3:GetObject',
  //         's3:GetObjectVersion',
  //         's3:PutObject',
  //         's3:PutObjectAcl',
  //         's3:DeleteObject',
  //         's3:ListBucket',
  //       ],
  //       resources: [
  //         documentsBucket.bucketArn,
  //         `${documentsBucket.bucketArn}/*`,
  //       ],
  //     }),
  //   );

  //   // OpenSearch permission
  //   if (opensearchDomain) {
  //     opensearchDomain.grantWrite(lambdaFunction);
  //     opensearchDomain.grantRead(lambdaFunction);
  //   }

  //   // Bedrock permission (for all AI models)
  //   lambdaFunction.addToRolePolicy(
  //     new iam.PolicyStatement({
  //       effect: iam.Effect.ALLOW,
  //       actions: [
  //         'bedrock:InvokeModel',
  //         'bedrock:InvokeModelWithResponseStream',
  //         'bedrock:Converse',
  //         'bedrock:ConverseStream',
  //       ],
  //       resources: [
  //         // Foundation Models
  //         'arn:aws:bedrock:*::foundation-model/anthropic.claude-*',
  //         'arn:aws:bedrock:*::foundation-model/amazon.titan-*',
  //         'arn:aws:bedrock:*::foundation-model/amazon.nova-*',
  //         'arn:aws:bedrock:*::foundation-model/meta.llama-*',
  //         'arn:aws:bedrock:*::foundation-model/mistral.*',
  //         'arn:aws:bedrock:*::foundation-model/cohere.*',
  //         'arn:aws:bedrock:*::foundation-model/ai21.*',
  //         'arn:aws:bedrock:*::foundation-model/twelvelabs.*',
  //         'arn:aws:bedrock:*::foundation-model/us.twelvelabs.*',
  //         // Inference Profiles (Cross-region)
  //         `arn:aws:bedrock:*:${this.account}:inference-profile/*`,
  //         // Application Inference Profiles
  //         `arn:aws:bedrock:*:${this.account}:application-inference-profile/*`,
  //       ],
  //     }),
  //   );

  //   // OpenSearch permission (if OpenSearch domain exists)
  //   if (opensearchDomain) {
  //     lambdaFunction.addToRolePolicy(
  //       new iam.PolicyStatement({
  //         effect: iam.Effect.ALLOW,
  //         actions: [
  //           'es:ESHttpPost',
  //           'es:ESHttpPut',
  //           'es:ESHttpGet',
  //           'es:ESHttpDelete',
  //           'es:ESHttpHead',
  //         ],
  //         resources: [
  //           opensearchDomain.domainArn,
  //           `${opensearchDomain.domainArn}/*`,
  //         ],
  //       }),
  //     );

  //     // Additional permission for OpenSearch access within VPC
  //     if (vpc) {
  //       lambdaFunction.addToRolePolicy(
  //         new iam.PolicyStatement({
  //           effect: iam.Effect.ALLOW,
  //           actions: [
  //             'ec2:CreateNetworkInterface',
  //             'ec2:DescribeNetworkInterfaces',
  //             'ec2:DeleteNetworkInterface',
  //             'ec2:AttachNetworkInterface',
  //             'ec2:DetachNetworkInterface',
  //           ],
  //           resources: ['*'],
  //         }),
  //       );
  //     }
  //   }

  //   return lambdaFunction;
  // }

  /**
   * Create Vision Plan Execute Analysis Lambda (NEW)
   */
  // private createVisionPlanExecuteAnalysisLambda(
  //   stage: string,
  //   indicesTable: dynamodb.ITable,
  //   documentsTable: dynamodb.ITable,
  //   segmentsTable: dynamodb.ITable,
  //   documentsBucket: s3.IBucket,
  //   opensearchEndpoint?: string,
  //   opensearchDomain?: oss.IDomain,
  //   vpc?: ec2.IVpc,
  //   bedrock?: {
  //     analysisAgentModelId?: string;
  //     analysisAgentMaxToken?: number;
  //     analysisImageModelId?: string;
  //     analysisImageMaxToken?: number;
  //     analysisVideoModelId?: string;
  //   },
  //   analysis?: {
  //     previousAnalysisMaxCharacters?: number;
  //     maxIterations?: number;
  //   },
  // ): lambda.Function {
  //   // Create Analysis Package Lambda Layer
  //   const analysisPackageLayer = new lambda.LayerVersion(
  //     this,
  //     'VisionAnalysisPackageLayer',
  //     {
  //       code: lambda.Code.fromAsset(
  //         path.join(
  //           __dirname,
  //           '../lambda_layer/custom_layer_analysis_package.zip',
  //         ),
  //       ),
  //       compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
  //       description: 'Analysis package dependencies for Vision Plan Execute Lambda functions',
  //     },
  //   );

  //   // Create Image Processing Lambda Layer (for Vision Plan Execute analysis)
  //   const imageProcessingLayerForVision = new lambda.LayerVersion(
  //     this,
  //     'ImageProcessingLayerForVision',
  //     {
  //       layerVersionName: `aws-idp-ai-image-processing-layer-vision-${stage}`,
  //       code: lambda.Code.fromAsset(
  //         'src/lambda_layer/custom_layer_image_processing.zip',
  //       ),
  //       compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
  //       description:
  //         'Image processing libraries including PyMuPDF (fitz) for Vision Plan Execute analysis image processing',
  //     },
  //   );

  //   const visionPlanExecuteConstruct = new StandardLambda(this, 'VisionPlanExecuteAnalysis', {
  //     functionName: 'aws-idp-ai-vision-plan-execute-analysis',
  //     codePath: 'step-functions/vision-plan-execute',
  //     description: 'AWS IDP AI Vision Plan Execute Analysis Lambda Function',
  //     environment: {
  //       STAGE: stage,
  //       BEDROCK_AGENT_MODEL_ID: bedrock?.analysisAgentModelId || '',
  //       BEDROCK_AGENT_MAX_TOKENS:
  //         bedrock?.analysisAgentMaxToken?.toString() || '8192',
  //       BEDROCK_IMAGE_MODEL_ID: bedrock?.analysisImageModelId || '',
  //       BEDROCK_IMAGE_MAX_TOKENS:
  //         bedrock?.analysisImageMaxToken?.toString() || '8192',
  //       BEDROCK_VIDEO_MODEL_ID: bedrock?.analysisVideoModelId || '',
  //       PREVIOUS_ANALYSIS_MAX_CHARACTERS:
  //         analysis?.previousAnalysisMaxCharacters?.toString() || '100000',
  //       MAX_ITERATIONS:
  //         analysis?.maxIterations?.toString() || '10',
  //       DOCUMENTS_TABLE_NAME: documentsTable.tableName,
  //       SEGMENTS_TABLE_NAME: segmentsTable.tableName,
  //       INDICES_TABLE_NAME: indicesTable.tableName,
  //       BUCKET_OWNER_ACCOUNT_ID: cdk.Stack.of(this).account, // VideoAnalyzerTool용 계정 ID
  //       ...(opensearchEndpoint && {
  //         OPENSEARCH_ENDPOINT: opensearchEndpoint,
  //         OPENSEARCH_INDEX_NAME: 'aws-idp-ai-analysis',
  //         OPENSEARCH_REGION: cdk.Stack.of(this).region,
  //       }),
  //     },
  //     deadLetterQueueEnabled: false,
  //     layers: [analysisPackageLayer, imageProcessingLayerForVision],
  //     timeout: cdk.Duration.minutes(15),
  //     memorySize: 3008,
  //     vpc: vpc,
  //     stage: stage,
  //   });

  //   const lambdaFunction = visionPlanExecuteConstruct.function;

  //   // DynamoDB table access permission
  //   documentsTable.grantReadData(lambdaFunction);
  //   segmentsTable.grantReadWriteData(lambdaFunction);

  //   // S3 bucket access permission
  //   documentsBucket.grantReadWrite(lambdaFunction);

  //   // Additional S3 permission (explicit permission for image access)
  //   lambdaFunction.addToRolePolicy(
  //     new iam.PolicyStatement({
  //       effect: iam.Effect.ALLOW,
  //       actions: [
  //         's3:GetObject',
  //         's3:GetObjectVersion',
  //         's3:PutObject',
  //         's3:PutObjectAcl',
  //         's3:DeleteObject',
  //         's3:ListBucket',
  //       ],
  //       resources: [
  //         documentsBucket.bucketArn,
  //         `${documentsBucket.bucketArn}/*`,
  //       ],
  //     }),
  //   );

  //   // OpenSearch permission
  //   if (opensearchDomain) {
  //     opensearchDomain.grantWrite(lambdaFunction);
  //     opensearchDomain.grantRead(lambdaFunction);
  //   }

  //   // Bedrock permission (for all AI models)
  //   lambdaFunction.addToRolePolicy(
  //     new iam.PolicyStatement({
  //       effect: iam.Effect.ALLOW,
  //       actions: [
  //         'bedrock:InvokeModel',
  //         'bedrock:InvokeModelWithResponseStream',
  //         'bedrock:Converse',
  //         'bedrock:ConverseStream',
  //       ],
  //       resources: [
  //         // Foundation Models
  //         'arn:aws:bedrock:*::foundation-model/anthropic.claude-*',
  //         'arn:aws:bedrock:*::foundation-model/amazon.titan-*',
  //         'arn:aws:bedrock:*::foundation-model/amazon.nova-*',
  //         'arn:aws:bedrock:*::foundation-model/meta.llama-*',
  //         'arn:aws:bedrock:*::foundation-model/mistral.*',
  //         'arn:aws:bedrock:*::foundation-model/cohere.*',
  //         'arn:aws:bedrock:*::foundation-model/ai21.*',
  //         'arn:aws:bedrock:*::foundation-model/twelvelabs.*',
  //         'arn:aws:bedrock:*::foundation-model/us.twelvelabs.*',
  //         // Inference Profiles (Cross-region)
  //         `arn:aws:bedrock:*:${this.account}:inference-profile/*`,
  //         // Application Inference Profiles
  //         `arn:aws:bedrock:*:${this.account}:application-inference-profile/*`,
  //       ],
  //     }),
  //   );

  //   // OpenSearch permission (if OpenSearch domain exists)
  //   if (opensearchDomain) {
  //     lambdaFunction.addToRolePolicy(
  //       new iam.PolicyStatement({
  //         effect: iam.Effect.ALLOW,
  //         actions: [
  //           'es:ESHttpPost',
  //           'es:ESHttpPut',
  //           'es:ESHttpGet',
  //           'es:ESHttpDelete',
  //           'es:ESHttpHead',
  //         ],
  //         resources: [
  //           opensearchDomain.domainArn,
  //           `${opensearchDomain.domainArn}/*`,
  //         ],
  //       }),
  //     );

  //     // Additional permission for OpenSearch access within VPC
  //     if (vpc) {
  //       lambdaFunction.addToRolePolicy(
  //         new iam.PolicyStatement({
  //           effect: iam.Effect.ALLOW,
  //           actions: [
  //             'ec2:CreateNetworkInterface',
  //             'ec2:DescribeNetworkInterfaces',
  //             'ec2:DeleteNetworkInterface',
  //             'ec2:AttachNetworkInterface',
  //             'ec2:DetachNetworkInterface',
  //           ],
  //           resources: ['*'],
  //         }),
  //       );
  //     }
  //   }

  //   return lambdaFunction;
  // }

  /**
   * Create Vision ReAct Analysis Lambda
   */
  private createVisionReactAnalysisLambda(
    stage: string,
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    documentsBucket: s3.IBucket,
    opensearchEndpoint?: string,
    opensearchDomain?: oss.IDomain,
    vpc?: ec2.IVpc,
    bedrock?: {
      analysisAgentModelId?: string;
      analysisAgentMaxToken?: number;
      analysisImageModelId?: string;
      analysisImageMaxToken?: number;
      analysisVideoModelId?: string;
    },
    analysis?: {
      previousAnalysisMaxCharacters?: number;
      maxIterations?: number;
    },
  ): lambda.Function {
    // Create Analysis Package Lambda Layer
    const analysisPackageLayer = new lambda.LayerVersion(
      this,
      'VisionReactAnalysisPackageLayer',
      {
        code: lambda.Code.fromAsset(
          path.join(
            __dirname,
            '../lambda_layer/custom_layer_analysis_package.zip',
          ),
        ),
        compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
        description: 'Analysis package dependencies for Vision ReAct Lambda functions',
      },
    );

    // Create Image Processing Lambda Layer (for Vision ReAct analysis)
    const imageProcessingLayerForReact = new lambda.LayerVersion(
      this,
      'ImageProcessingLayerForReact',
      {
        layerVersionName: `aws-idp-ai-image-processing-layer-react-${stage}`,
        code: lambda.Code.fromAsset(
          'src/lambda_layer/custom_layer_image_processing.zip',
        ),
        compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
        description:
          'Image processing libraries including PyMuPDF (fitz) for Vision ReAct analysis image processing',
      },
    );

    const visionReactConstruct = new StandardLambda(this, 'VisionReactAnalysis', {
      functionName: 'aws-idp-ai-vision-react-analysis',
      codePath: 'step-functions/vision-react',
      description: 'AWS IDP AI Vision ReAct Analysis Lambda Function',
      environment: {
        STAGE: stage,
        BEDROCK_AGENT_MODEL_ID: bedrock?.analysisAgentModelId || '',
        BEDROCK_AGENT_MAX_TOKENS:
          bedrock?.analysisAgentMaxToken?.toString() || '8192',
        BEDROCK_IMAGE_MODEL_ID: bedrock?.analysisImageModelId || '',
        BEDROCK_IMAGE_MAX_TOKENS:
          bedrock?.analysisImageMaxToken?.toString() || '8192',
        BEDROCK_VIDEO_MODEL_ID: bedrock?.analysisVideoModelId || '',
        PREVIOUS_ANALYSIS_MAX_CHARACTERS:
          analysis?.previousAnalysisMaxCharacters?.toString() || '100000',
        MAX_ITERATIONS:
          analysis?.maxIterations?.toString() || '5',
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
        DOCUMENTS_BUCKET_NAME: documentsBucket.bucketName,
        BUCKET_OWNER_ACCOUNT_ID: cdk.Stack.of(this).account, // VideoAnalyzerTool용 계정 ID
        ...(opensearchEndpoint && {
          OPENSEARCH_ENDPOINT: opensearchEndpoint,
          OPENSEARCH_INDEX_NAME: 'aws-idp-ai-analysis',
          OPENSEARCH_REGION: cdk.Stack.of(this).region,
        }),
      },
      deadLetterQueueEnabled: false,
      layers: [analysisPackageLayer, imageProcessingLayerForReact],
      timeout: cdk.Duration.minutes(15),
      memorySize: 3008,
      vpc: vpc,
      stage: stage,
    });

    const lambdaFunction = visionReactConstruct.function;

    // DynamoDB table access permission
    documentsTable.grantReadData(lambdaFunction);
    segmentsTable.grantReadWriteData(lambdaFunction);

    // S3 bucket access permission
    documentsBucket.grantReadWrite(lambdaFunction);

    // Additional S3 permission (explicit permission for image access)
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          's3:GetObject',
          's3:GetObjectVersion',
          's3:PutObject',
          's3:PutObjectAcl',
          's3:DeleteObject',
          's3:ListBucket',
        ],
        resources: [
          documentsBucket.bucketArn,
          `${documentsBucket.bucketArn}/*`,
        ],
      }),
    );

    // OpenSearch permission
    if (opensearchDomain) {
      opensearchDomain.grantWrite(lambdaFunction);
      opensearchDomain.grantRead(lambdaFunction);
    }

    // Bedrock permission (for all AI models)
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
          'bedrock:Converse',
          'bedrock:ConverseStream',
        ],
        resources: [
          // Foundation Models
          'arn:aws:bedrock:*::foundation-model/anthropic.claude-*',
          'arn:aws:bedrock:*::foundation-model/amazon.titan-*',
          'arn:aws:bedrock:*::foundation-model/amazon.nova-*',
          'arn:aws:bedrock:*::foundation-model/meta.llama-*',
          'arn:aws:bedrock:*::foundation-model/mistral.*',
          'arn:aws:bedrock:*::foundation-model/cohere.*',
          'arn:aws:bedrock:*::foundation-model/ai21.*',
          'arn:aws:bedrock:*::foundation-model/twelvelabs.*',
          'arn:aws:bedrock:*::foundation-model/us.twelvelabs.*',
          // Inference Profiles (Cross-region)
          `arn:aws:bedrock:*:${this.account}:inference-profile/*`,
          // Application Inference Profiles
          `arn:aws:bedrock:*:${this.account}:application-inference-profile/*`,
        ],
      }),
    );

    // OpenSearch permission (if OpenSearch domain exists)
    if (opensearchDomain) {
      lambdaFunction.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'es:ESHttpPost',
            'es:ESHttpPut',
            'es:ESHttpGet',
            'es:ESHttpDelete',
            'es:ESHttpHead',
          ],
          resources: [
            opensearchDomain.domainArn,
            `${opensearchDomain.domainArn}/*`,
          ],
        }),
      );

      // Additional permission for OpenSearch access within VPC
      if (vpc) {
        lambdaFunction.addToRolePolicy(
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: [
              'ec2:CreateNetworkInterface',
              'ec2:DescribeNetworkInterfaces',
              'ec2:DeleteNetworkInterface',
              'ec2:AttachNetworkInterface',
              'ec2:DetachNetworkInterface',
            ],
            resources: ['*'],
          }),
        );
      }
    }

    return lambdaFunction;
  }

  /**
   * Create React Analysis Finalizer Lambda
   */
  private createReactAnalysisFinalizerLambda(
    stage: string,
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    commonLayer?: lambda.ILayerVersion,
    props?: WorkflowStackProps,
  ): lambda.Function {
    const reactAnalysisFinalizerConstruct = new StandardLambda(this, 'ReactAnalysisFinalizer', {
      functionName: 'aws-idp-ai-analysis-finalizer',
      codePath: 'step-functions/analysis-finalizer',
      description: 'AWS IDP AI React Analysis Finalizer',
      environment: {
        STAGE: stage,
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
        OPENSEARCH_ENDPOINT: props?.opensearchEndpoint || '',
        OPENSEARCH_INDEX_NAME: 'aws-idp-ai-analysis',
        OPENSEARCH_REGION: cdk.Stack.of(this).region,
      },
      deadLetterQueueEnabled: false,
      commonLayer: commonLayer,
      timeout: cdk.Duration.minutes(15),
      memorySize: 2048,
      vpc: props?.vpc,
      stage: stage,
    });

    const lambdaFunction = reactAnalysisFinalizerConstruct.function;

    // DynamoDB table access permission
    documentsTable.grantReadWriteData(lambdaFunction);
    segmentsTable.grantReadWriteData(lambdaFunction);

    // Bedrock permission (for embedding model)
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ],
        resources: [
          // Titan Embedding model
          'arn:aws:bedrock:*::foundation-model/amazon.titan-embed-*',
          // Cohere Embedding model
          'arn:aws:bedrock:*::foundation-model/cohere.embed-*',
        ],
      }),
    );

    // OpenSearch permission (if OpenSearch domain exists)
    if (props?.opensearchDomain) {
      lambdaFunction.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'es:ESHttpPost',
            'es:ESHttpPut',
            'es:ESHttpGet',
            'es:ESHttpDelete',
            'es:ESHttpHead',
          ],
          resources: [
            props.opensearchDomain.domainArn,
            `${props.opensearchDomain.domainArn}/*`,
          ],
        }),
      );
    }

    return lambdaFunction;
  }

  /**
   * Create Document Summarizer Lambda
   */
  private createDocumentSummarizerLambda(
    stage: string,
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    opensearchEndpoint?: string,
    opensearchDomain?: oss.IDomain,
    vpc?: ec2.IVpc,
    bedrock?: {
      analysisAgentModelId?: string;
      analysisAgentMaxToken?: number;
      analysisImageModelId?: string;
      analysisImageMaxToken?: number;
      analysisSummarizerModelId?: string;
      analysisSummarizerMaxToken?: number;
      pageSummaryModelId?: string;
      pageSummaryMaxToken?: number;
    },
    commonLayer?: lambda.ILayerVersion,
  ): lambda.Function {
    const documentSummarizerConstruct = new StandardLambda(this, 'DocumentSummarizer', {
      functionName: 'aws-idp-ai-document-summarizer',
      codePath: 'step-functions/document-summarizer',
      description: 'AWS IDP AI Document Summarizer - Generate document-level summary using LLM',
      environment: {
        STAGE: stage,
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
        BEDROCK_SUMMARY_MODEL_ID: bedrock?.analysisSummarizerModelId || 'us.anthropic.claude-3-7-sonnet-20250219-v1:0',
        BEDROCK_SUMMARY_MAX_TOKENS: bedrock?.analysisSummarizerMaxToken?.toString() || '8192',
        BEDROCK_PAGE_SUMMARY_MODEL_ID: bedrock?.pageSummaryModelId || 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
        BEDROCK_PAGE_SUMMARY_MAX_TOKENS: bedrock?.pageSummaryMaxToken?.toString() || '8192',
        ...(opensearchEndpoint && {
          OPENSEARCH_ENDPOINT: opensearchEndpoint,
          OPENSEARCH_INDEX_NAME: 'aws-idp-ai-analysis',
          OPENSEARCH_REGION: cdk.Stack.of(this).region,
        }),
      },
      deadLetterQueueEnabled: false,
      commonLayer: commonLayer,
      timeout: cdk.Duration.minutes(15),
      memorySize: 2048,
      vpc: vpc,
      stage: stage,
    });

    const lambdaFunction = documentSummarizerConstruct.function;

    // DynamoDB table access permission
    documentsTable.grantReadWriteData(lambdaFunction);
    segmentsTable.grantReadData(lambdaFunction);

    // OpenSearch permission
    if (opensearchEndpoint && opensearchDomain) {
      lambdaFunction.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'es:ESHttpPost',
            'es:ESHttpPut',
            'es:ESHttpGet',
            'es:ESHttpDelete',
            'es:ESHttpHead',
          ],
          resources: [
            opensearchDomain.domainArn,
            `${opensearchDomain.domainArn}/*`
          ],
        }),
      );
    }

    // Bedrock permission for summary generation
    lambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
          'bedrock:Converse',
          'bedrock:ConverseStream',
        ],
        resources: [
          // Foundation Models
          'arn:aws:bedrock:*::foundation-model/anthropic.claude-*',
          'arn:aws:bedrock:*::foundation-model/amazon.titan-*',
          'arn:aws:bedrock:*::foundation-model/amazon.nova-*',
          'arn:aws:bedrock:*::foundation-model/meta.llama-*',
          'arn:aws:bedrock:*::foundation-model/mistral.*',
          'arn:aws:bedrock:*::foundation-model/cohere.*',
          'arn:aws:bedrock:*::foundation-model/ai21.*',
          // Inference Profiles (Cross-region)
          `arn:aws:bedrock:*:${this.account}:inference-profile/*`,
          // Application Inference Profiles
          `arn:aws:bedrock:*:${this.account}:application-inference-profile/*`,
        ],
      }),
    );

    return lambdaFunction;
  }

  /**
   * Create Get Document Pages Lambda
   */
  private createGetDocumentPagesLambda(
    stage: string,
    indicesTable: dynamodb.ITable,
    documentsTable: dynamodb.ITable,
    segmentsTable: dynamodb.ITable,
    commonLayer?: lambda.ILayerVersion,
  ): lambda.Function {
    const getDocumentPagesConstruct = new StandardLambda(this, 'GetDocumentPages', {
      functionName: 'aws-idp-ai-get-document-pages',
      codePath: 'step-functions/get-document-pages',
      description: 'AWS IDP AI Get Document Pages Lambda Function',
      environment: {
        STAGE: stage,
        DOCUMENTS_TABLE_NAME: documentsTable.tableName,
        SEGMENTS_TABLE_NAME: segmentsTable.tableName,
        INDICES_TABLE_NAME: indicesTable.tableName,
      },
      deadLetterQueueEnabled: false,
      commonLayer: commonLayer,
      stage: stage,
    });

    const lambdaFunction = getDocumentPagesConstruct.function;

    // DynamoDB table access permission
    documentsTable.grantReadWriteData(lambdaFunction);
    segmentsTable.grantReadData(lambdaFunction);

    return lambdaFunction;
  }

  /**
   * Create BDA-based Document Processing Workflow
   */
  private createBdaBasedDocumentProcessingWorkflow(
    stage: string,
    bdaProcessorLambda: lambda.IFunction,
    bdaStatusCheckerLambda: lambda.IFunction,
    reactAnalysisLambda: lambda.IFunction,
    reactAnalysisFinalizerLambda: lambda.IFunction,
    documentSummarizerLambda: lambda.IFunction,
    getDocumentPagesLambda: lambda.IFunction,
  ): sfn.StateMachine {
    // 0. Define failure handling state
    const bdaProcessingFailed = new sfn.Fail(this, 'BdaProcessingFailed', {
      comment: 'BDA processing failed',
    });

    const bdaProcessingTimeout = new sfn.Fail(this, 'BdaProcessingTimeout', {
      comment: 'BDA processing timed out after maximum retries',
    });

    const documentIndexingFailed = new sfn.Fail(this, 'DocumentIndexingFailed', {
      comment: 'Document indexing failed',
    });

    // 1. Start BDA processing task
    const startBdaProcessingTask = new sfnTasks.LambdaInvoke(
      this,
      'StartBdaProcessing',
      {
        lambdaFunction: bdaProcessorLambda,
        comment: 'Start BDA processing for uploaded document',
        payload: sfn.TaskInput.fromObject({
          'index_id.$': '$.index_id',
          'document_id.$': '$.document_id',
          'file_name.$': '$.file_name',
          'file_type.$': '$.file_type',
          'processing_type.$': '$.processing_type',
          'file_uri.$': '$.file_uri',
          'stage.$': '$.stage',
        }),
      },
    );

    // 2. Check BDA status task
    const checkBdaStatusTask = new sfnTasks.LambdaInvoke(
      this,
      'CheckBdaStatus',
      {
        lambdaFunction: bdaStatusCheckerLambda,
        comment: 'Check BDA processing status',
        payload: sfn.TaskInput.fromObject({
          'index_id.$': '$.Payload.index_id',
          'document_id.$': '$.Payload.document_id',
          'bda_invocation_arn.$': '$.Payload.bda_invocation_arn',  // BDA task ARN
          'stage.$': '$.Payload.stage',
          'file_type.$': '$$.Execution.Input.file_type',
          'processing_type.$': '$$.Execution.Input.processing_type',
        }),
      },
    );

    // 3. Wait task (30 seconds)
    const waitForBdaCompletion = new sfn.Wait(this, 'WaitForBdaCompletion', {
      time: sfn.WaitTime.duration(cdk.Duration.seconds(30)),
      comment: 'Wait 30 seconds before checking BDA status again',
    });

    // 4. Document Indexer task (process BDA results, update Documents table, create Elements table data, and index to OpenSearch)
    const documentIndexerTask = new sfnTasks.LambdaInvoke(
      this,
      'DocumentIndexerTask',
      {
        lambdaFunction: this.documentIndexerLambda,
        comment: 'Process BDA results: update Documents table, create Elements table data, and index to OpenSearch',
        payload: sfn.TaskInput.fromObject({
          'document_id.$': '$.Payload.document_id',
          'index_id.$': '$.Payload.index_id',
          'bda_metadata_uri.$': '$.Payload.bda_metadata_uri',
          'bda_invocation_arn.$': '$.Payload.bda_invocation_arn',
        }),
        outputPath: '$.Payload',  // Extract only the Payload to simplify downstream access
      },
    ).addCatch(documentIndexingFailed, {
      errors: [sfn.Errors.ALL],
    });

    // 5. PDF Text Extractor task
    const pdfTextExtractorTask = new sfnTasks.LambdaInvoke(
      this,
      'PdfTextExtractorTask',
      {
        lambdaFunction: this.pdfTextExtractorLambda,
        comment: 'Extract text directly from PDF and index to OpenSearch',
        payload: sfn.TaskInput.fromObject({
          'document_id.$': '$$.Execution.Input.document_id',
          'index_id.$': '$$.Execution.Input.index_id',
          'file_uri.$': '$$.Execution.Input.file_uri',
          'media_type.$': '$.media_type',  // Media type from document-indexer output
        }),
        outputPath: '$.Payload',  // Extract only the Payload to simplify downstream access
      },
    );

    // 6. Get document segments task for parallel ReAct analysis
    const getDocumentPagesTask = new sfnTasks.LambdaInvoke(
      this,
      'GetDocumentPagesTask',
      {
        lambdaFunction: getDocumentPagesLambda,
        comment: 'Get all segments for the document to enable parallel processing',
        payload: sfn.TaskInput.fromObject({
          'index_id.$': '$$.Execution.Input.index_id',
          'document_id.$': '$$.Execution.Input.document_id',
          'media_type.$': '$.media_type',  // Media type from previous step
        }),
      },
    );

    // 7. Distributed Map for parallel ReAct analysis (handles unlimited segments)
    const stepFunctionsConfig = getStepFunctionsConfig();
    const reactAnalysisParallelMap = new sfn.DistributedMap(this, 'ReactAnalysisParallelMap', {
      comment: 'Process each segment in parallel using ReAct analysis with Distributed Map',
      maxConcurrency: stepFunctionsConfig.maxConcurrency,  // Use config value (30)
      itemsPath: '$.Payload.segment_ids',  // Use segment_ids array from GetDocumentPagesTask
      // Pass parent context to child executions
      itemSelector: {
        'segment.$': '$$.Map.Item.Value',  // Current segment item
        'document_id.$': '$.Payload.document_id',  // Parent document_id
        'index_id.$': '$$.Execution.Input.index_id',  // Parent index_id
        'file_uri.$': '$$.Execution.Input.file_uri',  // Parent file_uri
        'media_type.$': '$.Payload.media_type',  // Parent media_type
      },
      resultPath: sfn.JsonPath.DISCARD,  // Discard Map results to avoid size limit issues with large documents
      toleratedFailurePercentage: 5,  // Allow 5% of segments to fail without failing the entire workflow
      mapExecutionType: sfn.StateMachineType.STANDARD,  // Use STANDARD for child executions (supports longer running tasks)
    });

    // 8. Single segment ReAct analysis task with parameters
    const singlePageReactAnalysisTask = new sfnTasks.LambdaInvoke(
      this,
      'SinglePageReactAnalysis',
      {
        lambdaFunction: reactAnalysisLambda,
        comment: 'Perform ReAct analysis on a single segment',
        payload: sfn.TaskInput.fromObject({
          'document_id.$': '$.document_id',  // From itemSelector
          'index_id.$': '$.index_id',  // From itemSelector
          'file_uri.$': '$.file_uri',  // From itemSelector
          'media_type.$': '$.media_type',  // From itemSelector
          'segment_id.$': '$.segment.segment_id',  // From segment object in itemSelector
          'segment_index.$': '$.segment.segment_index',  // From segment object in itemSelector
        }),
        timeout: cdk.Duration.minutes(15), // Explicit timeout to match Lambda timeout
        // Only keep essential fields to reduce result size
        resultSelector: {
          'segment_id.$': '$.Payload.segment_id',
          'document_id.$': '$.Payload.document_id',
          'success.$': '$.Payload.success',
        },
      },
    );

    // 9. Single segment finalizer task (runs after AI analysis for each segment)
    const singleSegmentFinalizerTask = new sfnTasks.LambdaInvoke(
      this,
      'SingleSegmentFinalizerTask',
      {
        lambdaFunction: reactAnalysisFinalizerLambda,
        comment: 'Finalize single segment - combine content and create embedding for this segment',
        payload: sfn.TaskInput.fromObject({
          'index_id.$': '$$.Execution.Input.index_id',
          'document_id.$': '$.document_id',  // Get from previous step's result
          'segment_id.$': '$.segment_id',  // Get from previous step's result
        }),
        timeout: cdk.Duration.minutes(15), // Explicit timeout to match Lambda timeout
        // Only keep minimal result to avoid accumulating large data in Map state
        resultSelector: {
          'document_id.$': '$.Payload.document_id',
          'success.$': '$.Payload.success',
        },
      },
    );

    // Connect tasks in Distributed Map: AI analysis → segment finalizer
    const segmentChain = singlePageReactAnalysisTask.next(singleSegmentFinalizerTask);
    reactAnalysisParallelMap.itemProcessor(segmentChain);

    // 10. Document Summarizer task (final task after all segment processing)
    const documentSummarizerTask = new sfnTasks.LambdaInvoke(
      this,
      'DocumentSummarizerTask',
      {
        lambdaFunction: documentSummarizerLambda,
        comment: 'Generate document-level summary using LLM and update final document status',
        payload: sfn.TaskInput.fromObject({
          'index_id.$': '$$.Execution.Input.index_id',
          'document_id.$': '$$.Execution.Input.document_id',
        }),
      },
    );

    // 10. Success handling
    const processingSucceeded = new sfn.Succeed(this, 'ProcessingSucceeded', {
      comment: 'Document processing completed successfully',
    });

    // 10a. Media processing completed (for video/audio files)
    const mediaProcessingSucceeded = new sfn.Succeed(this, 'MediaProcessingSucceeded', {
      comment: 'Media file processing completed successfully (BDA metadata extracted)',
    });

    // 11. File type branching choice (after DocumentIndexer)
    const fileTypeBranchChoice = new sfn.Choice(this, 'FileTypeBranchChoice', {
      comment: 'Branch workflow based on file processing type after basic indexing',
    })
      .when(
        sfn.Condition.stringEquals('$$.Execution.Input.processing_type', 'video'),
        // 동영상: PDF 텍스트 추출 건너뛰고 바로 페이지 분석
        getDocumentPagesTask,
      )
      .when(
        sfn.Condition.stringEquals('$$.Execution.Input.processing_type', 'audio'),
        // 오디오: 미디어 처리 완료
        mediaProcessingSucceeded,
      )
      .when(
        sfn.Condition.and(
          sfn.Condition.stringEquals('$$.Execution.Input.processing_type', 'document'),
          sfn.Condition.stringEquals('$$.Execution.Input.file_type', 'application/pdf')
        ),
        // PDF 문서: PDF 텍스트 추출 → 페이지 분석
        pdfTextExtractorTask,
      )
      .otherwise(
        // 비PDF 문서: PDF 텍스트 추출 건너뛰고 바로 페이지 분석
        getDocumentPagesTask,
      );

    // 12. Analysis chain: segment processing → document summary
    const analysisChain = reactAnalysisParallelMap.next(documentSummarizerTask).next(processingSucceeded);
    
    // Connect the chains
    getDocumentPagesTask.next(analysisChain);
    pdfTextExtractorTask.next(getDocumentPagesTask);

    // 12. Choice condition definition (use BDA API official status values)
    const bdaStatusChoice = new sfn.Choice(this, 'BdaStatusChoice', {
      comment: 'Check BDA processing status',
    })
      .when(
        sfn.Condition.stringEquals('$.Payload.status', 'Success'),
        documentIndexerTask.next(fileTypeBranchChoice),
      )
      .when(
        sfn.Condition.or(
          sfn.Condition.stringEquals('$.Payload.status', 'ServiceError'),
          sfn.Condition.stringEquals('$.Payload.status', 'ClientError'),
        ),
        bdaProcessingFailed,
      )
      .when(
        sfn.Condition.or(
          sfn.Condition.stringEquals('$.Payload.status', 'Created'),
          sfn.Condition.stringEquals('$.Payload.status', 'InProgress'),
        ),
        waitForBdaCompletion.next(checkBdaStatusTask),
      )
      .otherwise(bdaProcessingTimeout);

    // 13. Define workflow
    const definition = startBdaProcessingTask
      .next(checkBdaStatusTask)
      .next(bdaStatusChoice);

    // 14. Create custom IAM role for Step Function
    const stateMachineRole = new iam.Role(this, 'DocumentProcessingStateMachineRole', {
      assumedBy: new iam.ServicePrincipal('states.amazonaws.com'),
      description: 'IAM role for AWS IDP AI Document Processing State Machine',
    });

    // 15. Explicit permission for specific Lambda functions called by Step Function
    const functionsToInvoke = [
      bdaProcessorLambda,
      bdaStatusCheckerLambda,
      this.documentIndexerLambda,
      this.pdfTextExtractorLambda,
      getDocumentPagesLambda,
      reactAnalysisLambda,
      reactAnalysisFinalizerLambda,
      documentSummarizerLambda,
    ];

    functionsToInvoke.forEach((fn) => {
      stateMachineRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['lambda:InvokeFunction'],
          resources: [fn.functionArn],
        }),
      );
    });

    // 16. Create State Machine
    const stateMachine = new sfn.StateMachine(
      this,
      'BdaDocumentProcessingWorkflow',
      {
        stateMachineName: `aws-idp-ai-bda-document-processing-${stage}`,
        definition,
        role: stateMachineRole,
        comment: 'BDA-based document processing workflow',
        timeout: cdk.Duration.minutes(this.props.stepfunctions?.documentProcessingTimeout || 60),
      },
    );

    return stateMachine;
  }

  /**
   * Create Step Function Trigger Lambda
   */
  private createStepFunctionTriggerLambda(
    stage: string,
    queue: sqs.Queue,
    sqsBatchSize?: number,
  ): lambda.Function {
    if (!this.documentProcessingWorkflow) {
      throw new Error(
        'documentProcessingWorkflow must be created before creating trigger lambda',
      );
    }

    const sqsConfig = getSqsConfig();
    const stepFunctionTriggerConstruct = new StandardLambda(this, 'StepFunctionTrigger', {
      functionName: 'aws-idp-ai-step-function-trigger',
      codePath: 'api/step-function-trigger',
      description: 'AWS IDP AI Step Function Trigger Lambda Function',
      environment: {
        STAGE: stage,
        STEP_FUNCTION_ARN: this.documentProcessingWorkflow.stateMachineArn,
      },
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      stage: stage,
      reservedConcurrency: sqsConfig.reservedConcurrency,
    });

    const triggerLambda = stepFunctionTriggerConstruct.function;

    // Connect SQS event source
    triggerLambda.addEventSource(
      new eventsources.SqsEventSource(queue, {
        batchSize: sqsBatchSize || 1,
        maxBatchingWindow: cdk.Duration.seconds(5),
      }),
    );

    // Grant Step Function execution permission
    this.documentProcessingWorkflow.grantStartExecution(triggerLambda);
    
    // Grant Step Function list executions permission (for checking running status)
    triggerLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'states:ListExecutions',
        ],
        resources: [this.documentProcessingWorkflow.stateMachineArn],
      }),
    );

    return triggerLambda;
  }

  /**
   * CDK Nag suppression settings
   */
  private addNagSuppressions(): void {
    // All Lambda functions IAM suppressions
    const allLambdas = [
      this.bdaProcessorLambda,
      this.bdaStatusCheckerLambda,
      this.pdfTextExtractorLambda,
      this.documentIndexerLambda,
      this.reactAnalysisLambda,
      this.reactAnalysisFinalizerLambda,
      this.documentSummarizerLambda,
      this.getDocumentPagesLambda,
      this.stepFunctionTriggerLambda,
    ].filter(Boolean);

    allLambdas.forEach((lambdaFunction) => {
      if (lambdaFunction) {
        NagSuppressions.addResourceSuppressions(
          lambdaFunction,
          [
            {
              id: 'AwsSolutions-IAM4',
              reason: [
                'AWS Lambda Basic Execution Role and VPC Access Execution Role are required for Lambda execution.',
                'These managed policies provide necessary CloudWatch logging and VPC networking permissions.',
                'Cannot be replaced with custom policies for basic Lambda execution requirements.',
              ].join(' '),
              appliesTo: [
                'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
                'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole',
              ],
            },
            {
              id: 'AwsSolutions-IAM5',
              reason: [
                'Wildcard permissions are required for dynamic resource access patterns.',
                'DynamoDB GSI access requires wildcard patterns as index names are dynamically generated.',
                'S3 object operations require wildcard access for document storage and retrieval.',
                'OpenSearch domain access requires wildcard for index operations.',
                'Bedrock model access requires wildcard for various AI models and versions.',
              ].join(' '),
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

        // Lambda Dead Letter Queue SSL requirement suppression
        if (lambdaFunction.deadLetterQueue) {
          NagSuppressions.addResourceSuppressions(
            lambdaFunction.deadLetterQueue,
            [
              {
                id: 'AwsSolutions-SQS4',
                reason: [
                  'Lambda Dead Letter Queue is used for internal AWS service communication only.',
                  'Queue is not exposed to external clients and handles failed Lambda invocations.',
                  'SSL/TLS encryption is handled at the AWS service level for internal communications.',
                ].join(' '),
              },
            ],
            true,
          );
        }
      }
    });

    // Step Functions suppressions
    if (this.documentProcessingWorkflow) {
      NagSuppressions.addResourceSuppressions(
        this.documentProcessingWorkflow,
        [
          {
            id: 'AwsSolutions-SF1',
            reason: [
              'CloudWatch Logs are not enabled for Step Functions due to high-volume processing.',
              'Application-level logging in Lambda functions provides sufficient monitoring.',
              'Step Functions execution history provides operational visibility.',
            ].join(' '),
          },
          {
            id: 'AwsSolutions-SF2',
            reason: [
              'X-Ray tracing is not enabled for Step Functions due to performance considerations.',
              'Lambda function tracing provides sufficient distributed tracing capabilities.',
              'CloudWatch metrics provide adequate monitoring for workflow execution.',
            ].join(' '),
          },
        ],
        true,
      );

      // Step Functions Role Lambda invocation permissions
      const stateMachineRole = this.node.findChild('DocumentProcessingStateMachineRole');
      if (stateMachineRole) {
        NagSuppressions.addResourceSuppressions(
          stateMachineRole,
          [
            {
              id: 'AwsSolutions-IAM5',
              reason: [
                'Step Functions requires wildcard permissions for Lambda function invocation.',
                'Lambda function ARNs include version and alias patterns requiring wildcard access.',
                'Each Lambda function requires specific ARN and version-based access permissions.',
              ].join(' '),
            },
          ],
          true,
        );
      }

      // Distributed Map Policy suppressions
      const distributedMapPolicy = this.node.tryFindChild('BdaDocumentProcessingWorkflow')?.node.tryFindChild('DistributedMapPolicy');
      if (distributedMapPolicy) {
        NagSuppressions.addResourceSuppressions(
          distributedMapPolicy,
          [
            {
              id: 'AwsSolutions-IAM5',
              reason: [
                'Distributed Map requires wildcard permissions for child executions.',
                'Child execution ARNs are dynamically generated and cannot be predicted.',
                'This is required for Distributed Map to create and manage child workflows.',
              ].join(' ')
            },
          ],
          true,
        );
      }
    }
  }
}
