import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export interface StandardLambdaProps {
  readonly functionName: string;
  readonly codePath: string;
  readonly description?: string;
  readonly handler?: string;
  readonly environment?: { [key: string]: string };
  readonly vpc?: ec2.IVpc;
  readonly commonLayer?: lambda.ILayerVersion;
  readonly layers?: lambda.ILayerVersion[];
  readonly timeout?: cdk.Duration;
  readonly memorySize?: number;
  readonly runtime?: lambda.Runtime;
  readonly deadLetterQueueEnabled?: boolean;
  readonly retryAttempts?: number;
  readonly stage?: string;
  readonly reservedConcurrency?: number;
}

export class StandardLambda extends Construct {
  public readonly function: lambda.Function;
  public readonly deadLetterQueue?: sqs.Queue;

  constructor(scope: Construct, id: string, props: StandardLambdaProps) {
    super(scope, id);

    const stage = props.stage || 'dev';

    // Create custom DLQ with enforceSSL if DLQ is enabled
    let deadLetterQueue: sqs.Queue | undefined;
    if (props.deadLetterQueueEnabled !== false) {
      deadLetterQueue = new sqs.Queue(this, 'DeadLetterQueue', {
        queueName: `${props.functionName}-dlq-${stage}`,
        encryption: sqs.QueueEncryption.SQS_MANAGED,
        enforceSSL: true,
        retentionPeriod: cdk.Duration.days(14),
      });
      this.deadLetterQueue = deadLetterQueue;
    }

    this.function = new lambda.Function(this, 'Function', {
      functionName: `${props.functionName}-${stage}`,
      runtime: props.runtime || lambda.Runtime.PYTHON_3_13,
      handler: props.handler || 'index.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, `../functions/${props.codePath}`)),
      description: props.description || `AWS IDP AI ${props.functionName} Lambda Function`,
      timeout: props.timeout || cdk.Duration.seconds(60),
      memorySize: props.memorySize || 512,
      environment: props.environment,
      layers: props.layers || (props.commonLayer ? [props.commonLayer] : undefined),
      vpc: props.vpc,
      vpcSubnets: props.vpc ? { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS } : undefined,
      deadLetterQueue: deadLetterQueue,
      retryAttempts: props.retryAttempts || 2,
      reservedConcurrentExecutions: props.reservedConcurrency,
    });
  }

  /**
   * Grant read permission to DynamoDB table
   */
  public grantDynamoDBRead(...tables: any[]): void {
    tables.forEach(table => {
      if (table && table.grantReadData) {
        table.grantReadData(this.function);
      }
    });
  }

  /**
   * Grant read/write permission to DynamoDB table
   */
  public grantDynamoDBReadWrite(...tables: any[]): void {
    tables.forEach(table => {
      if (table && table.grantReadWriteData) {
        table.grantReadWriteData(this.function);
      }
    });
  }

  /**
   * Grant read permission to S3 bucket
   */
  public grantS3Read(...buckets: any[]): void {
    buckets.forEach(bucket => {
      if (bucket && bucket.grantRead) {
        bucket.grantRead(this.function);
      }
    });
  }

  /**
   * Grant read/write permission to S3 bucket
   */
  public grantS3ReadWrite(...buckets: any[]): void {
    buckets.forEach(bucket => {
      if (bucket && bucket.grantReadWrite) {
        bucket.grantReadWrite(this.function);
      }
    });
  }
} 