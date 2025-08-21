import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export interface LambdaLayerStackProps extends cdk.StackProps {
  readonly stage?: string;
}

/**
 * AWS IDP AI Analysis - Lambda Layer Stack
 *
 * Common Lambda Layer stack (direct reference method):
 * - Integrated services for DynamoDB, OpenSearch, S3
 * - ActivityRecorder activity logging service
 * - Common utility functions
 * - AWS client factory
 * - Does not use CloudFormation Export/Import
 */
export class LambdaLayerStack extends cdk.Stack {
  public readonly commonLayer: lambda.LayerVersion;

  constructor(
    scope: Construct,
    id: string,
    props: LambdaLayerStackProps,
  ) {
    super(scope, id, props);

    const stage = props.stage || 'prod';
    
    // Create common Lambda Layer (using pre-built ZIP file)
    // Remove timestamp for stable version management
    this.commonLayer = new lambda.LayerVersion(
      this,
      'BlueprintAiCommonLayer',
      {
        layerVersionName: `aws-idp-ai-common-${stage}`,
        code: lambda.Code.fromAsset(
          path.join(__dirname, '../lambda_layer/custom_layer_common.zip'),
        ),
        compatibleRuntimes: [
          lambda.Runtime.PYTHON_3_13,
        ],
        description: 'AWS IDP AI Common Layer - boto3, opensearch-py, pillow, PyMuPDF, PyPDF2',
        compatibleArchitectures: [lambda.Architecture.X86_64],
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      },
    );
  }
}