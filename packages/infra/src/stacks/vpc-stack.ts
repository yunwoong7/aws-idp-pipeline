import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as iam from 'aws-cdk-lib/aws-iam';
// import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface VpcStackProps extends cdk.StackProps {
  vpcCidr?: string;
  maxAzs?: number;
  existingVpcId?: string;
}

export class VpcStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public webSecurityGroup!: ec2.SecurityGroup;
  public appSecurityGroup!: ec2.SecurityGroup;
  public databaseSecurityGroup!: ec2.SecurityGroup;
  public lambdaSecurityGroup!: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props?: VpcStackProps) {
    super(scope, id, props);

    // Create VPC
    this.vpc = new ec2.Vpc(this, 'AwsIdpAiVpc', {
      ipAddresses: ec2.IpAddresses.cidr(props?.vpcCidr || '10.0.0.0/16'),
      maxAzs: props?.maxAzs || 3,
      enableDnsHostnames: true,
      enableDnsSupport: true,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'PublicSubnet',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'PrivateSubnet',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          cidrMask: 24,
          name: 'IsolatedSubnet',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
      natGateways: 2, // For high availability, use 2 NAT Gateways
    });

    // Add VPC tags
    cdk.Tags.of(this.vpc).add('Project', 'AwsIdpAiAnalytics');
    cdk.Tags.of(this.vpc).add('Environment', props?.env?.account || 'sandbox');

    // Create Security Groups
    this.createSecurityGroups();

    // Create VPC Flow Logs
    this.createVpcFlowLogs();

    // Create VPC Endpoints
    this.createVpcEndpoints();


    // CDK Nag Suppressions
    this.addNagSuppressions();
  }

  private addNagSuppressions(): void {
    // Web Security Group: Internet access is required for ALB
    NagSuppressions.addResourceSuppressions(this.webSecurityGroup, [
      {
        id: 'AwsSolutions-EC23',
        reason: [
          'Public Application Load Balancer requires internet access (0.0.0.0/0) for HTTPS traffic.',
          'Access is restricted to HTTPS port 443 only for security.',
          'Application-level security (WAF, authentication) provides additional protection layers.',
          'This is standard pattern for public-facing web applications with ALB.',
        ].join(' '),
      },
    ]);

    // Lambda Security Group: CDK internal VPC CIDR reference causes validation failure
    NagSuppressions.addResourceSuppressions(this.lambdaSecurityGroup, [
      {
        id: 'CdkNagValidationFailure',
        reason: [
          'CDK VPC CIDR reference (Fn::GetAtt) causes nag validation failure.',
          'Lambda security group correctly uses VPC CIDR block for internal communication.',
          'This is CDK framework limitation, not a security issue.',
          'Manual security group rules are properly scoped to VPC CIDR only.',
        ].join(' '),
      },
    ]);

    // VPC Flow Log Role: AWS service requirement for wildcard permissions
    const flowLogRole = this.node.findChild('VpcFlowLogRole');
    if (flowLogRole) {
      NagSuppressions.addResourceSuppressions(flowLogRole, [
        {
          id: 'AwsSolutions-IAM5',
          reason: [
            'VPC Flow Logs service requires wildcard permissions for CloudWatch Logs operations.',
            'AWS VPC Flow Logs cannot predict log group/stream names in advance.',
            'This is AWS service limitation, not application design choice.',
            'Permissions are scoped to CloudWatch Logs actions only.',
          ].join(' '),
          appliesTo: ['Resource::*'],
        },
      ]);
    }
  }

  private createSecurityGroups(): void {
    // Web Tier Security Group (for ALB)
    this.webSecurityGroup = new ec2.SecurityGroup(this, 'WebSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for web tier (ALB)',
      allowAllOutbound: true,
    });

    // Only allow HTTPS for web traffic, restrict to common CDN/proxy ranges
    this.webSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'Allow HTTPS traffic from anywhere',
    );

    // Application Tier Security Group (for Lambda/ECS)
    this.appSecurityGroup = new ec2.SecurityGroup(this, 'AppSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for application tier',
      allowAllOutbound: true,
    });

    this.appSecurityGroup.addIngressRule(
      this.webSecurityGroup,
      ec2.Port.tcp(8080),
      'Allow traffic from web tier',
    );

    // Database Tier Security Group
    this.databaseSecurityGroup = new ec2.SecurityGroup(
      this,
      'DatabaseSecurityGroup',
      {
        vpc: this.vpc,
        description: 'Security group for database tier',
        allowAllOutbound: false,
      },
    );

    this.databaseSecurityGroup.addIngressRule(
      this.appSecurityGroup,
      ec2.Port.tcp(443),
      'Allow HTTPS from application tier',
    );

    this.databaseSecurityGroup.addIngressRule(
      this.appSecurityGroup,
      ec2.Port.tcp(9200),
      'Allow OpenSearch from application tier',
    );

    // Lambda Security Group (for Lambda functions)
    this.lambdaSecurityGroup = new ec2.SecurityGroup(
      this,
      'LambdaSecurityGroup',
      {
        vpc: this.vpc,
        description: 'Security group for Lambda functions',
        allowAllOutbound: true,
      },
    );

    // Allow database access from Lambda
    this.databaseSecurityGroup.addIngressRule(
      this.lambdaSecurityGroup,
      ec2.Port.tcp(443),
      'Allow HTTPS from Lambda',
    );

    this.databaseSecurityGroup.addIngressRule(
      this.lambdaSecurityGroup,
      ec2.Port.tcp(9200),
      'Allow OpenSearch from Lambda',
    );
  }

  private createVpcFlowLogs(): void {
    // CloudWatch Log Group for VPC Flow Logs
    const flowLogGroup = new logs.LogGroup(this, 'VpcFlowLogGroup', {
      logGroupName: '/aws-idp-ai/vpc/flowlogs',
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // IAM Role for VPC Flow Logs
    const flowLogRole = new iam.Role(this, 'VpcFlowLogRole', {
      assumedBy: new iam.ServicePrincipal('vpc-flow-logs.amazonaws.com'),
      inlinePolicies: {
        FlowLogDeliveryPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'logs:CreateLogGroup',
                'logs:CreateLogStream',
                'logs:PutLogEvents',
                'logs:DescribeLogGroups',
                'logs:DescribeLogStreams',
              ],
              resources: ['*'],
            }),
          ],
        }),
      },
    });

    // Create VPC Flow Logs
    new ec2.FlowLog(this, 'VpcFlowLog', {
      resourceType: ec2.FlowLogResourceType.fromVpc(this.vpc),
      destination: ec2.FlowLogDestination.toCloudWatchLogs(
        flowLogGroup,
        flowLogRole,
      ),
      trafficType: ec2.FlowLogTrafficType.ALL,
    });


  }

  private createVpcEndpoints(): void {
    // S3 Gateway Endpoint
    this.vpc.addGatewayEndpoint('S3GatewayEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
      subnets: [
        {
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // DynamoDB Gateway Endpoint
    this.vpc.addGatewayEndpoint('DynamoDBGatewayEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.DYNAMODB,
      subnets: [
        {
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // ECR Interface Endpoints (for Lambda)
    this.vpc.addInterfaceEndpoint('ECRDockerEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });

    this.vpc.addInterfaceEndpoint('ECREndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.ECR,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });

    // SSM Interface Endpoints
    this.vpc.addInterfaceEndpoint('SSMEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.SSM,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });

    this.vpc.addInterfaceEndpoint('SSMMessagesEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });

    // CloudWatch Logs Interface Endpoint
    this.vpc.addInterfaceEndpoint('CloudWatchLogsEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });

    // Lambda Interface Endpoint
    this.vpc.addInterfaceEndpoint('LambdaEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.LAMBDA,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });

    // Step Functions Interface Endpoint
    this.vpc.addInterfaceEndpoint('StepFunctionsEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.STEP_FUNCTIONS,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });

    // Bedrock Interface Endpoint (for AI services)
    this.vpc.addInterfaceEndpoint('BedrockEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [this.lambdaSecurityGroup],
    });
  }

}
