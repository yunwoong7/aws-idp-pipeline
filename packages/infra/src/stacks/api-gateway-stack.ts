import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as logs from 'aws-cdk-lib/aws-logs';
import { CfnStage } from 'aws-cdk-lib/aws-apigatewayv2';
import { Construct } from 'constructs';

export interface ApiGatewayStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly throttleSettings?: {
    rateLimit: number;
    burstLimit: number;
  };
}

/**
 * AWS IDP AI Analysis API Gateway Stack
 *
 * Provides only the basic HTTP API Gateway infrastructure:
 * - Create HTTP API Gateway
 * - CORS configuration
 * - CloudWatch logging
 * - Throttling configuration
 * - Store in SSM Parameter Store
 *
 * Each feature stack references httpApi to add its own Lambda + routes
 */
export class ApiGatewayStack extends cdk.Stack {
  public readonly httpApi: apigw.HttpApi;
  public readonly apiUrl: string;
  public readonly stageName: string;

  constructor(scope: Construct, id: string, props: ApiGatewayStackProps) {
    super(scope, id, props);

    this.stageName = props.stage || 'prod';

    // CloudWatch Log Group for API Gateway access logs
    const logGroup = new logs.LogGroup(this, 'AwsIdpAiApiAccessLogs', {
      logGroupName: `/aws-idp-ai/api-gateway/${this.stageName}/access-logs`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create HTTP API Gateway for AWS IDP AI Analysis
    this.httpApi = new apigw.HttpApi(this, 'AwsIdpAiApi', {
      apiName: `aws-idp-ai-api-${this.stageName}`,
      description:
        'AWS IDP AI Analysis Platform API - 각 기능 스택에서 라우트 추가',

      // CORS configuration for Next.js frontend
      corsPreflight: {
        allowOrigins: ['*'], // Allow all origins for MVP
        allowMethods: [
          apigw.CorsHttpMethod.GET,
          apigw.CorsHttpMethod.POST,
          apigw.CorsHttpMethod.PUT,
          apigw.CorsHttpMethod.DELETE,
          apigw.CorsHttpMethod.OPTIONS,
          apigw.CorsHttpMethod.PATCH,
        ],
        allowHeaders: [
          'Content-Type',
          'Authorization',
          'X-Amz-Date',
          'X-Api-Key',
          'X-Amz-Security-Token',
          'X-Amz-User-Agent',
          'Cache-Control',
          'Pragma',
          'Accept',
          'Accept-Encoding',
          'Accept-Language',
          'Connection',
          'Host',
          'Origin',
          'Referer',
          'User-Agent',
        ],
        exposeHeaders: ['X-Request-Id', 'X-Amzn-Trace-Id'],
        allowCredentials: false,
        maxAge: cdk.Duration.hours(2),
      },

      defaultIntegration: undefined,
      disableExecuteApiEndpoint: false,
    });

    // Configure access logging and throttling
    this.configureStageSettings(logGroup, props.throttleSettings);


    // Create CloudFormation outputs
    this.createOutputs();

    this.apiUrl = this.httpApi.apiEndpoint;
  }

  /**
   * Configure stage settings for logging and throttling
   */
  private configureStageSettings(
    logGroup: logs.LogGroup,
    throttleSettings?: { rateLimit: number; burstLimit: number },
  ): void {
    const defaultStage = this.httpApi.defaultStage?.node
      .defaultChild as CfnStage;
    if (defaultStage) {
      defaultStage.accessLogSettings = {
        destinationArn: logGroup.logGroupArn,
        format: JSON.stringify({
          requestId: '$context.requestId',
          requestTime: '$context.requestTime',
          httpMethod: '$context.httpMethod',
          routeKey: '$context.routeKey',
          path: '$context.path',
          sourceIp: '$context.identity.sourceIp',
          userAgent: '$context.identity.userAgent',
          status: '$context.status',
          responseLength: '$context.responseLength',
          integrationLatency: '$context.integrationLatency',
          responseLatency: '$context.responseLatency',
          error: {
            message: '$context.error.message',
            responseType: '$context.error.responseType',
          },
        }),
      };

      const throttle = throttleSettings || {
        rateLimit: 1000,
        burstLimit: 2000,
      };
      defaultStage.defaultRouteSettings = {
        throttlingRateLimit: throttle.rateLimit,
        throttlingBurstLimit: throttle.burstLimit,
        detailedMetricsEnabled: true,
      };
    }
  }

  /**
   * Create CloudFormation outputs for deployment script
   */
  private createOutputs(): void {
    new cdk.CfnOutput(this, 'ApiGatewayEndpoint', {
      value: this.httpApi.apiEndpoint,
      description: 'AWS IDP AI API Gateway endpoint URL',
    });

    new cdk.CfnOutput(this, 'ApiGatewayId', {
      value: this.httpApi.httpApiId,
      description: 'AWS IDP AI API Gateway ID',
    });

    new cdk.CfnOutput(this, 'ApiGatewayStageName', {
      value: this.stageName,
      description: 'AWS IDP AI API Gateway stage name',
    });
  }
}
