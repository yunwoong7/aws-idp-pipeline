import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

interface RouteInfo {
  path: string;
  methods: apigw.HttpMethod[];
}

export interface ApiGatewayRoutesProps {
  readonly httpApi: apigw.IHttpApi;
  readonly integrationLambda: lambda.IFunction;
  readonly routePaths: RouteInfo[];
  readonly constructIdPrefix: string;
  readonly authSuppressionReason?: string;
}

export class ApiGatewayRoutes extends Construct {
  public readonly httpRoutes: apigw.HttpRoute[] = [];
  public readonly integration: integrations.HttpLambdaIntegration;

  constructor(scope: Construct, id: string, props: ApiGatewayRoutesProps) {
    super(scope, id);

    // Create Lambda integration
    this.integration = new integrations.HttpLambdaIntegration(
      `${props.constructIdPrefix}Integration`,
      props.integrationLambda,
    );

    // Create routes
    props.routePaths.forEach((route, index) => {
      route.methods.forEach((method, methodIndex) => {
        // Create unique route ID
        const sanitizedPath = route.path.replace(/[^A-Za-z0-9]/g, '');
        const sanitizedMethod = method.toString().replace(/[^A-Za-z0-9]/g, '');
        const routeId = `${props.constructIdPrefix}${sanitizedMethod}${sanitizedPath}Route${index}${methodIndex}`;

        const httpRoute = new apigw.HttpRoute(
          this,
          routeId,
          {
            httpApi: props.httpApi,
            routeKey: apigw.HttpRouteKey.with(route.path, method),
            integration: this.integration,
          },
        );
        this.httpRoutes.push(httpRoute);
      });
    });

    // Apply common Nag suppression
    this.addNagSuppressions(props.authSuppressionReason);
  }

  /**
   * CDK Nag suppression settings
   */
  private addNagSuppressions(customReason?: string): void {
    const defaultReason = [
      'MVP development environment requires unauthenticated API access for rapid prototyping and testing.',
      'This is a development/testing environment where API endpoints need to be accessible without authentication.',
      'Production deployment will implement proper authentication using AWS Cognito User Pools or IAM authorization.',
      'Current API endpoints are used for internal development and integration testing only.',
    ].join(' ');

    this.httpRoutes.forEach((route) => {
      NagSuppressions.addResourceSuppressions(
        route,
        [
          {
            id: 'AwsSolutions-APIG4',
            reason: customReason || defaultReason,
          },
        ],
        true,
      );
    });
  }
} 