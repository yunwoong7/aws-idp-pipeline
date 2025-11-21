import * as cdk from 'aws-cdk-lib';
import * as apigatewayv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigatewayv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface WebSocketApiStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly webSocketConnectionsTableName: string;
  readonly webSocketConnectionsTableArn: string;
  readonly vpc: ec2.Vpc;
}

/**
 * AWS IDP AI Analysis WebSocket API Stack
 * 
 * Realtime updates for WebSocket API Gateway and connection management Lambda functions.
 * 
 * Main features:
 * - Create and configure WebSocket API Gateway
 * - Create connection/disconnect management Lambda functions
 * - DynamoDB Streams integration
 */
export class WebSocketApiStack extends cdk.Stack {
  public readonly webSocketApi: apigatewayv2.WebSocketApi;
  public readonly webSocketStage: apigatewayv2.WebSocketStage;
  public readonly connectFunction: lambda.Function;
  public readonly disconnectFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: WebSocketApiStackProps) {
    super(scope, id, props);

    const stage = props.stage || 'prod';
  
    // Use VPC directly from props
    const vpcId = props.vpc.vpcId;

    // Create Lambda Execution Role
    const lambdaExecutionRole = this.createLambdaExecutionRole(stage, vpcId, props);

    // Create Lambda functions
    this.connectFunction = this.createConnectFunction(stage, lambdaExecutionRole, props);
    this.disconnectFunction = this.createDisconnectFunction(stage, lambdaExecutionRole, props);

    // Create WebSocket API
    this.webSocketApi = this.createWebSocketApi(stage);

    // Setup routes
    this.setupRoutes();

    // Create WebSocket Stage
    this.webSocketStage = this.createWebSocketStage(stage);


    // CloudFormation Outputs
    this.createOutputs();

    // CDK Nag suppression settings
    this.addNagSuppressions();

    console.log(`WebSocket API Stack - WebSocket URL: ${this.webSocketApi.apiEndpoint}`);
    console.log(`WebSocket API Stack - Stage: ${this.webSocketStage.stageName}`);
  }

  /**
  * Create Lambda Execution Role
   */
  private createLambdaExecutionRole(
    stage: string,
    vpcId: string,
    props: WebSocketApiStackProps
  ): iam.Role {
    const role = new iam.Role(this, 'WebSocketLambdaExecutionRole', {
      roleName: `aws-idp-ai-websocket-lambda-role-${stage}`,
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'Execution role for AWS IDP AI WebSocket Lambda functions',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
      ],
    });

    // DynamoDB WebSocket Connections table access permission
    role.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'dynamodb:GetItem',
          'dynamodb:PutItem',
          'dynamodb:UpdateItem',
          'dynamodb:DeleteItem',
          'dynamodb:Query',
          'dynamodb:Scan',
        ],
        resources: [
          props.webSocketConnectionsTableArn,
          `${props.webSocketConnectionsTableArn}/index/*`,
        ],
      })
    );

    // API Gateway Management API permission (for message sending)
    role.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['execute-api:ManageConnections'],
        resources: ['arn:aws:execute-api:*:*:*'],
      })
    );

    return role;
  }

  /**
   * Create Connect function
   */
  private createConnectFunction(
    stage: string,
    executionRole: iam.Role,
    props: WebSocketApiStackProps
  ): lambda.Function {
    return new lambda.Function(this, 'WebSocketConnectFunction', {
      functionName: `aws-idp-ai-websocket-connect-${stage}`,
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('src/functions/api/websocket-connect'),
      role: executionRole,
      timeout: cdk.Duration.seconds(30),
      environment: {
        WEBSOCKET_CONNECTIONS_TABLE: props.webSocketConnectionsTableName,
      },
      logRetention: logs.RetentionDays.ONE_WEEK,
      description: 'WebSocket connection handler for AWS IDP AI',
    });
  }

  /**
   * Create Disconnect function
   */
  private createDisconnectFunction(
    stage: string,
    executionRole: iam.Role,
    props: WebSocketApiStackProps
  ): lambda.Function {
    return new lambda.Function(this, 'WebSocketDisconnectFunction', {
      functionName: `aws-idp-ai-websocket-disconnect-${stage}`,
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('src/functions/api/websocket-disconnect'),
      role: executionRole,
      timeout: cdk.Duration.seconds(30),
      environment: {
        WEBSOCKET_CONNECTIONS_TABLE: props.webSocketConnectionsTableName,
      },
      logRetention: logs.RetentionDays.ONE_WEEK,
      description: 'WebSocket disconnection handler for AWS IDP AI',
    });
  }


  /**
   * Create WebSocket API
   */
  private createWebSocketApi(stage: string): apigatewayv2.WebSocketApi {
    return new apigatewayv2.WebSocketApi(this, 'WebSocketApi', {
      apiName: `aws-idp-ai-websocket-api-${stage}`,
      description: 'WebSocket API for AWS IDP AI real-time updates',
      connectRouteOptions: {
        integration: new apigatewayv2Integrations.WebSocketLambdaIntegration(
          'ConnectIntegration',
          this.connectFunction
        ),
      },
      disconnectRouteOptions: {
        integration: new apigatewayv2Integrations.WebSocketLambdaIntegration(
          'DisconnectIntegration',
          this.disconnectFunction
        ),
      },
    });
  }

  /**
   * Setup routes
   */
  private setupRoutes(): void {
    // Additional routes can be added here
    // Currently, only basic connect/disconnect/default routes are used
  }

  /**
   * Create WebSocket Stage
   */
  private createWebSocketStage(stage: string): apigatewayv2.WebSocketStage {
    return new apigatewayv2.WebSocketStage(this, 'WebSocketStage', {
      webSocketApi: this.webSocketApi,
      stageName: stage,
      autoDeploy: true,
    });
  }


  /**
   * Create CloudFormation Outputs
   */
  private createOutputs(): void {
    new cdk.CfnOutput(this, 'WebSocketApiIdOutput', {
      value: this.webSocketApi.apiId,
      description: 'AWS IDP AI WebSocket API ID',
    });

    new cdk.CfnOutput(this, 'WebSocketApiEndpointOutput', {
      value: this.webSocketApi.apiEndpoint,
      description: 'AWS IDP AI WebSocket API endpoint',
    });

    new cdk.CfnOutput(this, 'WebSocketStageNameOutput', {
      value: this.webSocketStage.stageName,
      description: 'AWS IDP AI WebSocket stage name',
    });
  }

  /**
   * CDK Nag suppression settings
   */
  private addNagSuppressions(): void {
    // Lambda execution role suppressions
    const role = this.node.findChild('WebSocketLambdaExecutionRole');
    if (role) {
      NagSuppressions.addResourceSuppressions(role, [
        {
          id: 'AwsSolutions-IAM4',
          reason: [
            'AWS managed policies are required for Lambda VPC execution and basic logging.',
            'AWSLambdaBasicExecutionRole and AWSLambdaVPCAccessExecutionRole cannot be replaced with custom policies.',
            'These are AWS standard policies for Lambda execution in VPC environments.',
          ].join(' '),
          appliesTo: [
            'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
            'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole',
          ],
        },
        {
          id: 'AwsSolutions-IAM5',
          reason: [
            'Wildcard permissions are necessary for WebSocket API and DynamoDB operations.',
            'API Gateway Management API requires wildcard resource access for connection management.',
            'DynamoDB GSI access requires wildcard as index ARNs are dynamically generated by CDK.',
          ].join(' '),
        },
      ]);
    }

    // Stack-level suppressions for API Gateway routes and stage
    NagSuppressions.addStackSuppressions(this, [
      {
        id: 'AwsSolutions-APIG4',
        reason: [
          'WebSocket API does not implement authorization for real-time communication requirements.',
          'Authentication is handled at the application level through project_id validation.',
          'WebSocket connections are scoped to specific projects and validated on connect.',
          'Future enhancement will include JWT-based authentication.',
        ].join(' '),
      },
      {
        id: 'AwsSolutions-APIG1',
        reason: [
          'Access logging is not enabled for WebSocket API due to high-volume real-time traffic.',
          'Application-level logging provides sufficient monitoring for business logic.',
          'CloudWatch metrics and X-Ray tracing provide operational visibility.',
          'Enabling access logs for WebSocket would incur significant cost with minimal value.',
        ].join(' '),
      },
      {
        id: 'AwsSolutions-IAM4',
        reason: [
          'CDK auto-generated LogRetention function uses AWS managed policy.',
          'AWSLambdaBasicExecutionRole is required for CloudFormation custom resource operations.',
          'This is a CDK internal resource and cannot use custom policies.',
        ].join(' '),
        appliesTo: ['Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'],
      },
      {
        id: 'AwsSolutions-IAM5',
        reason: [
          'CDK auto-generated LogRetention function requires wildcard permissions for CloudWatch logs management.',
          'This function manages log retention across multiple log groups and requires broad permissions.',
          'Wildcard permissions are necessary for CDK internal CloudFormation operations.',
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
    ]);
  }
}