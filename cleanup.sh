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

# Function to delete a stack with retries
delete_stack() {
    local stack_name=$1
    local max_attempts=3
    local attempt=1
    
    echo "Deleting stack: $stack_name"
    
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
echo "Step 6: Deleting CodeBuild stack..."
delete_stack "aws-idp-ai-codebuild-deploy-${STAGE}"

echo ""
echo "Step 7: Cleaning up CDK bootstrap resources (optional)..."
echo "Note: This will only clean if no other CDK apps are using bootstrap"
# Uncomment if you want to clean CDK bootstrap
# delete_stack "CDKToolkit"

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