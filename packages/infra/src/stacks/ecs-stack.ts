import * as cdk from 'aws-cdk-lib';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as elbv2Actions from 'aws-cdk-lib/aws-elasticloadbalancingv2-actions';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as r53 from 'aws-cdk-lib/aws-route53';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as cr from 'aws-cdk-lib/custom-resources';

import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface EcsStackProps extends cdk.StackProps {
  stage: string;
  vpc: ec2.IVpc;
  backendRepository: ecr.IRepository;
  frontendRepository: ecr.IRepository;
  apiGatewayUrl: string;
  s3BucketName: string;
  documentsTableName: string;
  usersTableName: string;
  // Cognito configuration (using IDs to avoid cross-stack exports)
  userPoolId?: string;
  userPoolClientId?: string;
  userPoolDomainName?: string;
  certificate?: acm.ICertificate;
  existingCertificateArn?: string;
  // Domain configuration
  useCustomDomain?: boolean;
  domainName?: string;
  hostedZoneId?: string;
  hostedZoneName?: string;
}

export class EcsStack extends cdk.Stack {
  public readonly cluster: ecs.Cluster;
  public readonly frontendService: ecsPatterns.ApplicationLoadBalancedFargateService;
  public readonly backendService: ecsPatterns.ApplicationLoadBalancedFargateService;
  public readonly loadBalancer: elbv2.IApplicationLoadBalancer;
  public readonly cognitoUserPoolDomain?: string;
  public readonly cognitoClientId?: string;

  constructor(scope: Construct, id: string, props: EcsStackProps) {
    super(scope, id, props);

    const {
      stage,
      vpc,
      backendRepository,
      frontendRepository,
      apiGatewayUrl,
      s3BucketName,
      documentsTableName,
      usersTableName,
      userPoolId,
      userPoolClientId,
      userPoolDomainName,
      certificate,
      existingCertificateArn,
      useCustomDomain,
      domainName,
      hostedZoneId,
      hostedZoneName
    } = props;

    // Import Cognito resources from IDs to avoid cross-stack exports
    const userPool = userPoolId ? cognito.UserPool.fromUserPoolId(this, 'ImportedUserPool', userPoolId) : undefined;
    const userPoolClient = userPoolClientId ? cognito.UserPoolClient.fromUserPoolClientId(this, 'ImportedUserPoolClient', userPoolClientId) : undefined;
    const userPoolDomain = userPoolDomainName ? cognito.UserPoolDomain.fromDomainName(this, 'ImportedUserPoolDomain', userPoolDomainName) : undefined;

    // Assign Cognito properties for export
    this.cognitoUserPoolDomain = userPoolDomainName;
    this.cognitoClientId = userPoolClientId;

    // Handle certificate - use provided certificate or existing ARN
    const finalCertificate = certificate || (existingCertificateArn ?
      acm.Certificate.fromCertificateArn(this, 'ExistingCertificate', existingCertificateArn) :
      undefined
    );

    // ECS Cluster 생성
    this.cluster = new ecs.Cluster(this, 'EcsCluster', {
      clusterName: `aws-idp-cluster-${stage}`,
      vpc,
      containerInsights: true,
    });

    // S3 bucket for ALB access logs
    const albLogsBucket = new s3.Bucket(this, 'AlbLogsBucket', {
      bucketName: `aws-idp-alb-logs-${stage}-${cdk.Aws.ACCOUNT_ID}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      lifecycleRules: [
        {
          id: 'delete-old-access-logs',
          expiration: cdk.Duration.days(30),
        },
      ],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      enforceSSL: true,
    });

    // Task Execution Role (ECR, CloudWatch 권한)
    const taskExecutionRole = new iam.Role(this, 'TaskExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
      ],
      inlinePolicies: {
        ECSTaskExecutionPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'secretsmanager:GetSecretValue',
                'ssm:GetParameter',
                'ssm:GetParameters',
                'ssm:GetParametersByPath',
              ],
              resources: [
                `arn:aws:secretsmanager:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:secret:/aws-idp/${stage}/*`,
                `arn:aws:ssm:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:parameter/aws-idp/${stage}/*`,
              ],
            }),
          ],
        }),
      },
    });

    // Task Role (애플리케이션이 AWS 서비스 접근용)
    const taskRole = new iam.Role(this, 'TaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      inlinePolicies: {
        ApplicationPolicy: new iam.PolicyDocument({
          statements: [
            // Bedrock 접근 권한
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:InvokeModel',
                'bedrock:InvokeModelWithResponseStream',
              ],
              resources: ['*'],
            }),
            // DynamoDB 접근 권한
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'dynamodb:GetItem',
                'dynamodb:PutItem',
                'dynamodb:Query',
                'dynamodb:Scan',
                'dynamodb:UpdateItem',
                'dynamodb:DeleteItem',
              ],
              resources: [
                `arn:aws:dynamodb:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:table/aws-idp-ai-*`,
              ],
            }),
            // S3 접근 권한 (백엔드 직접 업로드용)
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                's3:GetObject',
                's3:PutObject',
                's3:DeleteObject',
                's3:PutObjectMetadata',
              ],
              resources: [
                `arn:aws:s3:::${s3BucketName}/*`,
              ],
            }),
            // OpenSearch 접근 권한
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'es:ESHttpPost',
                'es:ESHttpPut',
                'es:ESHttpGet',
                'es:ESHttpDelete',
              ],
              resources: [
                `arn:aws:es:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:domain/aws-idp-*/*`,
              ],
            }),
          ],
        }),
      },
    });

    // Determine domain configuration
    let domainZone: r53.IHostedZone | undefined;
    let fullDomainName: string | undefined;

    if (useCustomDomain && domainName && hostedZoneId && hostedZoneName) {
      domainZone = r53.HostedZone.fromHostedZoneAttributes(this, 'HostedZone', {
        hostedZoneId,
        zoneName: hostedZoneName,
      });
      fullDomainName = `${domainName}.${hostedZoneName}`;
    }

    // Frontend Fargate Service (ApplicationLoadBalancedFargateService 사용)
    // Note: We'll modify the listener actions after creation for Cognito
    this.frontendService = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'FrontendService', {
      cluster: this.cluster,
      serviceName: `aws-idp-frontend-${stage}`,
      cpu: 512,
      memoryLimitMiB: 1024,
      desiredCount: 1,
      publicLoadBalancer: true,
      openListener: true,  // Always create the listener, we'll modify it for Cognito
      taskImageOptions: {
        image: ecs.ContainerImage.fromEcrRepository(frontendRepository, 'latest'),
        containerName: 'frontend',
        containerPort: 3000,
        executionRole: taskExecutionRole,
        taskRole: taskRole,
        logDriver: ecs.LogDrivers.awsLogs({
          streamPrefix: 'frontend',
          logRetention: logs.RetentionDays.ONE_WEEK,
        }),
        environment: {
          NODE_ENV: 'production',
          PORT: '3000',
          NEXT_PUBLIC_AUTH_DISABLED: 'false',  // 배포 환경에서는 실제 Cognito 인증 사용
        },
      },
      certificate: finalCertificate,
      domainName: fullDomainName,
      domainZone: domainZone,
      listenerPort: finalCertificate ? 443 : 80,
      protocol: finalCertificate ? elbv2.ApplicationProtocol.HTTPS : elbv2.ApplicationProtocol.HTTP,
      redirectHTTP: finalCertificate ? true : false,
    });

    // ALB DNS 또는 커스텀 도메인을 기반으로 백엔드 URL 생성 및 API Gateway URL과 함께 프론트엔드 환경변수에 추가
    const albDnsName = this.frontendService.loadBalancer.loadBalancerDnsName;
    // 커스텀 도메인이 있으면 우선 사용, 없으면 ALB DNS 사용
    const actualDomain = fullDomainName || albDnsName;
    const backendUrl = finalCertificate ? `https://${actualDomain}` : `http://${actualDomain}`;

    // 프론트엔드 태스크 정의의 컨테이너에 동적 URL 환경변수 추가
    const frontendContainer = this.frontendService.taskDefinition.defaultContainer;
    if (frontendContainer) {
      frontendContainer.addEnvironment('NEXT_PUBLIC_ECS_BACKEND_URL', backendUrl);
      frontendContainer.addEnvironment('NEXT_PUBLIC_API_BASE_URL', apiGatewayUrl);
      // 디버깅을 위한 로그
      console.log(`Frontend container env vars: API_BASE_URL=${apiGatewayUrl}, ECS_BACKEND_URL=${backendUrl}`);
      console.log(`Using domain: ${actualDomain} (custom domain: ${fullDomainName || 'none'})`);
    }

    // Backend Fargate Service (별도 ALB 대신 Frontend ALB에 리스너 규칙 추가)
    const backendTaskDefinition = new ecs.FargateTaskDefinition(this, 'BackendTaskDefinition', {
      cpu: 512,
      memoryLimitMiB: 1024,
      executionRole: taskExecutionRole,
      taskRole: taskRole,
    });

    backendTaskDefinition.addContainer('backend', {
      image: ecs.ContainerImage.fromEcrRepository(backendRepository, 'latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'backend',
        logRetention: logs.RetentionDays.ONE_WEEK,
      }),
      environment: {
        PYTHONPATH: '/app',
        PYTHONUNBUFFERED: '1',
        PROJECT_ROOT: '/app',
        MCP_WORKSPACE_DIR: '/app/mcp-workspace',
        STAGE: stage,
        AWS_REGION: cdk.Aws.REGION,
        AWS_DEFAULT_REGION: cdk.Aws.REGION,
        AUTH_DISABLED: 'false',  // 배포 환경에서는 실제 Cognito 인증 사용
        API_BASE_URL: apiGatewayUrl,
        // Document upload related environment variables
        DOCUMENTS_BUCKET_NAME: s3BucketName,
        DOCUMENTS_TABLE_NAME: documentsTableName,
        // RBAC related environment variables
        USERS_TABLE_NAME: usersTableName,
        // Cognito configuration for logout (will be added dynamically if Cognito is configured)
        ...(userPool && userPoolClient && userPoolDomain && {
          COGNITO_USER_POOL_DOMAIN: userPoolDomain.domainName,
          COGNITO_CLIENT_ID: userPoolClient.userPoolClientId,
        }),
      },
      portMappings: [
        {
          containerPort: 8000,
          protocol: ecs.Protocol.TCP,
        },
      ],
    });

    // Backend ECS Service
    const backendService = new ecs.FargateService(this, 'BackendFargateService', {
      cluster: this.cluster,
      serviceName: `aws-idp-backend-${stage}`,
      taskDefinition: backendTaskDefinition,
      desiredCount: 1,
    });

    // Type assertion for public property
    this.backendService = backendService as any;

    // Frontend ALB에 Backend용 Target Group과 리스너 규칙 추가
    this.loadBalancer = this.frontendService.loadBalancer;

    const backendTargetGroup = new elbv2.ApplicationTargetGroup(this, 'BackendTargetGroup', {
      vpc,
      port: 8000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        enabled: true,
        healthyHttpCodes: '200',
        path: '/',
        port: '8000',
        protocol: elbv2.Protocol.HTTP,
        timeout: cdk.Duration.seconds(30),
        interval: cdk.Duration.seconds(60),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
      // 스트리밍 응답을 위한 타임아웃 설정
      deregistrationDelay: cdk.Duration.seconds(60),
    });

    // Backend 서비스를 Target Group에 연결
    backendTargetGroup.addTarget(backendService);

    // Configure Cognito authentication using the existing listener
    const listener = this.frontendService.listener;

    if (userPool && userPoolClient && userPoolDomain) {
      // Modify the existing listener's default action to use Cognito authentication
      // IMPORTANT: Order matters - authenticate first (order: 1), then forward (order: 2)
      const cfnListener = listener.node.defaultChild as elbv2.CfnListener;
      cfnListener.defaultActions = [
        {
          type: 'authenticate-cognito',
          order: 1,
          authenticateCognitoConfig: {
            userPoolArn: userPool.userPoolArn,
            userPoolClientId: userPoolClient.userPoolClientId,
            userPoolDomain: userPoolDomain.domainName,
            sessionCookieName: 'AWSELBAuthSessionCookie',
            scope: 'openid email profile',
            sessionTimeout: '86400', // 1 day (86400 seconds)
            onUnauthenticatedRequest: 'authenticate',
          },
        },
        {
          type: 'forward',
          order: 2,
          targetGroupArn: this.frontendService.targetGroup.targetGroupArn,
        },
      ];

      // Add public routes (no authentication required)
      // - /logged-out: Post-logout landing page
      // - /_next/*: Next.js static assets (CSS, JS chunks, images)
      listener.addAction('LoggedOutPageAction', {
        priority: 10,
        conditions: [
          elbv2.ListenerCondition.pathPatterns([
            '/logged-out',
            '/logged-out/*',
            '/_next/*',
          ]),
        ],
        action: elbv2.ListenerAction.forward([this.frontendService.targetGroup]),
      });

      // Add backend routing with Cognito auth
      listener.addAction('BackendApiAction', {
        priority: 50,
        conditions: [
          elbv2.ListenerCondition.pathPatterns(['/api/*']),
        ],
        action: new elbv2Actions.AuthenticateCognitoAction({
          userPool,
          userPoolClient,
          userPoolDomain,
          next: elbv2.ListenerAction.forward([backendTargetGroup]),
        }),
      });

      // Update Cognito callback URL with actual ALB DNS (only if not using custom domain)
      if (!useCustomDomain) {
        this.createCallbackUpdater(
          userPool,
          userPoolClient,
          this.frontendService.loadBalancer.loadBalancerDnsName
        );
      }
    } else {
      // No authentication - add backend routing only
      listener.addAction('BackendRoutingAction', {
        priority: 100,
        conditions: [
          elbv2.ListenerCondition.pathPatterns(['/api/*']),
        ],
        action: elbv2.ListenerAction.forward([backendTargetGroup]),
      });
    }

    // ALB 액세스 로그 설정
    this.frontendService.loadBalancer.logAccessLogs(albLogsBucket, 'alb-access-logs');
    
    // ALB idle timeout 설정 (대용량 파일 업로드를 위해 600초로 증가)
    this.frontendService.loadBalancer.setAttribute('idle_timeout.timeout_seconds', '600');

    // Security group configuration - allow internet access for Cognito authentication
    // Remove IP whitelist since we're using Cognito for authentication
    const httpsPort = finalCertificate ? 443 : 80;
    const httpPort = 80;

    // Allow HTTPS/HTTP from anywhere for Cognito authentication
    this.frontendService.loadBalancer.connections.allowFromAnyIpv4(
      ec2.Port.tcp(httpsPort),
      `Allow ${finalCertificate ? 'HTTPS' : 'HTTP'} from anywhere for Cognito auth`
    );

    // If HTTPS, also allow HTTP for redirect
    if (finalCertificate) {
      this.frontendService.loadBalancer.connections.allowFromAnyIpv4(
        ec2.Port.tcp(httpPort),
        'Allow HTTP for HTTPS redirect'
      );
    }

    // VPC internal communication
    this.frontendService.loadBalancer.connections.allowFrom(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(httpsPort),
      'Allow internal VPC communication'
    );


    // CloudFormation Outputs
    new cdk.CfnOutput(this, 'LoadBalancerDnsName', {
      value: this.frontendService.loadBalancer.loadBalancerDnsName,
      description: 'Application Load Balancer DNS Name',
      exportName: `${id}-LoadBalancerDnsName`,
    });

    new cdk.CfnOutput(this, 'FrontendUrl', {
      value: `http://${this.frontendService.loadBalancer.loadBalancerDnsName}`,
      description: 'Frontend Application URL',
      exportName: `${id}-FrontendUrl`,
    });

    new cdk.CfnOutput(this, 'BackendApiUrl', {
      value: `http://${this.frontendService.loadBalancer.loadBalancerDnsName}/api`,
      description: 'Backend API URL',
      exportName: `${id}-BackendApiUrl`,
    });

    // CDK-NAG 억제
    NagSuppressions.addResourceSuppressions(
      taskExecutionRole,
      [
        {
          id: 'AwsSolutions-IAM4',
          reason: 'ECS Task Execution Role requires AWS managed policy for container operations',
          appliesTo: ['Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'],
        },
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Task execution role needs broad permissions for ECS operations and Secrets Manager access',
          appliesTo: [
            'Resource::*',
            'Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:secret:/aws-idp/dev/*',
            'Resource::arn:aws:ssm:<AWS::Region>:<AWS::AccountId>:parameter/aws-idp/dev/*',
          ],
        },
      ]
    );

    // Task Execution Role Default Policy suppression
    NagSuppressions.addResourceSuppressions(
      taskExecutionRole.node.findChild('DefaultPolicy') as iam.Policy,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Task execution role default policy needs wildcard permissions for Secrets Manager and SSM access',
          appliesTo: ['Resource::*'],
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      taskRole,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Task role needs permissions to access AWS services with dynamic resource names',
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      albLogsBucket,
      [
        {
          id: 'AwsSolutions-S1',
          reason: 'ALB access logs bucket does not need server access logging',
        },
      ]
    );

    // Frontend Service suppressions
    NagSuppressions.addResourceSuppressions(
      this.frontendService.loadBalancer.connections.securityGroups[0],
      [
        {
          id: 'AwsSolutions-EC23',
          reason: 'ALB security group allows internet access for web application (will be restricted in production)',
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      this.frontendService.taskDefinition,
      [
        {
          id: 'AwsSolutions-ECS2',
          reason: 'Task definition uses environment variables for non-sensitive configuration only',
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      this.frontendService.service,
      [
        {
          id: '@aws-cdk/aws-ecs:minHealthyPercent',
          reason: 'Default minHealthyPercent is acceptable for development environment',
        },
      ]
    );

    // Backend Task Definition suppressions
    NagSuppressions.addResourceSuppressions(
      backendTaskDefinition,
      [
        {
          id: 'AwsSolutions-ECS2',
          reason: 'Task definition uses environment variables for non-sensitive configuration only',
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      backendService,
      [
        {
          id: '@aws-cdk/aws-ecs:minHealthyPercent',
          reason: 'Default minHealthyPercent is acceptable for development environment',
        },
      ]
    );

    // Tag resources
    cdk.Tags.of(this).add('Project', 'aws-idp-pipeline');
    cdk.Tags.of(this).add('Environment', stage);
  }

  private createCallbackUpdater(userPool: cognito.IUserPool, userPoolClient: cognito.IUserPoolClient, albDnsName: string) {
    // Lambda function to update callback URL
    const updateCallbackLambda = new lambda.Function(this, 'UpdateCallbackLambda', {
      runtime: lambda.Runtime.NODEJS_18_X,
      handler: 'index.handler',
      code: lambda.Code.fromInline(`
        const { CognitoIdentityProviderClient, DescribeUserPoolClientCommand, UpdateUserPoolClientCommand } = require('@aws-sdk/client-cognito-identity-provider');
        
        exports.handler = async (event) => {
          console.log('Event:', JSON.stringify(event, null, 2));
          
          if (event.RequestType === 'Delete') {
            return { PhysicalResourceId: event.PhysicalResourceId || 'UpdateCallbackResource' };
          }
          
          try {
            const { UserPoolId, UserPoolClientId, AlbDnsName } = event.ResourceProperties;

            // ALB returns DNS names with mixed case, but browsers/ALB may normalize to lowercase
            // Add both original and lowercase versions to handle case sensitivity in Cognito
            const baseUrl = \`https://\${AlbDnsName}\`;
            const baseUrlLower = \`https://\${AlbDnsName.toLowerCase()}\`;
            const callbackUrl = \`\${baseUrl}/oauth2/idpresponse\`;
            const callbackUrlLower = \`\${baseUrlLower}/oauth2/idpresponse\`;
            const logoutUrl = \`\${baseUrl}/logged-out\`;
            const logoutUrlLower = \`\${baseUrlLower}/logged-out\`;

            const client = new CognitoIdentityProviderClient({ region: process.env.AWS_REGION });

            // Get current client configuration
            const describeCommand = new DescribeUserPoolClientCommand({
              UserPoolId,
              ClientId: UserPoolClientId,
            });
            const describeResponse = await client.send(describeCommand);
            const currentClient = describeResponse.UserPoolClient;

            // Only include necessary fields to avoid read-only property errors
            const updateCommand = new UpdateUserPoolClientCommand({
              UserPoolId,
              ClientId: UserPoolClientId,
              ClientName: currentClient.ClientName,
              AllowedOAuthFlows: currentClient.AllowedOAuthFlows || ['code'],
              AllowedOAuthScopes: currentClient.AllowedOAuthScopes || ['openid', 'email', 'profile'],
              AllowedOAuthFlowsUserPoolClient: true, // Explicitly enable OAuth flows
              CallbackURLs: [callbackUrl, baseUrl, callbackUrlLower, baseUrlLower],
              LogoutURLs: [baseUrl, logoutUrl, baseUrlLower, logoutUrlLower],
              SupportedIdentityProviders: currentClient.SupportedIdentityProviders || ['COGNITO'],
              ExplicitAuthFlows: currentClient.ExplicitAuthFlows,
              PreventUserExistenceErrors: currentClient.PreventUserExistenceErrors,
            });
            await client.send(updateCommand);

            console.log('Successfully updated callback URLs (with case variants):', [callbackUrl, baseUrl, callbackUrlLower, baseUrlLower]);
            console.log('Successfully updated logout URLs (with case variants):', [baseUrl, logoutUrl, baseUrlLower, logoutUrlLower]);
            return {
              PhysicalResourceId: 'UpdateCallbackResource',
              Data: { CallbackUrl: callbackUrl, BaseUrl: baseUrl, LogoutUrl: logoutUrl }
            };
          } catch (error) {
            console.error('Error updating callback URL:', error);
            throw error;
          }
        };
      `),
      timeout: cdk.Duration.minutes(5),
    });

    // Grant permissions
    updateCallbackLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          'cognito-idp:DescribeUserPoolClient',
          'cognito-idp:UpdateUserPoolClient',
        ],
        resources: ['*'],
      })
    );

    // Create custom resource provider
    const provider = new cr.Provider(this, 'UpdateCallbackProvider', {
      onEventHandler: updateCallbackLambda,
    });

    // Add NAG suppressions for the Provider's framework Lambda
    NagSuppressions.addResourceSuppressionsByPath(
      this,
      '/aws-idp-ai-ecs/UpdateCallbackProvider/framework-onEvent/Resource',
      [
        {
          id: 'AwsSolutions-L1',
          reason: 'CDK-generated custom resource framework Lambda uses CDK-managed runtime version',
        },
      ]
    );

    // Create custom resource
    new cdk.CustomResource(this, 'UpdateCallbackResource', {
      serviceToken: provider.serviceToken,
      properties: {
        UserPoolId: userPool.userPoolId,
        UserPoolClientId: userPoolClient.userPoolClientId,
        AlbDnsName: albDnsName,
      },
    });

    // Apply NAG suppressions for Lambda function
    NagSuppressions.addResourceSuppressions(
      updateCallbackLambda,
      [
        {
          id: 'AwsSolutions-IAM4',
          reason: 'Lambda requires AWS managed policy for basic execution',
        },
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Lambda requires wildcard permissions for Cognito operations',
        },
        {
          id: 'AwsSolutions-L1',
          reason: 'Using Node.js 18 which is a supported runtime',
        },
      ],
      true
    );

    // Apply NAG suppressions for Provider framework
    NagSuppressions.addResourceSuppressions(
      provider,
      [
        {
          id: 'AwsSolutions-IAM4',
          reason: 'Provider framework requires AWS managed policies for Lambda execution',
          appliesTo: ['Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'],
        },
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Provider framework requires wildcard permissions for Lambda invocation',
        },
      ],
      true
    );
  }
}