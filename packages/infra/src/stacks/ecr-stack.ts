import * as cdk from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface EcrStackProps extends cdk.StackProps {
  stage: string;
}

export class EcrStack extends cdk.Stack {
  public readonly backendRepository: ecr.Repository;
  public readonly frontendRepository: ecr.Repository;

  constructor(scope: Construct, id: string, props: EcrStackProps) {
    super(scope, id, props);

    const { stage } = props;

    // Backend ECR Repository
    this.backendRepository = new ecr.Repository(this, 'BackendRepository', {
      repositoryName: `aws-idp-backend-${stage}`,
      imageScanOnPush: true,
      imageTagMutability: ecr.TagMutability.MUTABLE,
      lifecycleRules: [
        {
          description: 'Keep only the latest 10 images',
          maxImageCount: 10,
        },
      ],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Frontend ECR Repository
    this.frontendRepository = new ecr.Repository(this, 'FrontendRepository', {
      repositoryName: `aws-idp-frontend-${stage}`,
      imageScanOnPush: true,
      imageTagMutability: ecr.TagMutability.MUTABLE,
      lifecycleRules: [
        {
          description: 'Keep only the latest 10 images',
          maxImageCount: 10,
        },
      ],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });


    // CloudFormation Outputs
    new cdk.CfnOutput(this, 'BackendRepositoryUri', {
      value: this.backendRepository.repositoryUri,
      description: 'Backend ECR Repository URI',
      exportName: `${id}-BackendRepositoryUri`,
    });

    new cdk.CfnOutput(this, 'FrontendRepositoryUri', {
      value: this.frontendRepository.repositoryUri,
      description: 'Frontend ECR Repository URI',
      exportName: `${id}-FrontendRepositoryUri`,
    });

    // CDK-NAG 억제
    NagSuppressions.addResourceSuppressions(
      this.backendRepository,
      [
        {
          id: 'AwsSolutions-ECR2',
          reason: 'ECR repository encryption with KMS is not required for this demo application',
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      this.frontendRepository,
      [
        {
          id: 'AwsSolutions-ECR2',
          reason: 'ECR repository encryption with KMS is not required for this demo application',
        },
      ]
    );

    // Tag resources
    cdk.Tags.of(this).add('Project', 'aws-idp-pipeline');
    cdk.Tags.of(this).add('Environment', stage);
  }
}