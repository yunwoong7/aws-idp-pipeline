import * as cdk from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag';
import {
  Config,
  getFullStackName,
  getVpcConfig,
  getApiGatewayConfig,
  getOpenSearchConfig,
  getLambdaConfig,
  getAnalysisConfig,
  getSqsConfig,
  getStepFunctionsConfig,
} from '../config/loader.js';

// Transform lambda config to CDK format
const transformLambdaConfig = () => {
  const rawConfig = getLambdaConfig();
  return {  
    timeout: cdk.Duration.seconds(rawConfig.timeout),
    memorySize: rawConfig.memorySize,
    retryAttempts: 2,
  };
};

// Stack imports
import { VpcStack } from './stacks/vpc-stack.js';
import { LambdaLayerStack } from './stacks/lambda-layer-stack.js';
import { ApiGatewayStack } from './stacks/api-gateway-stack.js';
import { S3Stack } from './stacks/s3-stack.js';
import { DynamoDBStack } from './stacks/dynamodb-stack.js';
import { OpensearchStack } from './stacks/opensearch-stack.js';
import { DocumentManagementStack } from './stacks/document-management-stack.js';
import { WorkflowStack } from './stacks/workflow-stack.js';
import { WebSocketApiStack } from './stacks/websocket-api-stack.js';
import { DynamoDBStreamsStack } from './stacks/dynamodb-streams-stack.js';
import { IndicesManagementStack } from './stacks/indices-management-stack.js';
import { EcrStack } from './stacks/ecr-stack.js';
import { EcsStack } from './stacks/ecs-stack.js';

// Initialize app
const app = new cdk.App();
cdk.Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));

// Common environment configuration
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

console.log('🚀 AWS IDP AI Analysis - Infrastructure Deployment');
console.log('📝 Configuration:', JSON.stringify(Config, null, 2));

// =================================================================
// Tier 1: Foundation Stacks (no dependencies)
// =================================================================

// VPC Stack - All network-based infrastructure
const vpcConfig = getVpcConfig();
const vpcStack = new VpcStack(app, getFullStackName('vpc'), {
  vpcCidr: vpcConfig.vpcCidr,
  maxAzs: vpcConfig.maxAzs,
  existingVpcId: Config.vpc?.vpcId,
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics VPC Infrastructure Stack',
});

// Lambda Layer Stack - Common library layer
const lambdaLayerStack = new LambdaLayerStack(app, getFullStackName('lambda-layer'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics Lambda Layer Stack',
  stage: Config.app.stage,
});


// API Gateway Stack - Basic HTTP API Gateway
const apiGatewayConfig = getApiGatewayConfig();
const apiGatewayStack = new ApiGatewayStack(app, getFullStackName('api-gateway'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics API Gateway Stack',
  stage: Config.app.stage,
  throttleSettings: {
    rateLimit: apiGatewayConfig.throttleRateLimit,
    burstLimit: apiGatewayConfig.throttleBurstLimit,
  },
});

// =================================================================
// Tier 2: Core Data Services (depends on Tier 1)
// =================================================================

// S3 Stack - S3 bucket for document storage
const s3Stack = new S3Stack(app, getFullStackName('s3'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics S3 Storage Stack',
  stage: Config.app.stage,
  documentsBucketName: Config.s3?.documentsBucketName,
});

// DynamoDB Stack - DynamoDB tables
const dynamoDBStack = new DynamoDBStack(app, getFullStackName('dynamodb'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics DynamoDB Stack',
  stage: Config.app.stage,
  vpc: vpcStack.vpc,
  documentsTableName: Config.dynamodb?.documentsTableName,
  pagesTableName: Config.dynamodb?.pagesTableName,
  segmentsTableName: Config.dynamodb?.segmentsTableName,
  indicesTableName: Config.dynamodb?.indicesTableName,
});

// OpenSearch Stack - OpenSearch domain (pass VPC object directly)
const opensearchConfig = getOpenSearchConfig();
const opensearchStack = new OpensearchStack(app, getFullStackName('opensearch'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics OpenSearch Domain Stack',
  vpc: vpcStack.vpc,
  domainName: opensearchConfig.domainName,
  indexName: opensearchConfig.indexName,
  instanceType: opensearchConfig.instanceType,
  instanceCount: opensearchConfig.instanceCount,
  dedicatedMasterEnabled: opensearchConfig.dedicatedMasterEnabled,
});

// =================================================================
// Tier 3: Core Application Logic (depends on Tier 1, 2)
// =================================================================

// Indices (Workspace) Management Stack - CRUD for indices
new IndicesManagementStack(app, getFullStackName('indices-management'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Indices (Workspace) Management Stack',
  stage: Config.app.stage,
  httpApi: apiGatewayStack.httpApi,
  vpc: vpcStack.vpc,
  indicesTable: dynamoDBStack.indicesTable,
  documentsTable: dynamoDBStack.documentsTable,
  segmentsTable: dynamoDBStack.segmentsTable,
  documentsBucket: s3Stack.documentsBucket,
  opensearchEndpoint: opensearchStack.domainEndpoint,
  opensearchIndex: opensearchConfig.indexName,
  opensearchDomain: opensearchStack.domain,
  commonLayer: lambdaLayerStack.commonLayer,
  lambdaConfig: transformLambdaConfig(),
});

// Document Management Stack - Document management API
const documentManagementStack = new DocumentManagementStack(app, getFullStackName('document-management'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics Document Management API Stack',
  stage: Config.app.stage,
  httpApi: apiGatewayStack.httpApi,
  documentsBucket: s3Stack.documentsBucket,
  indicesTable: dynamoDBStack.indicesTable,
  documentsTable: dynamoDBStack.documentsTable,
  segmentsTable: dynamoDBStack.segmentsTable,
  opensearchEndpoint: opensearchStack.domainEndpoint,
  opensearchIndex: opensearchConfig.indexName,
  opensearchDomain: opensearchStack.domain,
  vpc: vpcStack.vpc,
  commonLayer: lambdaLayerStack.commonLayer,
  lambdaConfig: transformLambdaConfig(),
});

// Workflow Stack - Step Functions workflow and related Lambda functions
const analysisConfig = getAnalysisConfig();
const sqsConfig = getSqsConfig();
const stepFunctionsConfig = getStepFunctionsConfig();
new WorkflowStack(app, getFullStackName('workflow'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics Workflow Stack',
  stage: Config.app.stage,
  bedrock: Config.bedrock,
  analysis: analysisConfig,
  stepfunctions: stepFunctionsConfig,
  indicesTable: dynamoDBStack.indicesTable,
  documentsTable: dynamoDBStack.documentsTable,
  segmentsTable: dynamoDBStack.segmentsTable,
  documentsBucket: s3Stack.documentsBucket,
  vpc: vpcStack.vpc,
  opensearchDomain: opensearchStack.domain,
  opensearchEndpoint: opensearchStack.domainEndpoint,
  documentProcessingQueue: documentManagementStack.documentProcessingQueue,
  databaseServiceLambda: undefined,
  commonLayer: lambdaLayerStack.commonLayer,
  lambdaConfig: transformLambdaConfig(),
  sqsBatchSize: sqsConfig.sqsBatchSize,
});

// =================================================================
// Tier 4: Real-time & Eventing Stacks (depends on Tier 1, 2, 3)
// =================================================================

// WebSocket API Stack - WebSocket API Gateway and connection management Lambda functions
const webSocketApiStack = new WebSocketApiStack(app, getFullStackName('websocket-api'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics WebSocket API Stack',
  stage: Config.app.stage,
  vpc: vpcStack.vpc,
  webSocketConnectionsTableName: dynamoDBStack.webSocketConnectionsTable.tableName,
  webSocketConnectionsTableArn: dynamoDBStack.webSocketConnectionsTable.tableArn,
});

// DynamoDB Streams Stack - Documents table status changes only
new DynamoDBStreamsStack(app, getFullStackName('dynamodb-streams'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI Analytics DynamoDB Streams Stack',
  stage: Config.app.stage,
  vpc: vpcStack.vpc,
  documentsTable: dynamoDBStack.documentsTable,
  webSocketConnectionsTableName: dynamoDBStack.webSocketConnectionsTable.tableName,
  webSocketConnectionsTableArn: dynamoDBStack.webSocketConnectionsTable.tableArn,
  webSocketApiId: webSocketApiStack.webSocketApi.apiId,
});

// =================================================================
// Tier 5: Container Services (ECR/ECS) - Deployed separately
// =================================================================

// ECR Stack - Container registries
const ecrStack = new EcrStack(app, getFullStackName('ecr'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI ECR Container Registries Stack',
  stage: Config.app.stage,
});

// ECS Stack - Container services
new EcsStack(app, getFullStackName('ecs'), {
  env,
  crossRegionReferences: true,
  description: 'AWS IDP AI ECS Container Services Stack',
  stage: Config.app.stage,
  vpc: vpcStack.vpc,
  backendRepository: ecrStack.backendRepository,
  frontendRepository: ecrStack.frontendRepository,
  apiGatewayUrl: apiGatewayStack.apiUrl,
});

app.synth();
