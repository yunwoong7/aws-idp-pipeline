import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as oss from 'aws-cdk-lib/aws-opensearchservice';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface OpensearchProps {
  vpc: ec2.IVpc;
  isProd?: boolean;
}

/**
 * AWS IDP AI Analysis - OpenSearch Construct
 *
 * OpenSearch domain for storing analysis results and vector embeddings:
 * - Store project-specific analysis results
 * - Store vector embeddings and support hybrid search
 * - Secure VPC configuration
 * - Logging and monitoring settings
 */
export class Opensearch extends Construct {
  readonly domain: oss.IDomain;
  readonly securityGroup: ec2.ISecurityGroup;

  constructor(scope: Construct, id: string, props: OpensearchProps) {
    super(scope, id);

    const securityGroup = this.createSecurityGroup(props.vpc);
    const domain = this.createDomain(
      props.vpc,
      securityGroup,
      props.isProd || false,
    );

    this.domain = domain;
    this.securityGroup = securityGroup;
  }

  /**
   * Create OpenSearch domain
   */
  private createDomain(
    vpc: ec2.IVpc,
    securityGroup: ec2.ISecurityGroup,
    isProd: boolean,
  ): oss.Domain {
    const searchSlowLogsGroup = new logs.LogGroup(this, 'SearchSlowLogs', {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: isProd
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });

    const indexSlowLogsGroup = new logs.LogGroup(this, 'IndexSlowLogs', {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: isProd
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });

    const openSearchPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      principals: [new iam.AccountPrincipal(cdk.Stack.of(this).account)],
      actions: ['es:*'],
      resources: ['*'],
    });

    const subnets = vpc.selectSubnets({
      subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
    }).subnets;

    const selectedSubnets = subnets.slice(0, 2);

    const domain = new oss.Domain(this, 'OpenSearchDomain', {
      vpc,
      vpcSubnets: [{ subnets: selectedSubnets }],
      version: oss.EngineVersion.OPENSEARCH_2_19,
      nodeToNodeEncryption: true,
      encryptionAtRest: {
        enabled: true,
      },
      zoneAwareness: {
        enabled: true,
        availabilityZoneCount: 2,
      },
      enforceHttps: true,
      useUnsignedBasicAuth: false,
      accessPolicies: [openSearchPolicy],
      ebs: {
        volumeSize: 128,
      },
      capacity: {
        masterNodes: 3,
        masterNodeInstanceType: 'r6g.large.search',
        dataNodes: 4,
        dataNodeInstanceType: 'r6g.large.search',
        multiAzWithStandbyEnabled: false,
      },
      securityGroups: [securityGroup],
      removalPolicy: isProd
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
      logging: {
        slowSearchLogEnabled: true,
        slowSearchLogGroup: searchSlowLogsGroup,
        slowIndexLogEnabled: true,
        slowIndexLogGroup: indexSlowLogsGroup,
        appLogEnabled: true,
        appLogGroup: new logs.LogGroup(this, 'AppLogs', {
          retention: logs.RetentionDays.ONE_MONTH,
          removalPolicy: isProd
            ? cdk.RemovalPolicy.RETAIN
            : cdk.RemovalPolicy.DESTROY,
        }),
      },
    });

    domain.connections.allowFrom(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(443),
      'Allow OpenSearch HTTPS port from the VPC',
    );
    domain.connections.allowFrom(
      securityGroup,
      ec2.Port.tcp(443),
      'Allow OpenSearch HTTPS port from the security group',
    );
    domain.connections.allowFrom(
      securityGroup,
      ec2.Port.tcpRange(9200, 9300),
      'Allow OpenSearch service ports from the security group',
    );
    domain.connections.allowFrom(
      securityGroup,
      ec2.Port.tcp(5601),
      'Allow OpenSearch dashboard port from the security group',
    );

    return domain;
  }

  /**
   * Create security group for OpenSearch domain
   */
  private createSecurityGroup(vpc: ec2.IVpc): ec2.SecurityGroup {
    const securityGroup = new ec2.SecurityGroup(
      this,
      'OpenSearchSecurityGroup',
      {
        vpc,
        allowAllOutbound: false,
        description: 'Security group for OpenSearch Domain',
      },
    );
    securityGroup.addEgressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'Allow HTTPS outbound traffic',
    );
    securityGroup.addEgressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.udp(53),
      'Allow DNS (UDP) outbound traffic',
    );
    securityGroup.addEgressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(53),
      'Allow DNS (TCP) outbound traffic',
    );

    return securityGroup;
  }
}
