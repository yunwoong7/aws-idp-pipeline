import * as cdk from 'aws-cdk-lib';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as r53 from 'aws-cdk-lib/aws-route53';
import { Construct } from 'constructs';

export interface CertificateStackProps extends cdk.StackProps {
  readonly stage?: string;
  readonly useCustomDomain?: boolean;
  readonly domainName?: string;
  readonly hostedZoneId?: string;
  readonly hostedZoneName?: string;
  readonly existingCertificateArn?: string;
  readonly albDnsName?: string;
}

/**
 * AWS IDP AI - Certificate Stack
 * 
 * Provides SSL/TLS certificates for ALB:
 * - Custom domain: Creates ACM certificate with Route53 validation
 * - No custom domain: Creates self-signed certificate and imports to ACM
 */
export class CertificateStack extends cdk.Stack {
  public readonly certificate: acm.ICertificate;

  constructor(scope: Construct, id: string, props: CertificateStackProps) {
    super(scope, id, props);

    const stage = props.stage || 'dev';

    if (props.existingCertificateArn) {
      // Use existing certificate
      this.certificate = acm.Certificate.fromCertificateArn(
        this,
        'Certificate',
        props.existingCertificateArn
      );
    } else if (props.useCustomDomain && props.domainName && props.hostedZoneId && props.hostedZoneName) {
      // Create certificate for custom domain with DNS validation
      const hostedZone = r53.HostedZone.fromHostedZoneAttributes(this, 'HostedZone', {
        hostedZoneId: props.hostedZoneId,
        zoneName: props.hostedZoneName,
      });

      this.certificate = new acm.Certificate(this, 'Certificate', {
        domainName: `${props.domainName}.${props.hostedZoneName}`,
        validation: acm.CertificateValidation.fromDns(hostedZone),
      });
    } else {
      throw new Error('Certificate Stack requires either custom domain configuration or existing certificate ARN');
    }

    new cdk.CfnOutput(this, 'CertificateArn', {
      value: this.certificate.certificateArn,
      description: 'SSL Certificate ARN',
      exportName: `aws-idp-ai-certificate-arn-${stage}`,
    });
  }

}