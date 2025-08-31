#!/bin/bash

echo ""
echo "==========================================================================="
echo "  🗑️  AWS IDP AI Pipeline - Cleanup Script                                "
echo "---------------------------------------------------------------------------"
echo "  This script will remove all resources created by the deployment         "
echo "==========================================================================="
echo ""

STAGE="dev"

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --stage) STAGE="$2"; shift ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --stage STAGE    Stage to clean up (dev/prod)"
            echo "  --help           Show this help message"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo "Stage to clean up: $STAGE"
echo ""
echo "⚠️  WARNING: This will delete ALL resources for the $STAGE environment"
echo "   including:"
echo "   - ECS services and tasks"
echo "   - Lambda functions"
echo "   - DynamoDB tables (and all data)"
echo "   - S3 buckets (and all files)"
echo "   - OpenSearch domain"
echo "   - Cognito user pool"
echo "   - VPC and networking resources"
echo "   - CodeBuild project"
echo "   - DynamoDB tables (and all data)"
echo "   - CloudWatch Log Groups"
echo "   - CDK bootstrap resources (S3 bucket, ECR repo, IAM roles)"
echo "   - All related CloudFormation stacks"
echo ""

while true; do
    read -p "Are you sure you want to continue? Type 'DELETE' to confirm: " answer
    if [[ "$answer" == "DELETE" ]]; then
        echo "Starting cleanup..."
        break
    else
        echo "Cleanup cancelled."
        exit 0
    fi
done

# Function to forcefully stop and delete ECS services
force_delete_ecs_services() {
    local cluster_name="$1"
    echo "Forcing deletion of ECS services in cluster: $cluster_name"
    
    # Get all services in the cluster
    local services=$(aws ecs list-services --cluster $cluster_name --query 'serviceArns[]' --output text 2>/dev/null)
    
    for service_arn in $services; do
        local service_name=$(basename $service_arn)
        echo "  Stopping service: $service_name"
        
        # Update service to 0 desired count
        aws ecs update-service --cluster $cluster_name --service $service_name --desired-count 0 2>/dev/null
        
        # Wait for tasks to stop
        aws ecs wait services-stable --cluster $cluster_name --services $service_name 2>/dev/null
        
        # Delete service
        aws ecs delete-service --cluster $cluster_name --service $service_name --force 2>/dev/null
        echo "  ✅ Service deleted: $service_name"
    done
}

# Function to delete a stack with retries and ECS force cleanup
delete_stack() {
    local stack_name=$1
    local max_attempts=3
    local attempt=1
    
    echo "Deleting stack: $stack_name"
    
    # If this is an ECS stack, force cleanup first
    if [[ "$stack_name" == *"ecs"* ]]; then
        echo "  Pre-cleaning ECS resources..."
        force_delete_ecs_services "aws-idp-ai-cluster" 2>/dev/null || true
        force_delete_ecs_services "aws-idp-ai-ecs-cluster" 2>/dev/null || true
    fi
    
    while [ $attempt -le $max_attempts ]; do
        aws cloudformation delete-stack --stack-name $stack_name 2>/dev/null
        
        if [ $? -eq 0 ]; then
            echo "Delete initiated for $stack_name"
            
            # Wait for deletion
            echo "Waiting for deletion to complete..."
            aws cloudformation wait stack-delete-complete --stack-name $stack_name 2>/dev/null
            
            if [ $? -eq 0 ]; then
                echo "✅ $stack_name deleted successfully"
                return 0
            fi
        fi
        
        # Check if stack exists
        aws cloudformation describe-stacks --stack-name $stack_name &>/dev/null
        if [ $? -ne 0 ]; then
            echo "✅ $stack_name does not exist or already deleted"
            return 0
        fi
        
        echo "Attempt $attempt failed. Retrying..."
        attempt=$((attempt + 1))
        sleep 10
    done
    
    echo "⚠️  Failed to delete $stack_name after $max_attempts attempts"
    return 1
}

# Delete stacks in reverse order of dependencies
echo ""
echo "Step 1: Deleting service stacks..."
delete_stack "aws-idp-ai-ecs-${STAGE}"
delete_stack "aws-idp-ai-ecs"  # Try without stage suffix
delete_stack "aws-idp-ai-document-management"
delete_stack "aws-idp-ai-step-functions"
delete_stack "aws-idp-ai-workflow-${STAGE}"
delete_stack "aws-idp-ai-workflow"

echo ""
echo "Step 2: Deleting authentication stack..."
delete_stack "aws-idp-ai-cognito-${STAGE}"
delete_stack "aws-idp-ai-cognito"

echo ""
echo "Step 3: Deleting data stacks..."

# Empty S3 buckets before deletion
echo "Emptying S3 buckets..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)
BUCKET_NAME="aws-idp-ai-documents-${ACCOUNT_ID}-${REGION}"

aws s3 rm s3://${BUCKET_NAME} --recursive 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ S3 bucket emptied: $BUCKET_NAME"
fi

delete_stack "aws-idp-ai-opensearch"
delete_stack "aws-idp-ai-s3"
delete_stack "aws-idp-ai-dynamodb"

echo ""
echo "Step 4: Deleting network stack..."
delete_stack "aws-idp-ai-vpc"

echo ""
echo "Step 5: Deleting ECR repositories..."
aws ecr delete-repository --repository-name aws-idp-ai-backend --force 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ ECR repository deleted: aws-idp-ai-backend"
fi

aws ecr delete-repository --repository-name aws-idp-ai-frontend --force 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ ECR repository deleted: aws-idp-ai-frontend"
fi

echo ""
echo "Step 6: Deleting additional ECR repositories..."
# Delete any additional ECR repositories that might have been created
ECR_REPOS=$(aws ecr describe-repositories --query 'repositories[?contains(repositoryName, `aws-idp-ai`)].repositoryName' --output text)
for repo in $ECR_REPOS; do
    echo "Deleting ECR repository: $repo"
    aws ecr delete-repository --repository-name $repo --force 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ ECR repository deleted: $repo"
    fi
done

echo ""
echo "Step 7: Deleting DynamoDB tables..."
echo "Deleting any remaining DynamoDB tables..."
TABLES=$(aws dynamodb list-tables --query 'TableNames[]' --output text | tr '\t' '\n' | grep 'aws-idp-ai')
for table in $TABLES; do
    echo "Deleting table: $table"
    aws dynamodb delete-table --table-name $table 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Table deleted: $table"
    fi
done

echo ""
echo "Step 8: Deleting CloudWatch Log Groups..."
echo "Deleting log groups..."
LOG_GROUPS=$(aws logs describe-log-groups --query 'logGroups[?contains(logGroupName, `aws-idp-ai`) || contains(logGroupName, `/aws/codebuild/aws-idp-ai`)].logGroupName' --output text)
for log_group in $LOG_GROUPS; do
    echo "Deleting log group: $log_group"
    aws logs delete-log-group --log-group-name "$log_group" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Log group deleted: $log_group"
    fi
done

echo ""
echo "Step 9: Cleaning up CDK bootstrap resources..."
echo "Deleting CDK bootstrap resources..."

# Get account and region info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")

# Delete CDK S3 bucket
CDK_S3_BUCKET="cdk-hnb659fds-assets-${ACCOUNT_ID}-${REGION}"
echo "Checking for CDK S3 bucket: $CDK_S3_BUCKET"
aws s3 ls s3://$CDK_S3_BUCKET >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Emptying and deleting CDK S3 bucket: $CDK_S3_BUCKET"
    aws s3 rm s3://$CDK_S3_BUCKET --recursive 2>/dev/null
    aws s3 rb s3://$CDK_S3_BUCKET 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ CDK S3 bucket deleted: $CDK_S3_BUCKET"
    fi
fi

# Delete CDK ECR repository
CDK_ECR_REPO="cdk-hnb659fds-container-assets-${ACCOUNT_ID}-${REGION}"
echo "Deleting CDK ECR repository: $CDK_ECR_REPO"
aws ecr delete-repository --repository-name $CDK_ECR_REPO --force 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ CDK ECR repository deleted: $CDK_ECR_REPO"
fi

# Delete CDK IAM roles
CDK_ROLES=(
    "cdk-hnb659fds-file-publishing-role-${ACCOUNT_ID}-${REGION}"
    "cdk-hnb659fds-image-publishing-role-${ACCOUNT_ID}-${REGION}"
    "cdk-hnb659fds-lookup-role-${ACCOUNT_ID}-${REGION}"
    "cdk-hnb659fds-cfn-exec-role-${ACCOUNT_ID}-${REGION}"
)

for role in "${CDK_ROLES[@]}"; do
    echo "Deleting CDK IAM role: $role"
    # Detach policies first
    aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null | xargs -n1 aws iam detach-role-policy --role-name $role --policy-arn 2>/dev/null
    # Delete inline policies
    aws iam list-role-policies --role-name $role --query 'PolicyNames[]' --output text 2>/dev/null | xargs -n1 aws iam delete-role-policy --role-name $role --policy-name 2>/dev/null
    # Delete role
    aws iam delete-role --role-name $role 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ CDK IAM role deleted: $role"
    fi
done

# Delete CDKToolkit stack
delete_stack "CDKToolkit"

echo ""
echo "Step 10: Deleting CodeBuild deployment stack..."
delete_stack "aws-idp-ai-codebuild-deploy-${STAGE}"

echo ""
echo "==========================================================================="
echo "  Cleanup Summary                                                         "
echo "---------------------------------------------------------------------------"

# Check remaining stacks
remaining=$(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[?contains(StackName, 'aws-idp-ai')].StackName" --output text)

if [ -z "$remaining" ]; then
    echo "  ✅ All AWS IDP AI resources have been deleted successfully"
else
    echo "  ⚠️  The following stacks may still exist:"
    echo "$remaining" | tr '\t' '\n' | sed 's/^/     - /'
    echo ""
    echo "  You may need to delete these manually in the AWS Console"
fi

echo ""
echo "==========================================================================="

# Clean up local deployment info file
if [ -f "deployment-info-${STAGE}.json" ]; then
    rm "deployment-info-${STAGE}.json"
    echo "Local deployment info file removed"
fi