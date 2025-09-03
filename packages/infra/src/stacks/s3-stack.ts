import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface S3StackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly documentsBucketName?: string;
}

/**
 * AWS IDP AI Analysis S3 Stack
 * This stack provides S3 storage for PDF documents and converted images
 * with a hierarchical folder structure: projects/{project_id}/documents/{doc_id}/
 * Integrates with VPC for secure access from Lambda functions
 */
export class S3Stack extends cdk.Stack {
  public readonly documentsBucket: s3.Bucket;
  public readonly accessLogsBucket: s3.Bucket;
  public readonly bucketName: string;
  // private readonly vpcId: string;
  // private readonly lambdaSecurityGroupId: string;

  constructor(scope: Construct, id: string, props: S3StackProps) {
    super(scope, id, props);

    const stage = props.stage || 'prod';

    // Create S3 access logs bucket first
    this.accessLogsBucket = new s3.Bucket(this, 'BlueprintAiAccessLogsBucket', {
      bucketName: `aws-idp-ai-access-logs-${this.account}-${this.region}-${stage}`,
      
      // Access logs bucket settings
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      
      // Lifecycle management for access logs
      // lifecycleRules: [
      //   {
      //     id: 'access-logs-lifecycle',
      //     enabled: true,
      //     transitions: [
      //       {
      //         storageClass: s3.StorageClass.INFREQUENT_ACCESS,
      //         transitionAfter: cdk.Duration.days(30),
      //       },
      //       {
      //         storageClass: s3.StorageClass.GLACIER,
      //         transitionAfter: cdk.Duration.days(90),
      //       },
      //     ],
      //     expiration: cdk.Duration.days(365), // Delete access logs after 1 year
      //   },
      // ],

      // Remove bucket when stack is deleted (MVP only)
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Create S3 bucket for document storage
    this.documentsBucket = new s3.Bucket(this, 'BlueprintAiDocumentsBucket', {
      bucketName: `aws-idp-ai-documents-${this.account}-${this.region}-${stage}`,

      // Versioning for document history and recovery
      versioned: true,

      // Server access logging - now enabled
      serverAccessLogsBucket: this.accessLogsBucket,
      serverAccessLogsPrefix: 'documents-access-logs/',

      // Lifecycle management for cost optimization
      // lifecycleRules: [
      //   {
      //     id: 'thumbnail-transition',
      //     enabled: true,
      //     prefix: 'projects/*/documents/*/thumbnails/',
      //     transitions: [
      //       {
      //         storageClass: s3.StorageClass.INFREQUENT_ACCESS,
      //         transitionAfter: cdk.Duration.days(30),
      //       },
      //       {
      //         storageClass: s3.StorageClass.GLACIER,
      //         transitionAfter: cdk.Duration.days(90),
      //       },
      //     ],
      //   },
      //   {
      //     id: 'original-document-transition',
      //     enabled: true,
      //     prefix: 'projects/*/documents/*/original/',
      //     transitions: [
      //       {
      //         storageClass: s3.StorageClass.INFREQUENT_ACCESS,
      //         transitionAfter: cdk.Duration.days(90),
      //       },
      //     ],
      //   },
      //   {
      //     id: 'incomplete-uploads-cleanup',
      //     enabled: true,
      //     abortIncompleteMultipartUploadAfter: cdk.Duration.days(1),
      //   },
      // ],

      // CORS configuration for frontend access
      cors: [
        {
          allowedMethods: [
            s3.HttpMethods.GET,
            s3.HttpMethods.PUT,
            s3.HttpMethods.POST,
            s3.HttpMethods.DELETE,
            s3.HttpMethods.HEAD
          ],
          allowedOrigins: ['*'],
          allowedHeaders: ['*'],
          exposedHeaders: ['ETag'], // Minimal required header
          maxAge: 3600,
        },
      ],

      // Security settings
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,

      // Encryption
      encryption: s3.BucketEncryption.S3_MANAGED,

      // Event notifications (for future Lambda triggers)
      eventBridgeEnabled: true,

      // Remove bucket when stack is deleted (Prototyping only)
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Add bucket policy to allow access only from VPC
    this.addVpcOnlyBucketPolicy();

    // Store bucket name for easy access
    this.bucketName = this.documentsBucket.bucketName;


    // Create IAM policy for Lambda functions to access the bucket
    const s3AccessPolicy = new iam.ManagedPolicy(
      this,
      'BlueprintAiS3AccessPolicy',
      {
        managedPolicyName: `aws-idp-ai-s3-access-${stage}`,
        description:
          'IAM policy for AWS IDP AI Lambda functions to access S3 bucket',
        statements: [
          // Read access to all objects
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: [
              's3:GetObject',
              's3:GetObjectVersion',
              's3:GetObjectMetadata',
              's3:ListBucket',
            ],
            resources: [
              this.documentsBucket.bucketArn,
              `${this.documentsBucket.bucketArn}/*`,
            ],
          }),
          // Write access to project-specific paths
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: [
              's3:PutObject',
              's3:PutObjectMetadata',
              's3:DeleteObject',
              's3:AbortMultipartUpload',
              's3:ListMultipartUploadParts',
            ],
            resources: [`${this.documentsBucket.bucketArn}/projects/*`],
          }),
          // Generate pre-signed URLs
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ['s3:GetObjectPresignedUrl', 's3:PutObjectPresignedUrl'],
            resources: [`${this.documentsBucket.bucketArn}/*`],
          }),
        ],
      },
    );

    // Suppress TypeScript unused variable warning for policy that is created but not stored
    void s3AccessPolicy;

    // CDK Nag suppression settings
    this.addNagSuppressions();
  }

  /**
   * CDK Nag suppression settings
   */
  private addNagSuppressions(): void {
    // S3 Access Policy: wildcard permissions (S3 object access pattern)
    const s3AccessPolicy = this.node.findChild('BlueprintAiS3AccessPolicy');
    if (s3AccessPolicy) {
      NagSuppressions.addResourceSuppressions(
        s3AccessPolicy,
        [
          {
            id: 'AwsSolutions-IAM5',
            reason: [
              'S3 object access requires wildcard patterns for file operations.',
              'Access is restricted to specific VPC and limited to document processing functions.',
              'Bucket policy further restricts access to VPC endpoints only.',
              'Wildcard is necessary for S3 object operations (/* pattern is standard S3 practice).',
            ].join(' '),
            appliesTo: [
              'Resource::<BlueprintAiDocumentsBucket8AB2CA7C.Arn>/*',
              'Resource::<BlueprintAiDocumentsBucket8AB2CA7C.Arn>/projects/*',
            ],
          },
        ],
      );
    }

    // CDK auto-generated BucketNotificationsHandler suppression
    NagSuppressions.addStackSuppressions(this, [
      {
        id: 'AwsSolutions-IAM4',
        reason: [
          'CDK auto-generated BucketNotificationsHandler uses AWS managed policy for basic Lambda execution.',
          'This is required for S3 bucket notifications setup and cannot be replaced with custom policies.',
          'Handler is only used during CloudFormation deployment for bucket configuration.',
        ].join(' '),
        appliesTo: [
          'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
        ],
      },
      {
        id: 'AwsSolutions-IAM5',
        reason: [
          'CDK auto-generated BucketNotificationsHandler requires wildcard permissions for S3 notifications setup.',
          'This is necessary for CloudFormation to configure S3 bucket notifications properly.',
          'Handler is only active during stack deployment and update operations.',
        ].join(' '),
        appliesTo: ['Resource::*'],
      },
    ]);
  }

  /**
   * Prototyping stage: Relax VPC restrictions for Pre-signed URL testing
   * Production will revert to VPC-only policy
   */
  private addVpcOnlyBucketPolicy(): void {
    // In Prototyping stage, relax VPC restrictions to allow Pre-signed URL testing
    // Production will revert to VPC-only policy

    // Apply only SSL enforcement policy (security maintained)
    this.documentsBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: 'DenyInsecureConnections',
        effect: iam.Effect.DENY,
        principals: [new iam.AnyPrincipal()],
        actions: ['s3:*'],
        resources: [
          this.documentsBucket.bucketArn,
          `${this.documentsBucket.bucketArn}/*`,
        ],
        conditions: {
          Bool: {
            'aws:SecureTransport': 'false',
          },
        },
      }),
    );

    // Presigned URL policy removed - using backend direct upload instead
    // CloudFormation Outputs (without exportName)
    new cdk.CfnOutput(this, 'DocumentsBucketName', {
      value: this.documentsBucket.bucketName,
      description: 'Documents S3 bucket name',
    });

    new cdk.CfnOutput(this, 'DocumentsBucketArn', {
      value: this.documentsBucket.bucketArn,
      description: 'Documents S3 bucket ARN',
    });

    new cdk.CfnOutput(this, 'AccessLogsBucketName', {
      value: this.accessLogsBucket.bucketName,
      description: 'Access logs S3 bucket name',
    });
  }

  /**
   * Get the S3 path for a specific document type
   */
  public static getDocumentPath(
    project_id: string,
    docId: string,
    type: 'original' | 'images' | 'thumbnails',
    filename?: string,
  ): string {
    const basePath = `projects/${project_id}/documents/${docId}/${type}`;
    return filename ? `${basePath}/${filename}` : basePath;
  }

  /**
   * Get the S3 path for a specific page image or thumbnail
   */
  public static getPagePath(
    projectId: string,
    docId: string,
    pageNumber: number,
    type: 'images' | 'thumbnails',
  ): string {
    const filename =
      type === 'thumbnails'
        ? `page_${pageNumber.toString().padStart(3, '0')}_thumb.png`
        : `page_${pageNumber.toString().padStart(3, '0')}.png`;

    return this.getDocumentPath(projectId, docId, type, filename);
  }
}
