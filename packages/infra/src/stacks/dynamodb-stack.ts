import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';
import { SecureDynamoDBTable } from '../constructs/secure-dynamodb-table.js';

export interface DynamoDBStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly documentsTableName?: string;
  readonly pagesTableName?: string; // legacy
  readonly segmentsTableName?: string;
  readonly indicesTableName?: string;
  readonly vpc: ec2.Vpc;
}

/**
 * AWS IDP AI Analysis DynamoDB Stack
 *
 * Two table structures according to updated requirements:
 * 1. Documents Table: Document management
 * 2. Pages Table: Detailed information per page
 */
export class DynamoDBStack extends cdk.Stack {
  public readonly documentsTable: dynamodb.Table;
  public readonly segmentsTable: dynamodb.Table;
  public readonly indicesTable: dynamodb.Table;
  public readonly webSocketConnectionsTable: dynamodb.Table;
  public readonly usersTable: dynamodb.Table;
  private readonly vpcId: string;

  constructor(scope: Construct, id: string, props: DynamoDBStackProps) {
    super(scope, id, props);

    const stage = props.stage || 'prod';

    // VPC 정보를 props에서 직접 사용
    this.vpcId = props.vpc.vpcId;

    // Create Documents Table
    this.documentsTable = this.createDocumentsTable();

    // Create Indices Table (workspace)
    this.indicesTable = this.createIndicesTable();

    // Create Segments Table (replaces Pages)
    this.segmentsTable = this.createSegmentsTable();

    // Create WebSocket Connections Table
    this.webSocketConnectionsTable = this.createWebSocketConnectionsTable();

    // Create Users Table (for RBAC)
    this.usersTable = this.createUsersTable();

    // Create IAM policies for Lambda functions
    this.createDynamoDBAccessPolicies(stage);

    // CDK Nag 억제 설정 추가
    this.addNagSuppressions();

    // CloudFormation 출력
    this.createOutputs();

    // 디버깅용 로그
    console.log(
      `DynamoDB Stack - Documents Table: ${this.documentsTable.tableName}`,
    );
    console.log(`DynamoDB Stack - Segments Table: ${this.segmentsTable.tableName}`);
    console.log(`DynamoDB Stack - WebSocket Connections Table: ${this.webSocketConnectionsTable.tableName}`);
    console.log(`DynamoDB Stack - Using VPC ID: ${this.vpcId}`);
  }

  /**
   * Create document management table (based on PRD schema)
   * Fields: document_id(PK), created_at, file_name, file_size, file_type,
   *         processing_completed_at, project_id, file_uri, total_pages, updated_at,
   *         description, summary, representation, statistics
   */
  private createDocumentsTable(): dynamodb.Table {
    const documentsTableConstruct = new SecureDynamoDBTable(this, 'DocumentsTable', {
      tableName: 'aws-idp-ai-documents',
      partitionKey: { name: 'document_id', type: dynamodb.AttributeType.STRING },
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Force recreation if needed
    });

    // GSI: Query by index_id (workspace)
    documentsTableConstruct.addGlobalSecondaryIndex({
      indexName: 'IndexId',
      partitionKey: { name: 'index_id', type: dynamodb.AttributeType.STRING },
    });

    return documentsTableConstruct.table;
  }

  /**
   * Create Indices table (workspace root)
   * Fields: index_id(PK), index_name, description, owner_id, owner_name, created_at, updated_at
   */
  private createIndicesTable(): dynamodb.Table {
    const indicesTableConstruct = new SecureDynamoDBTable(this, 'IndicesTable', {
      tableName: 'aws-idp-ai-indices',
      partitionKey: { name: 'index_id', type: dynamodb.AttributeType.STRING },
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
    });

    // Optional: GSI for owner-based listing
    indicesTableConstruct.addGlobalSecondaryIndex({
      indexName: 'OwnerIndex',
      partitionKey: { name: 'owner_id', type: dynamodb.AttributeType.STRING },
      // sortKey: { name: 'created_at', type: dynamodb.AttributeType.STRING },
    });

    return indicesTableConstruct.table;
  }

  /**
   * Create Segments table (replaces Pages)
   * Fields: segment_id(PK), document_id(GSI PK), segment_index(GSI SK), segment_type, summary,
   *         start_timecode_smpte, end_timecode_smpte, image_uri, created_at, updated_at
   * Legacy compatibility fields maintained: page_id, page_index, page_status, bda_analysis_id
   */
  private createSegmentsTable(): dynamodb.Table {
    const segmentsTableConstruct = new SecureDynamoDBTable(this, 'SegmentsTable', {
      tableName: 'aws-idp-ai-segments',
      partitionKey: { name: 'segment_id', type: dynamodb.AttributeType.STRING },
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
    });

    // GSI for document-based queries
    segmentsTableConstruct.addGlobalSecondaryIndex({
      indexName: 'DocumentIdIndex',
      partitionKey: { name: 'document_id', type: dynamodb.AttributeType.STRING },
      // Keep legacy sort key name for compatibility
      sortKey: { name: 'segment_index', type: dynamodb.AttributeType.NUMBER },
    });

    // GSI for page status queries (PRD 필드 기준)
    segmentsTableConstruct.addGlobalSecondaryIndex({
      indexName: 'SegmentStatusIndex',
      partitionKey: {
        name: 'status',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'analysis_started_at',
        type: dynamodb.AttributeType.STRING,
      },
    });

    // GSI for BDA analysis queries (PRD 필드 기준)
    segmentsTableConstruct.addGlobalSecondaryIndex({
      indexName: 'BdaAnalysisIdIndex',
      partitionKey: { name: 'bda_analysis_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'segment_index', type: dynamodb.AttributeType.NUMBER },
    });

    return segmentsTableConstruct.table;
  }



  /**
   * Create Users table for RBAC
   * Fields: user_id(PK), email, name, role, permissions, status, created_at, updated_at, last_login_at
   */
  private createUsersTable(): dynamodb.Table {
    const usersTableConstruct = new SecureDynamoDBTable(this, 'UsersTable', {
      tableName: 'aws-idp-ai-users',
      partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
    });

    // GSI for email-based queries
    usersTableConstruct.addGlobalSecondaryIndex({
      indexName: 'EmailIndex',
      partitionKey: { name: 'email', type: dynamodb.AttributeType.STRING },
    });

    // GSI for role-based queries
    usersTableConstruct.addGlobalSecondaryIndex({
      indexName: 'RoleIndex',
      partitionKey: { name: 'role', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'created_at', type: dynamodb.AttributeType.STRING },
    });

    return usersTableConstruct.table;
  }

  /**
   * Create WebSocket connection management table
   * Fields: connection_id(PK), index_id, user_id, connected_at, ttl
   */
  private createWebSocketConnectionsTable(): dynamodb.Table {
    const webSocketConnectionsTableConstruct = new SecureDynamoDBTable(this, 'WebSocketConnectionsTable', {
      tableName: 'aws-idp-ai-websocket-connections',
      partitionKey: { name: 'connection_id', type: dynamodb.AttributeType.STRING },
      timeToLiveAttribute: 'ttl',
    });

    // GSI for index-based queries (인덱스별 연결된 클라이언트 조회)
    webSocketConnectionsTableConstruct.addGlobalSecondaryIndex({
      indexName: 'IndexIdIndex',
      partitionKey: { name: 'index_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'connected_at', type: dynamodb.AttributeType.STRING },
    });

    // GSI for user-based queries (사용자별 연결 조회)
    webSocketConnectionsTableConstruct.addGlobalSecondaryIndex({
      indexName: 'UserIndex',
      partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'connected_at', type: dynamodb.AttributeType.STRING },
    });

    return webSocketConnectionsTableConstruct.table;
  }

  /**
   * Create IAM policies for DynamoDB access
   */
  private createDynamoDBAccessPolicies(stage: string): void {
    // Read-only access policy
    const readOnlyPolicy = new iam.ManagedPolicy(
      this,
      'AwsIdpAiDynamoDBReadPolicy',
      {
        managedPolicyName: `aws-idp-ai-dynamodb-read-${stage}`,
        description: 'Read-only access to AWS IDP AI DynamoDB tables',
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: [
              'dynamodb:GetItem',
              'dynamodb:Query',
              'dynamodb:Scan',
              'dynamodb:BatchGetItem',
            ],
            resources: [
              this.documentsTable.tableArn,
              `${this.documentsTable.tableArn}/index/*`,
              this.segmentsTable.tableArn,
              `${this.segmentsTable.tableArn}/index/*`,
              this.indicesTable.tableArn,
              `${this.indicesTable.tableArn}/index/*`,
              this.webSocketConnectionsTable.tableArn,
              `${this.webSocketConnectionsTable.tableArn}/index/*`,
              this.usersTable.tableArn,
              `${this.usersTable.tableArn}/index/*`,
            ],
            conditions: {
              StringEquals: {
                'aws:SourceVpc': this.vpcId,
              },
            },
          }),
        ],
      },
    );

    // Read-write access policy
    const readWriteAccessPolicy = new iam.ManagedPolicy(
      this,
      'AwsIdpAiDynamoDBReadWritePolicy',
      {
        managedPolicyName: `aws-idp-ai-dynamodb-readwrite-${stage}`,
        description: 'Read and write access to AWS IDP AI DynamoDB tables',
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: [
              'dynamodb:GetItem',
              'dynamodb:PutItem',
              'dynamodb:UpdateItem',
              'dynamodb:DeleteItem',
              'dynamodb:Query',
              'dynamodb:Scan',
              'dynamodb:BatchGetItem',
              'dynamodb:BatchWriteItem',
              'dynamodb:ConditionCheckItem',
            ],
            resources: [
              this.documentsTable.tableArn,
              `${this.documentsTable.tableArn}/index/*`,
              this.segmentsTable.tableArn,
              `${this.segmentsTable.tableArn}/index/*`,
              this.indicesTable.tableArn,
              `${this.indicesTable.tableArn}/index/*`,
              this.webSocketConnectionsTable.tableArn,
              `${this.webSocketConnectionsTable.tableArn}/index/*`,
              this.usersTable.tableArn,
              `${this.usersTable.tableArn}/index/*`,
            ],
            conditions: {
              StringEquals: {
                'aws:SourceVpc': this.vpcId,
              },
            },
          }),
        ],
      },
    );

    // Stream processing policy
    const streamPolicy = new iam.ManagedPolicy(
      this,
      'AwsIdpAiDynamoDBStreamPolicy',
      {
        managedPolicyName: `aws-idp-ai-dynamodb-stream-${stage}`,
        description:
          'DynamoDB Streams access for AWS IDP AI Lambda functions',
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: [
              'dynamodb:DescribeStream',
              'dynamodb:GetRecords',
              'dynamodb:GetShardIterator',
              'dynamodb:ListStreams',
            ],
            resources: [
              this.documentsTable.tableStreamArn || '',
              this.segmentsTable.tableStreamArn || '',
              this.usersTable.tableStreamArn || '',
            ],
            conditions: {
              StringEquals: {
                'aws:SourceVpc': this.vpcId,
              },
            },
          }),
        ],
      },
    );

    // Suppress TypeScript unused variable warnings for policies that are created but not stored
    void readOnlyPolicy;
    void readWriteAccessPolicy; 
    void streamPolicy;
  }

  /**
   * Add CDK Nag suppression settings
   */
  private addNagSuppressions(): void {
    // DynamoDB IAM policies: GSI access wildcard permissions
    const policies = [
      this.node.findChild('AwsIdpAiDynamoDBReadPolicy'),
      this.node.findChild('AwsIdpAiDynamoDBReadWritePolicy'),
    ];

    policies.forEach((policy) => {
      if (policy) {
        NagSuppressions.addResourceSuppressions(policy, [
          {
            id: 'AwsSolutions-IAM5',
            reason: [
              'Wildcard permissions are required for DynamoDB Global Secondary Index (GSI) access.',
              'AWS DynamoDB service dynamically creates GSI ARNs with unpredictable hash suffixes.',
              'CDK automatically adds unique identifiers to GSI names during table creation.',
              'This is the official AWS-recommended pattern for DynamoDB IAM policies.',
              'Additional security controls: VPC condition (aws:SourceVpc) and specific DynamoDB actions only.',
            ].join(' '),
          },
        ]);
      }
    });
  }

  /**
   * Create CloudFormation outputs
   */
  private createOutputs(): void {

    // Documents Table Outputs
    new cdk.CfnOutput(this, 'DocumentsTableNameOutput', {
      value: this.documentsTable.tableName,
      description: 'AWS IDP AI documents table name',
    });

    new cdk.CfnOutput(this, 'DocumentsTableArnOutput', {
      value: this.documentsTable.tableArn,
      description: 'AWS IDP AI documents table ARN',
    });

    // Segments Table Outputs
    new cdk.CfnOutput(this, 'SegmentsTableNameOutput', {
      value: this.segmentsTable.tableName,
      description: 'AWS IDP AI segments table name',
    });

    new cdk.CfnOutput(this, 'SegmentsTableArnOutput', {
      value: this.segmentsTable.tableArn,
      description: 'AWS IDP AI segments table ARN',
    });

    // Indices Table Outputs
    new cdk.CfnOutput(this, 'IndicesTableNameOutput', {
      value: this.indicesTable.tableName,
      description: 'AWS IDP AI indices table name',
    });

    new cdk.CfnOutput(this, 'IndicesTableArnOutput', {
      value: this.indicesTable.tableArn,
      description: 'AWS IDP AI indices table ARN',
    });

    // WebSocket Connections Table Outputs
    new cdk.CfnOutput(this, 'WebSocketConnectionsTableNameOutput', {
      value: this.webSocketConnectionsTable.tableName,
      description: 'AWS IDP AI WebSocket connections table name',
    });

    new cdk.CfnOutput(this, 'WebSocketConnectionsTableArnOutput', {
      value: this.webSocketConnectionsTable.tableArn,
      description: 'AWS IDP AI WebSocket connections table ARN',
    });

    // Users Table Outputs
    new cdk.CfnOutput(this, 'UsersTableNameOutput', {
      value: this.usersTable.tableName,
      description: 'AWS IDP AI users table name',
    });

    new cdk.CfnOutput(this, 'UsersTableArnOutput', {
      value: this.usersTable.tableArn,
      description: 'AWS IDP AI users table ARN',
    });
  }

  /**
   * Helper method: Generate elements ID
   */
  public static generateElementsId(
    bdaAnalysisId: string,
    elementIndex: number,
  ): string {
    return `${bdaAnalysisId}#elem_${elementIndex.toString().padStart(4, '0')}`;
  }

  /**
   * Helper method: Parse elements ID
   */
  public static parseElementsId(elementsId: string): {
    bdaAnalysisId: string;
    elementIndex: number;
  } {
    const [bdaAnalysisId, elementPart] = elementsId.split('#');
    const elementIndex = parseInt(elementPart.replace('elem_', ''), 10);
    return { bdaAnalysisId, elementIndex };
  }
}
