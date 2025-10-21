import * as cdk from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as cr from 'aws-cdk-lib/custom-resources';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface CognitoStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly adminUserEmail: string;
  readonly existingUserPoolId?: string;
  readonly existingUserPoolDomain?: string;
  readonly useCustomDomain?: boolean;
  readonly domainName?: string;
  readonly hostedZoneName?: string;
}

/**
 * AWS IDP AI - Cognito Authentication Stack
 * 
 * Provides Cognito User Pool for ALB authentication
 * Supports both custom domain and ALB DNS name for callback URLs
 */
export class CognitoStack extends cdk.Stack {
  public readonly userPool: cognito.IUserPool;
  public readonly userPoolClient: cognito.UserPoolClient;
  public readonly userPoolDomain: cognito.IUserPoolDomain;
  public readonly adminUser: cognito.CfnUserPoolUser;
  public readonly callbackUrl: string;

  constructor(scope: Construct, id: string, props: CognitoStackProps) {
    super(scope, id, props);

    const stage = props.stage || 'dev';

    // Use existing User Pool or create new one
    if (props.existingUserPoolId && props.existingUserPoolDomain) {
      this.userPool = cognito.UserPool.fromUserPoolId(
        this,
        'UserPool',
        props.existingUserPoolId
      );

      this.userPoolDomain = cognito.UserPoolDomain.fromDomainName(
        this,
        'UserPoolDomain',
        props.existingUserPoolDomain
      );
    } else {
      // Create new User Pool
      this.userPool = new cognito.UserPool(this, 'UserPool', {
        userPoolName: `aws-idp-ai-user-pool-${stage}`,
        autoVerify: { email: true, phone: false },
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        selfSignUpEnabled: true,
        signInAliases: {
          username: true,
          email: true,
        },
        signInCaseSensitive: false,
        standardAttributes: {
          email: {
            required: true,
            mutable: true,
          },
        },
        passwordPolicy: {
          minLength: 8,
          requireLowercase: true,
          requireUppercase: true,
          requireDigits: true,
          requireSymbols: true,
        },
        accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      });

      // Create User Pool Domain with valid prefix (must be globally unique)
      const accountSuffix = cdk.Stack.of(this).account.substring(8);
      const domainPrefix = `idp-${stage}-${accountSuffix}`;
      this.userPoolDomain = this.userPool.addDomain('UserPoolDomain', {
        cognitoDomain: {
          domainPrefix: domainPrefix,
        },
      });
    }

    // Create admin user - temporary password will be set via custom resource
    this.adminUser = new cognito.CfnUserPoolUser(this, 'AdminUser', {
      userPoolId: this.userPool.userPoolId,
      username: props.adminUserEmail.split('@')[0],
      userAttributes: [
        { name: 'email', value: props.adminUserEmail },
        { name: 'email_verified', value: 'true' },
      ],
      messageAction: 'SUPPRESS', // Don't send welcome email
    });

    // Create user groups
    const adminGroup = new cognito.UserPoolGroup(this, 'AdminGroup', {
      userPool: this.userPool,
      groupName: 'aws-idp-ai-admins',
      description: 'Administrative users with full access',
    });

    const userGroup = new cognito.UserPoolGroup(this, 'UserGroup', {
      userPool: this.userPool,
      groupName: 'aws-idp-ai-users',
      description: 'Regular users with standard access',
    });

    // Add admin user to both groups
    new cognito.CfnUserPoolUserToGroupAttachment(this, 'AdminUserToAdminGroup', {
      userPoolId: this.userPool.userPoolId,
      groupName: adminGroup.groupName,
      username: this.adminUser.username!,
    });

    new cognito.CfnUserPoolUserToGroupAttachment(this, 'AdminUserToUserGroup', {
      userPoolId: this.userPool.userPoolId,
      groupName: userGroup.groupName,
      username: this.adminUser.username!,
    });

    // Set temporary password using AWS custom resource
    new cr.AwsCustomResource(this, 'SetAdminPassword', {
      onCreate: {
        service: 'CognitoIdentityServiceProvider',
        action: 'adminSetUserPassword',
        parameters: {
          UserPoolId: this.userPool.userPoolId,
          Username: this.adminUser.username,
          Password: 'TempPass123!',
          Permanent: false, // Force password change on first login
        },
        physicalResourceId: cr.PhysicalResourceId.of('set-admin-password'),
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: [this.userPool.userPoolArn],
      }),
    });

    // Add NAG suppression for the custom resource at the stack level
    this.addNagSuppressionsForCustomResource();

    // Use temporary callback URL - will be updated by ECS stack after ALB creation
    const baseUrl = props.useCustomDomain && props.domainName && props.hostedZoneName
      ? `https://${props.domainName}.${props.hostedZoneName}`
      : 'https://localhost'; // Temporary placeholder - will be updated by ECS stack

    this.callbackUrl = `${baseUrl}/oauth2/idpresponse`;

    // Create User Pool Client
    const userPoolClient = new cognito.UserPoolClient(this, 'UserPoolClient', {
      userPool: this.userPool,
      userPoolClientName: `aws-idp-ai-alb-client-${stage}`,
      generateSecret: true,
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
        },
        scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
        callbackUrls: [this.callbackUrl, baseUrl],
        logoutUrls: [baseUrl, `${baseUrl}/logged-out`],
      },
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
      preventUserExistenceErrors: true,
      authFlows: {
        userPassword: true,
        userSrp: true,
      },
    });

    // Explicitly enable OAuth flows at the CloudFormation level
    const cfnUserPoolClient = userPoolClient.node.defaultChild as cognito.CfnUserPoolClient;
    cfnUserPoolClient.allowedOAuthFlowsUserPoolClient = true;

    // Include cognito:groups in ID token for RBAC
    // This ensures that user group membership is available in the JWT token from ALB
    cfnUserPoolClient.readAttributes = [
      'email',
      'email_verified',
      'name',
      'given_name',
      'family_name',
      'preferred_username',
      'cognito:groups', // Include groups in ID token
    ];

    this.userPoolClient = userPoolClient;

    // Custom Resource for callback URL update will be handled by ECS stack

    // Add Cognito branding
    new cognito.CfnManagedLoginBranding(this, 'ManagedLoginBranding', {
      userPoolId: this.userPool.userPoolId,
      clientId: this.userPoolClient.userPoolClientId,
      returnMergedResources: true,
      useCognitoProvidedValues: true,
    });

    // Apply NAG suppressions
    NagSuppressions.addResourceSuppressions(
      this.userPool,
      [
        {
          id: 'AwsSolutions-COG2',
          reason: 'MFA is optional for this application; users can enable it if needed',
        },
        {
          id: 'AwsSolutions-COG3',
          reason: 'AdvancedSecurityMode is not required for this internal tool',
        },
      ],
      true
    );

    // Output values
    new cdk.CfnOutput(this, 'UserPoolId', {
      value: this.userPool.userPoolId,
      description: 'Cognito User Pool ID',
      exportName: `aws-idp-ai-user-pool-id-${stage}`,
    });

    new cdk.CfnOutput(this, 'UserPoolClientId', {
      value: this.userPoolClient.userPoolClientId,
      description: 'Cognito User Pool Client ID',
      exportName: `aws-idp-ai-user-pool-client-id-${stage}`,
    });

    new cdk.CfnOutput(this, 'UserPoolDomain', {
      value: this.userPoolDomain.domainName,
      description: 'Cognito User Pool Domain',
      exportName: `aws-idp-ai-user-pool-domain-${stage}`,
    });

    new cdk.CfnOutput(this, 'AdminUsername', {
      value: this.adminUser.username || '',
      description: 'Admin user username',
    });

    new cdk.CfnOutput(this, 'AdminUserEmail', {
      value: props.adminUserEmail,
      description: 'Admin user email',
    });

    new cdk.CfnOutput(this, 'TemporaryPassword', {
      value: 'TempPass123!',
      description: 'Temporary password - must be changed on first login',
    });
  }

  /**
   * Add CDK Nag suppressions for custom resource
   */
  private addNagSuppressionsForCustomResource(): void {
    // Suppress IAM4 warning for custom resource service roles
    NagSuppressions.addStackSuppressions(this, [
      {
        id: 'AwsSolutions-IAM4',
        reason: [
          'AWS Lambda Basic Execution Role is required for custom resource Lambda functions.',
          'Custom resources created by CDK for Cognito password setting require AWS managed policies.',
          'These managed policies provide necessary CloudWatch logging permissions for custom resource execution.',
        ].join(' '),
        appliesTo: [
          'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
        ],
      },
    ]);
  }
}