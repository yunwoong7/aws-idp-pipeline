import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { StandardLambda } from '../constructs/standard-lambda.js';
import { ApiGatewayRoutes } from '../constructs/api-gateway-routes.js';

export interface UserManagementStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly httpApi?: apigw.IHttpApi;
  readonly usersTable?: dynamodb.ITable;
  readonly vpc?: ec2.IVpc;
  readonly commonLayer?: lambda.ILayerVersion;
  readonly cognitoUserPoolDomain?: string;
  readonly cognitoClientId?: string;
  readonly lambdaConfig?: {
    timeout?: cdk.Duration;
    memorySize?: number;
    retryAttempts?: number;
  };
}

/**
 * AWS IDP AI Analysis - User Management Stack
 *
 * Stack providing user management API for RBAC:
 * - Get current user permissions
 * - List all users (admin only)
 * - Update user permissions (admin only)
 * - Update user status (admin only)
 */
export class UserManagementStack extends cdk.Stack {
  public readonly userManagementLambda: lambda.Function;

  constructor(
    scope: Construct,
    id: string,
    props: UserManagementStackProps,
  ) {
    super(scope, id, props);

    const stage = props.stage || 'prod';

    // Get required resources from props
    const httpApi = props.httpApi;
    const usersTable = props.usersTable;

    if (!httpApi || !usersTable) {
      throw new Error(
        'HttpApi and usersTable must be provided in props',
      );
    }

    // Create User Management Lambda function
    const userManagementLambdaConstruct = new StandardLambda(this, 'UserManagement', {
      functionName: 'aws-idp-ai-user-management',
      codePath: 'api/user-management',
      description: 'AWS IDP AI User Management API Lambda Function',
      environment: {
        USERS_TABLE_NAME: usersTable.tableName,
        STAGE: props.stage || 'dev',
        AUTH_DISABLED: 'false',
        COGNITO_USER_POOL_DOMAIN: props.cognitoUserPoolDomain || '',
        COGNITO_CLIENT_ID: props.cognitoClientId || '',
      },
      deadLetterQueueEnabled: false,
      vpc: props.vpc,
      commonLayer: props.commonLayer,
      timeout: cdk.Duration.seconds(30),
      memorySize: props.lambdaConfig?.memorySize || 512,
      stage: stage,
    });

    this.userManagementLambda = userManagementLambdaConstruct.function;

    // Grant permissions to Lambda
    this.grantPermissions(usersTable);

    // Add API Gateway routes
    this.addApiRoutes(httpApi);

    // CDK Nag suppression settings
    this.addNagSuppressions();
  }

  /**
   * Grant permissions
   */
  private grantPermissions(usersTable: dynamodb.ITable): void {
    // Grant permissions to DynamoDB users table
    usersTable.grantReadWriteData(this.userManagementLambda);
  }

  /**
   * Add API Gateway routes
   */
  private addApiRoutes(httpApi: apigw.IHttpApi): void {
    // Define User Management API Routes
    const userRoutes = [
      // Authentication routes
      {
        path: '/api/auth/user',
        methods: [apigw.HttpMethod.GET],
      },
      {
        path: '/api/auth/logout',
        methods: [apigw.HttpMethod.POST],
      },
      // GET /api/users/me - Get current user permissions
      {
        path: '/api/users/me',
        methods: [apigw.HttpMethod.GET],
      },
      // GET /api/users - List all users
      {
        path: '/api/users',
        methods: [apigw.HttpMethod.GET],
      },
      // PUT /api/users/{user_id}/permissions - Update user permissions
      {
        path: '/api/users/{user_id}/permissions',
        methods: [apigw.HttpMethod.PUT],
      },
      // POST /api/users/{user_id}/status - Update user status
      {
        path: '/api/users/{user_id}/status',
        methods: [apigw.HttpMethod.POST],
      },
    ];

    // Add routes using ApiGatewayRoutes construct
    new ApiGatewayRoutes(this, 'UserManagementRoutes', {
      httpApi,
      integrationLambda: this.userManagementLambda,
      routePaths: userRoutes,
      constructIdPrefix: 'UserRoute',
      authSuppressionReason: [
        'User management endpoints are publicly accessible for development.',
        'Frontend handles permission checks to show/hide admin features.',
        'Production deployment will implement proper authentication using AWS Cognito User Pools or IAM authorization.',
      ].join(' '),
    });
  }

  /**
   * CDK Nag suppression settings
   */
  private addNagSuppressions(): void {
    // Suppressions for Lambda function service role
    NagSuppressions.addResourceSuppressions(
      this.userManagementLambda,
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
    if (this.userManagementLambda.role) {
      NagSuppressions.addResourceSuppressions(
        this.userManagementLambda.role,
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
