import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as oss from 'aws-cdk-lib/aws-opensearchservice';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';
import { StandardLambda } from '../constructs/standard-lambda.js';
import { ApiGatewayRoutes } from '../constructs/api-gateway-routes.js';

export interface IndicesManagementStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly vpc?: ec2.IVpc;
  readonly httpApi?: apigw.IHttpApi;
  readonly indicesTable?: dynamodb.ITable;
  readonly documentsTable?: dynamodb.ITable;
  readonly segmentsTable?: dynamodb.ITable;
  readonly documentsBucket?: s3.IBucket;
  readonly opensearchDomain?: oss.IDomain;
  readonly opensearchEndpoint?: string;
  readonly opensearchIndex?: string;
  readonly commonLayer?: lambda.ILayerVersion;
  readonly lambdaConfig?: {
    timeout?: cdk.Duration;
    memorySize?: number;
    retryAttempts?: number;
  };
}

/**
 * AWS IDP AI - Indices (Workspace) Management Stack
 *
 * API Endpoints:
 * - GET    /api/indices
 * - POST   /api/indices
 * - GET    /api/indices/{index_id}
 * - PUT    /api/indices/{index_id}
 * - DELETE /api/indices/{index_id}
 */
export class IndicesManagementStack extends cdk.Stack {
  public readonly indicesManagementLambda: lambda.Function;

  constructor(scope: Construct, id: string, props: IndicesManagementStackProps) {
    super(scope, id, props);

    const stage = props.stage || 'dev';

    const httpApi = props.httpApi;
    const indicesTable = props.indicesTable;
    const documentsTable = props.documentsTable;
    const segmentsTable = props.segmentsTable;
    const documentsBucket = props.documentsBucket;
    const vpc = props.vpc;
    const commonLayer = props.commonLayer;

    if (!httpApi || !indicesTable) {
      throw new Error('HttpApi and indicesTable must be provided');
    }

    // Lambda
    const lambdaConstruct = new StandardLambda(this, 'IndicesManagement', {
      functionName: 'aws-idp-ai-indices-management',
      codePath: 'api/indices-management',
      description: 'AWS IDP AI Indices (Workspace) Management API Lambda',
      timeout: props.lambdaConfig?.timeout || cdk.Duration.seconds(60),
      memorySize: props.lambdaConfig?.memorySize || 512,
      retryAttempts: props.lambdaConfig?.retryAttempts || 2,
      deadLetterQueueEnabled: false,
      vpc,
      commonLayer,
      stage,
      environment: {
        STAGE: stage,
        INDICES_TABLE_NAME: indicesTable.tableName,
        DOCUMENTS_TABLE_NAME: documentsTable?.tableName || '',
        SEGMENTS_TABLE_NAME: segmentsTable?.tableName || '',
        DOCUMENTS_BUCKET_NAME: documentsBucket?.bucketName || '',
        OPENSEARCH_ENDPOINT: props.opensearchEndpoint || '',
        OPENSEARCH_INDEX_NAME: props.opensearchIndex || 'aws-idp-ai-analysis',
        OPENSEARCH_REGION: cdk.Stack.of(this).region,
      },
    });

    this.indicesManagementLambda = lambdaConstruct.function;

    // Permissions
    lambdaConstruct.grantDynamoDBReadWrite(indicesTable);
    if (documentsTable) lambdaConstruct.grantDynamoDBReadWrite(documentsTable);
    if (segmentsTable) lambdaConstruct.grantDynamoDBReadWrite(segmentsTable);
    if (documentsBucket) {
      documentsBucket.grantReadWrite(this.indicesManagementLambda);
      // Ensure ListBucket for prefix listing/deletion
      this.indicesManagementLambda.addToRolePolicy(new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['s3:ListBucket'],
        resources: [documentsBucket.bucketArn],
      }));
    }

    // Grant OpenSearch permissions
    if (props.opensearchDomain) {
      props.opensearchDomain.grantReadWrite(this.indicesManagementLambda);
      
      // Grant HTTP access permission to OpenSearch domain
      this.indicesManagementLambda.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'es:ESHttpPost',
            'es:ESHttpPut',
            'es:ESHttpGet',
            'es:ESHttpDelete',
            'es:ESHttpHead',
          ],
          resources: [`${props.opensearchDomain.domainArn}/*`],
        }),
      );
    }

    // Routes
    const routes = [
      { path: '/api/indices', methods: [apigw.HttpMethod.GET] },
      { path: '/api/indices', methods: [apigw.HttpMethod.POST] },
      { path: '/api/indices/{index_id}', methods: [apigw.HttpMethod.GET] },
      { path: '/api/indices/{index_id}', methods: [apigw.HttpMethod.PUT] },
      { path: '/api/indices/{index_id}', methods: [apigw.HttpMethod.DELETE] },
      // Deep delete all resources related to an index
      { path: '/api/indices/{index_id}/deep-delete', methods: [apigw.HttpMethod.POST] },
    ];

    new ApiGatewayRoutes(this, 'IndicesRoutes', {
      httpApi,
      integrationLambda: this.indicesManagementLambda,
      routePaths: routes,
      constructIdPrefix: 'IndicesRoute',
      authSuppressionReason: [
        'Development environment unauthenticated routes. Production will add proper auth.',
      ].join(' '),
    });

    // CDK-Nag suppressions
    this.addNagSuppressions();
  }

  private addNagSuppressions(): void {
    // Suppressions for Lambda function service role
    NagSuppressions.addResourceSuppressions(
      this.indicesManagementLambda,
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
    if (this.indicesManagementLambda.role) {
      NagSuppressions.addResourceSuppressions(
        this.indicesManagementLambda.role,
        [
          {
            id: 'AwsSolutions-IAM5',
            reason: [
              'Wildcard permissions are required for dynamic resource access patterns.',
              'DynamoDB GSI access requires wildcard patterns as index names are dynamically generated.',
            ].join(' '),
          },
        ],
        true,
      );
    }
  }
}


