import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambdaEventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface DynamoDBStreamsStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly documentsTable: dynamodb.Table;
  readonly webSocketConnectionsTableName: string;
  readonly webSocketConnectionsTableArn: string;
  readonly webSocketApiId: string;
  readonly vpc: ec2.Vpc;
  readonly stepFunctionArn?: string;
}

/**
 * AWS IDP AI Analysis DynamoDB Streams Stack
 * 
 * DynamoDB Streams를 통해 Documents 테이블의 status 변경사항을 감지하고
 * WebSocket을 통해 실시간으로 프론트엔드에 알림을 전송합니다.
 */
export class DynamoDBStreamsStack extends cdk.Stack {
  public readonly documentsStreamHandler: lambda.Function;
  
  // Add reference fields
  // private readonly webSocketConnectionsTableArn: string;

  constructor(scope: Construct, id: string, props: DynamoDBStreamsStackProps) {
    super(scope, id, props);

    const stage = props.stage || 'prod';
    
    // Initialize reference fields
    // this.webSocketConnectionsTableArn = props.webSocketConnectionsTableArn;

    // Use VPC directly from props
    const vpcId = props.vpc.vpcId;

    // Create Lambda Execution Role
    const streamHandlerExecutionRole = this.createStreamHandlerExecutionRole(stage, vpcId, props);

    // Create Lambda function
    this.documentsStreamHandler = this.createDocumentsStreamHandler(stage, streamHandlerExecutionRole, props);

    // DynamoDB Streams event source connection
    this.connectEventSources(props);


    // CloudFormation Outputs
    this.createOutputs();

    // CDK Nag suppression settings
    this.addNagSuppressions(streamHandlerExecutionRole);

    console.log(`DynamoDB Streams Stack - Documents Handler: ${this.documentsStreamHandler.functionArn}`);
  }

  /**
   * Create Stream Handler Lambda execution role
   */
  private createStreamHandlerExecutionRole(
    stage: string,
    vpcId: string,
    props: DynamoDBStreamsStackProps
  ): iam.Role {
    const role = new iam.Role(this, 'StreamHandlerExecutionRole', {
      roleName: `aws-idp-ai-streams-lambda-role-${stage}`,
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'Execution role for AWS IDP AI DynamoDB Streams Lambda functions',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
      ],
    });

    // DynamoDB Streams read permission
    const streamArns: string[] = [];
    if (props.documentsTable.tableStreamArn) {
      streamArns.push(props.documentsTable.tableStreamArn);
    }

    role.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'dynamodb:DescribeStream',
          'dynamodb:GetRecords',
          'dynamodb:GetShardIterator',
          'dynamodb:ListStreams',
        ],
        resources: streamArns,
      })
    );

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

    // API Gateway Management API permission (for WebSocket message sending)
    role.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['execute-api:ManageConnections'],
        resources: ['*'],
      })
    );

    // Step Functions permissions for sequential processing
    if (props.stepFunctionArn) {
      role.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'states:ListExecutions',
            'states:StartExecution',
          ],
          resources: [props.stepFunctionArn],
        })
      );
    }

    // Documents table access for querying uploaded documents
    role.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'dynamodb:Query',
          'dynamodb:Scan',
        ],
        resources: [props.documentsTable.tableArn],
      })
    );

    return role;
  }

  /**
   * Create Documents Stream Handler function
   */
  private createDocumentsStreamHandler(
    stage: string,
    executionRole: iam.Role,
    props: DynamoDBStreamsStackProps
  ): lambda.Function {
    return new lambda.Function(this, 'DocumentsStreamHandler', {
      functionName: `aws-idp-ai-documents-stream-handler-${stage}`,
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'handlers.documents_handler.handler',
      code: lambda.Code.fromAsset('src/functions/api/dynamodb-streams-handler'),
      role: executionRole,
      timeout: cdk.Duration.minutes(5),
      environment: {
        WEBSOCKET_CONNECTIONS_TABLE: props.webSocketConnectionsTableName,
        WEBSOCKET_API_ID: props.webSocketApiId,
        WEBSOCKET_STAGE: stage,
        DOCUMENTS_TABLE_NAME: props.documentsTable.tableName,
        STEP_FUNCTION_ARN: props.stepFunctionArn || '',
        STAGE: stage,
      },
      logRetention: logs.RetentionDays.ONE_WEEK,
      description: 'Documents table DynamoDB Streams handler for status updates',
    });
  }

  /**
  * DynamoDB Streams event source connection
   */
  private connectEventSources(props: DynamoDBStreamsStackProps): void {
    // Documents table stream connection
    if (props.documentsTable.tableStreamArn) {
      this.documentsStreamHandler.addEventSource(
        new lambdaEventSources.DynamoEventSource(props.documentsTable, {
          startingPosition: lambda.StartingPosition.LATEST,
          batchSize: 10,
          maxBatchingWindow: cdk.Duration.seconds(5),
          retryAttempts: 3,
          parallelizationFactor: 2,
        })
      );
    }
  }


  /**
   * CloudFormation Outputs
   */
  private createOutputs(): void {
    new cdk.CfnOutput(this, 'DocumentsStreamHandlerArnOutput', {
      value: this.documentsStreamHandler.functionArn,
      description: 'AWS IDP AI Documents stream handler function ARN',
    });
  }

  /**
   * CDK Nag suppression settings
   */
  private addNagSuppressions(executionRole: iam.Role): void {
    // IAM Role suppressions
    NagSuppressions.addResourceSuppressions(executionRole, [
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
          'Wildcard permissions are necessary for DynamoDB Streams and WebSocket API operations.',
          'API Gateway Management API requires wildcard resource access for connection management.',
          'DynamoDB GSI access requires wildcard as index ARNs are dynamically generated by CDK.',
        ].join(' '),
      },
    ]);

    // Execution role default policy suppressions
    if (executionRole.node.findChild('DefaultPolicy')) {
      NagSuppressions.addResourceSuppressions(
        executionRole.node.findChild('DefaultPolicy'),
        [
          {
            id: 'AwsSolutions-IAM5',
            reason: [
              'Wildcard permissions are necessary for DynamoDB GSI access.',
              'WebSocket connections table GSI access requires wildcard as index ARNs are dynamically generated by CDK.',
            ].join(' '),
          },
        ]
      );
    }

    // CDK auto-generated LogRetention function suppressions
    NagSuppressions.addStackSuppressions(this, [
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
        appliesTo: ['Resource::*'],
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