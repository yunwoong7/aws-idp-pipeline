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

# Placeholder for any helper functions if needed later

# Delete stacks in reverse order of dependencies
echo ""
echo "Step 1: Pre-emptively emptying ALL S3 buckets and ECR repositories..."

# Empty and delete all S3 buckets
echo "Emptying and deleting S3 buckets..."
ALL_BUCKETS=$(aws s3api list-buckets --query 'Buckets[?contains(Name, `aws-idp`)].Name' --output text 2>/dev/null)

for bucket in $ALL_BUCKETS; do
    echo -n "Force deleting bucket: $bucket... "
    # Delete all objects including versions (suppress output)
    aws s3 rm s3://${bucket} --recursive >/dev/null 2>&1
    # Delete all object versions (for versioned buckets) - suppress output
    aws s3api delete-objects --bucket ${bucket} \
        --delete "$(aws s3api list-object-versions --bucket ${bucket} --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" >/dev/null 2>&1 || true
    # Delete all delete markers - suppress output
    aws s3api delete-objects --bucket ${bucket} \
        --delete "$(aws s3api list-object-versions --bucket ${bucket} --query='{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" >/dev/null 2>&1 || true
    # Delete the bucket itself
    aws s3 rb s3://${bucket} --force >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Done"
    else
        echo "⚠️ Failed to delete bucket"
    fi
done

# Force delete all ECR repositories with images
echo "Force deleting ECR repositories..."
ECR_REPOS=$(aws ecr describe-repositories --query 'repositories[?contains(repositoryName, `aws-idp`)].repositoryName' --output text 2>/dev/null)
for repo in $ECR_REPOS; do
    echo -n "Force deleting ECR repository: $repo... "
    aws ecr delete-repository --repository-name $repo --force >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Done"
    else
        echo "⚠️ Failed"
    fi
done

# Delete AWS Certificate Manager certificates
echo "Deleting ACM certificates..."
ACM_CERTS=$(aws acm list-certificates --query 'CertificateSummaryList[?contains(DomainName, `aws-idp-ai`) || DomainName==`aws-idp-ai.internal`].CertificateArn' --output text 2>/dev/null)
for cert_arn in $ACM_CERTS; do
    echo -n "Deleting ACM certificate: $cert_arn... "
    aws acm delete-certificate --certificate-arn "$cert_arn" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Done"
    else
        echo "⚠️ Failed (may be in use)"
    fi
done

echo ""
echo "Step 2: Deleting all CloudFormation stacks..."

# List of all stacks in dependency order (reverse for deletion)
STACKS=(
    "aws-idp-ai-ecs"
    "aws-idp-ai-ecs-${STAGE}"
    "aws-idp-ai-api-gateway"
    "aws-idp-ai-websocket-api"
    "aws-idp-ai-indices-management"
    "aws-idp-ai-document-management"
    "aws-idp-ai-workflow"
    "aws-idp-ai-workflow-${STAGE}"
    "aws-idp-ai-cognito"
    "aws-idp-ai-cognito-${STAGE}"
    "aws-idp-ai-dynamodb-streams"
    "aws-idp-ai-opensearch"
    "aws-idp-ai-s3"
    "aws-idp-ai-dynamodb"
    "aws-idp-ai-lambda-layer"
    "aws-idp-ai-ecr"
    "aws-idp-ai-vpc"
)

# Delete each stack
for stack in "${STACKS[@]}"; do
    # Check if stack exists
    aws cloudformation describe-stacks --stack-name $stack >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "Deleting stack: $stack"
        aws cloudformation delete-stack --stack-name $stack 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "  ✅ Deletion initiated for $stack"
        else
            echo "  ⚠️ Failed to initiate deletion for $stack"
        fi
    else
        echo "Stack $stack does not exist, skipping..."
    fi
done

echo ""
echo "Waiting for stack deletions to complete..."
echo "This may take 15-20 minutes (OpenSearch deletion can be slow)..."

# Wait for all stacks to be deleted (with extended timeout)
TIMEOUT=1800  # 30 minutes (OpenSearch can take 15+ minutes)
ELAPSED=0
LAST_STATUS_CHECK=0

while [ $ELAPSED -lt $TIMEOUT ]; do
    REMAINING_STACKS=""
    for stack in "${STACKS[@]}"; do
        aws cloudformation describe-stacks --stack-name $stack >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            STATUS=$(aws cloudformation describe-stacks --stack-name $stack --query 'Stacks[0].StackStatus' --output text 2>/dev/null)
            REMAINING_STACKS="$REMAINING_STACKS $stack"
            
            # Special handling for OpenSearch
            if [[ "$stack" == *"opensearch"* ]] && [ "$STATUS" == "DELETE_IN_PROGRESS" ]; then
                if [ $((ELAPSED - LAST_STATUS_CHECK)) -ge 60 ]; then
                    echo ""
                    echo "  ⏳ OpenSearch stack is still deleting (this can take 15+ minutes)..."
                    LAST_STATUS_CHECK=$ELAPSED
                fi
            elif [ "$STATUS" != "DELETE_IN_PROGRESS" ] && [ "$STATUS" != "DELETE_COMPLETE" ]; then
                echo ""
                echo "  ⚠️ Stack $stack is in status: $STATUS"
            fi
        fi
    done
    
    if [ -z "$REMAINING_STACKS" ]; then
        echo ""
        echo "✅ All stacks deleted successfully"
        break
    fi
    
    # Show progress with elapsed time every minute
    if [ $((ELAPSED % 60)) -eq 0 ] && [ $ELAPSED -gt 0 ]; then
        echo -n " [${ELAPSED}s elapsed]"
    else
        echo -n "."
    fi
    
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo ""
    echo "⚠️ Timeout after 30 minutes. Remaining stacks: $REMAINING_STACKS"
    echo "   You may need to check these stacks manually in the AWS Console."
fi

echo ""
echo "Step 3: Cleaning up CDK bootstrap resources..."

# Get account and region info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")

# Delete CDK bootstrap stack
echo "Deleting CDKToolkit stack..."
aws cloudformation delete-stack --stack-name CDKToolkit 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ CDKToolkit stack deletion initiated"
fi

# Manually clean up CDK bootstrap resources
echo "Cleaning up CDK S3 bucket..."
CDK_BUCKET="cdk-hnb659fds-assets-${ACCOUNT_ID}-${REGION}"
aws s3 rm s3://$CDK_BUCKET --recursive 2>/dev/null
aws s3 rb s3://$CDK_BUCKET 2>/dev/null

echo "Cleaning up CDK ECR repository..."
CDK_ECR="cdk-hnb659fds-container-assets-${ACCOUNT_ID}-${REGION}"
aws ecr delete-repository --repository-name $CDK_ECR --force 2>/dev/null

echo ""
echo "Step 4: Deleting CodeBuild deployment stack..."
aws cloudformation delete-stack --stack-name "aws-idp-ai-codebuild-deploy-${STAGE}" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ CodeBuild stack deletion initiated"
fi

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