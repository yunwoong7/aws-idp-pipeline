import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import * as toml from 'toml';
import Joi from 'joi';

// Replace __dirname with ES module
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface IConfig {
  app: {
    ns: string;
    stage: 'dev' | 'prod';
  };
  // security?: {
  //   whitelist?: string[];  // Removed - using Cognito authentication
  // };
  vpc?: {
    vpcId?: string;
    vpcCidr?: string;
    maxAzs?: number;
  };
  dynamodb?: {
    documentsTableName?: string;
    pagesTableName?: string; // legacy
    segmentsTableName?: string;
    indicesTableName?: string;
  };
  s3?: {
    documentsBucketName?: string;
  };
  opensearch?: {
    domainName?: string;
    indexName?: string;
    instanceType?: string;
    instanceCount?: number;
    dedicatedMasterEnabled?: boolean;
  };
  apigateway?: {
    throttleRateLimit?: number;
    throttleBurstLimit?: number;
  };
  bedrock?: {
    analysisAgentModelId?: string;
    analysisImageModelId?: string;
    analysisAgentMaxToken?: number;
    analysisImageMaxToken?: number;
    analysisVideoModelId?: string;
    analysisSummarizerModelId?: string;
    analysisSummarizerMaxToken?: number;
    pageSummaryModelId?: string;
    pageSummaryMaxToken?: number;
    rerankModelId?: string;
    embeddingsModelId?: string;
    embeddingsDimensions?: number;
    vectorWeight?: number;
    keywordWeight?: number;

    searchThresholdScore?: number;
  };
  search?: {
    hybridSearchSize?: number;
    rerankTopN?: number;
    maxSearchSize?: number;
    rerankScoreThreshold?: number;
  };
  analysis?: {
    previousAnalysisMaxCharacters?: number;
    maxIterations?: number;
  };
  lambda?: {
    timeout?: number;
    memorySize?: number;
    runtime?: string;
  };
  stepfunctions?: {
    documentProcessingTimeout?: number;
    maxConcurrency?: number;
  };
  sqs?: {
    sqsBatchSize?: number;
    reservedConcurrency?: number;
  };
}

// Check and load .toml file
const configPath = path.resolve(__dirname, '..', '.toml');
let cfg;

try {
  if (!fs.existsSync(configPath)) {
    console.log('No .toml file found, using dev.toml as default');
    const devConfigPath = path.resolve(__dirname, 'dev.toml');
    fs.copyFileSync(devConfigPath, configPath);
  }

  cfg = toml.parse(fs.readFileSync(configPath, 'utf-8'));
  console.log('✅ Loaded config:', JSON.stringify(cfg, null, 2));
} catch (error) {
  console.error('❌ Failed to load config:', error);
  throw error;
}

const schema = Joi.object({
  app: Joi.object({
    ns: Joi.string().required(),
    stage: Joi.string().valid('dev', 'prod').required(),
  }).required(),
  vpc: Joi.object({
    vpcId: Joi.string().optional(),
    vpcCidr: Joi.string().optional(),
    maxAzs: Joi.number().optional(),
  }).optional(),
  dynamodb: Joi.object({
    documentsTableName: Joi.string().optional(),
    pagesTableName: Joi.string().optional(),
    segmentsTableName: Joi.string().optional(),
    indicesTableName: Joi.string().optional(),
  }).optional(),
  s3: Joi.object({
    documentsBucketName: Joi.string().optional(),
  }).optional(),
  opensearch: Joi.object({
    domainName: Joi.string().optional(),
    indexName: Joi.string().optional(),
    instanceType: Joi.string().optional(),
    instanceCount: Joi.number().optional(),
    dedicatedMasterEnabled: Joi.boolean().optional(),
  }).optional(),
  apigateway: Joi.object({
    throttleRateLimit: Joi.number().optional(),
    throttleBurstLimit: Joi.number().optional(),
  }).optional(),
  bedrock: Joi.object({
    analysisAgentModelId: Joi.string().optional(),
    analysisImageModelId: Joi.string().optional(),
    analysisAgentMaxToken: Joi.number().optional(),
    analysisImageMaxToken: Joi.number().optional(),
    analysisVideoModelId: Joi.string().optional(),
    analysisSummarizerModelId: Joi.string().optional(),
    analysisSummarizerMaxToken: Joi.number().optional(),
    pageSummaryModelId: Joi.string().optional(),
    pageSummaryMaxToken: Joi.number().optional(),
    rerankModelId: Joi.string().optional(),
    embeddingsModelId: Joi.string().optional(),
    embeddingsDimensions: Joi.number().optional(),
    vectorWeight: Joi.number().optional(),
    keywordWeight: Joi.number().optional(),
    searchThresholdScore: Joi.number().optional(),
  }).optional(),
  search: Joi.object({
    hybridSearchSize: Joi.number().integer().min(1).max(100).optional(),
    rerankTopN: Joi.number().integer().min(1).max(20).optional(),
    maxSearchSize: Joi.number().integer().min(1).max(1000).optional(),
    rerankScoreThreshold: Joi.number().min(0).max(1).optional(),
  }).optional(),
  analysis: Joi.object({
    previousAnalysisMaxCharacters: Joi.number().optional(),
    maxIterations: Joi.number().optional(),
  }).optional(),
  lambda: Joi.object({
    timeout: Joi.number().optional(),
    memorySize: Joi.number().optional(),
    runtime: Joi.string().optional(),
  }).optional(),
  stepfunctions: Joi.object({
    documentProcessingTimeout: Joi.number().optional(),
    maxConcurrency: Joi.number().integer().min(1).optional(),
  }).optional(),
  sqs: Joi.object({
    sqsBatchSize: Joi.number().integer().min(1).max(10).optional(),
    reservedConcurrency: Joi.number().integer().min(1).optional(),
  }).optional(),
}).unknown();

const { error } = schema.validate(cfg);

if (error) {
  throw new Error(`❌ Config validation error: ${error.message}`);
}

export const Config: IConfig = {
  ...cfg,
  app: {
    ...cfg.app,
    ns: cfg.app.ns,
    stage: cfg.app.stage,
  },
};

// Functions to apply default values to settings
export const getFullStackName = (baseName: string): string => {
  return `${Config.app.ns.toLowerCase()}-${baseName}`;
};

export const getResourceName = (
  resourceType: string,
  suffix?: string,
): string => {
  const base = `${Config.app.ns.toLowerCase()}-${resourceType}`;
  return suffix ? `${base}-${suffix}` : base;
};

// Helper functions for common config access
export const getVpcConfig = () => ({
  vpcCidr: Config.vpc?.vpcCidr || '10.0.0.0/16',
  maxAzs: Config.vpc?.maxAzs || 3,
  ...Config.vpc,
});

export const getDynamoDbConfig = () => ({
  documentsTableName:
    Config.dynamodb?.documentsTableName || 'aws-idp-ai-documents',
  // Keep legacy default for backward compatibility but prefer segments
  pagesTableName: Config.dynamodb?.pagesTableName || 'aws-idp-ai-pages',
  segmentsTableName: Config.dynamodb?.segmentsTableName || 'aws-idp-ai-segments',
  indicesTableName: Config.dynamodb?.indicesTableName || 'aws-idp-ai-indices',
  ...Config.dynamodb,
});

export const getOpenSearchConfig = () => ({
  domainName: Config.opensearch?.domainName || 'aws-idp-ai-opensearch',
  indexName: Config.opensearch?.indexName || 'aws-idp-ai-analysis',
  instanceType: Config.opensearch?.instanceType || 't3.small.search',
  instanceCount: Config.opensearch?.instanceCount || 1,
  dedicatedMasterEnabled: Config.opensearch?.dedicatedMasterEnabled || false,
  ...Config.opensearch,
});

export const getApiGatewayConfig = () => ({
  throttleRateLimit: Config.apigateway?.throttleRateLimit || 1000,
  throttleBurstLimit: Config.apigateway?.throttleBurstLimit || 2000,
  ...Config.apigateway,
});

export const getLambdaConfig = () => ({
  timeout: Config.lambda?.timeout || 30,
  memorySize: Config.lambda?.memorySize || 512,
  runtime: Config.lambda?.runtime || 'python3.13',
  ...Config.lambda,
});

export const getAnalysisConfig = () => ({
  previousAnalysisMaxCharacters: Config.analysis?.previousAnalysisMaxCharacters || 100000,
  maxIterations: Config.analysis?.maxIterations || 10,
  ...Config.analysis,
});

export const getBedrockConfig = () => ({
  analysisAgentModelId: Config.bedrock?.analysisAgentModelId || 'us.anthropic.claude-3-7-sonnet-20250219-v1:0',
  analysisImageModelId: Config.bedrock?.analysisImageModelId || 'us.anthropic.claude-3-7-sonnet-20250219-v1:0',
  analysisAgentMaxToken: Config.bedrock?.analysisAgentMaxToken || 8192,
  analysisImageMaxToken: Config.bedrock?.analysisImageMaxToken || 8192,
  analysisVideoModelId: Config.bedrock?.analysisVideoModelId || 'us.twelvelabs.pegasus-1-2-v1:0',
  pageSummaryModelId: Config.bedrock?.pageSummaryModelId || 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
  pageSummaryMaxToken: Config.bedrock?.pageSummaryMaxToken || 8192,
  rerankModelId: Config.bedrock?.rerankModelId || 'cohere.rerank-v3-5:0',
  embeddingsModelId: Config.bedrock?.embeddingsModelId || 'amazon.titan-embed-text-v2:0',
  embeddingsDimensions: Config.bedrock?.embeddingsDimensions || 1024,
  vectorWeight: Config.bedrock?.vectorWeight || 0.6,
  keywordWeight: Config.bedrock?.keywordWeight || 0.4,
  searchThresholdScore: Config.bedrock?.searchThresholdScore || 0.4,
  ...Config.bedrock,
});

export const getSearchConfig = () => ({
  hybridSearchSize: Config.search?.hybridSearchSize || 25,
  rerankTopN: Config.search?.rerankTopN || 3,
  maxSearchSize: Config.search?.maxSearchSize || 100,
  rerankScoreThreshold: Config.search?.rerankScoreThreshold || 0.07,
  ...Config.search,
});

export const getSqsConfig = () => ({
  sqsBatchSize: Config.sqs?.sqsBatchSize || 1,
  reservedConcurrency: Config.sqs?.reservedConcurrency || 1,
  ...Config.sqs,
});

export const getStepFunctionsConfig = () => ({
  documentProcessingTimeout: Config.stepfunctions?.documentProcessingTimeout || 60,
  maxConcurrency: Config.stepfunctions?.maxConcurrency || 1,
  ...Config.stepfunctions,
});

// getSecurityConfig removed - IP whitelist replaced with Cognito authentication

// Helper to update config dynamically during deployment
export const updateConfig = (updates: Partial<IConfig>): void => {
  const configPath = path.resolve(__dirname, '..', '.toml');
  const currentConfig = toml.parse(fs.readFileSync(configPath, 'utf-8'));

  // Deep merge updates
  const mergedConfig = { ...currentConfig, ...updates };

  // Convert back to TOML format and write
  const tomlString = Object.entries(mergedConfig)
    .map(([section, values]) => {
      if (typeof values === 'object' && values !== null) {
        const sectionContent = Object.entries(values)
          .map(([key, value]) => {
            if (typeof value === 'string') {
              return `${key} = "${value}"`;
            }
            return `${key} = ${value}`;
          })
          .join('\n');
        return `[${section}]\n${sectionContent}`;
      }
      return '';
    })
    .join('\n\n');

  fs.writeFileSync(configPath, tomlString, 'utf-8');
  console.log('✅ Config updated:', configPath);
};
