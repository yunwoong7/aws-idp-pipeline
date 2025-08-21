import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';

export interface SecureDynamoDBTableProps {
  readonly tableName: string;
  readonly partitionKey: dynamodb.Attribute;
  readonly sortKey?: dynamodb.Attribute;
  readonly stream?: dynamodb.StreamViewType;
  readonly timeToLiveAttribute?: string;
  readonly billingMode?: dynamodb.BillingMode;
  readonly removalPolicy?: cdk.RemovalPolicy;
  readonly encryption?: dynamodb.TableEncryption;
  readonly pointInTimeRecovery?: boolean;
}

export class SecureDynamoDBTable extends Construct {
  public readonly table: dynamodb.Table;

  constructor(scope: Construct, id: string, props: SecureDynamoDBTableProps) {
    super(scope, id);

    // Get account, region, stage information from stack
    const stack = cdk.Stack.of(this);
    const account = stack.account;
    const region = stack.region;
    const stage = stack.stackName.split('-').pop() || 'dev';

    this.table = new dynamodb.Table(this, 'Table', {
      tableName: `${props.tableName}-${account}-${region}-${stage}`,
      partitionKey: props.partitionKey,
      sortKey: props.sortKey,
      stream: props.stream,
      timeToLiveAttribute: props.timeToLiveAttribute,
      
      // Standard security settings
      billingMode: props.billingMode || dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: props.encryption || dynamodb.TableEncryption.AWS_MANAGED,
      pointInTimeRecoverySpecification: { 
        pointInTimeRecoveryEnabled: props.pointInTimeRecovery ?? true 
      },
      removalPolicy: props.removalPolicy || cdk.RemovalPolicy.RETAIN,
    });
  }

  /**
   * Add GSI
   */
  public addGlobalSecondaryIndex(options: {
    indexName: string;
    partitionKey: dynamodb.Attribute;
    sortKey?: dynamodb.Attribute;
  }): void {
    this.table.addGlobalSecondaryIndex({
      indexName: options.indexName,
      partitionKey: options.partitionKey,
      sortKey: options.sortKey,
      projectionType: dynamodb.ProjectionType.ALL,
    });
  }

  /**
   * Add Local Secondary Index
   */
  public addLocalSecondaryIndex(props: {
    indexName: string;
    sortKey: dynamodb.Attribute;
    projectionType?: dynamodb.ProjectionType;
    nonKeyAttributes?: string[];
  }): void {
    this.table.addLocalSecondaryIndex({
      indexName: props.indexName,
      sortKey: props.sortKey,
      projectionType: props.projectionType || dynamodb.ProjectionType.ALL,
      nonKeyAttributes: props.nonKeyAttributes,
    });
  }

  /**
   * Grant read permission to Lambda function
   */
  public grantReadData(grantee: any): void {
    this.table.grantReadData(grantee);
  }

  /**
   * Grant write permission to Lambda function
   */
  public grantWriteData(grantee: any): void {
    this.table.grantWriteData(grantee);
  }

  /**
   * Grant read/write permission to Lambda function
   */
  public grantReadWriteData(grantee: any): void {
    this.table.grantReadWriteData(grantee);
  }

  /**
   * Grant stream read permission to Lambda function
   */
  public grantStreamRead(grantee: any): void {
    this.table.grantStreamRead(grantee);
  }

  /**
   * Return table name
   */
  public get tableName(): string {
    return this.table.tableName;
  }

  /**
   * Return table ARN
   */
  public get tableArn(): string {
    return this.table.tableArn;
  }

  /**
   * Return table stream ARN
   */
  public get tableStreamArn(): string | undefined {
    return this.table.tableStreamArn;
  }
} 