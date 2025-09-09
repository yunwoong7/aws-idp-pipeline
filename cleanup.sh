#!/bin/bash

# AWS IDP AI Pipeline - Cleanup Starter Script
# This script deploys a CodeBuild project to perform the cleanup

set -e

STAGE="dev"
FORCE_RECREATE=false

# Additional cleanup functions
cleanup_dynamodb_tables() {
    echo ""
    echo "🗑️  Manual DynamoDB cleanup"
    echo "=================================="
    echo ""
    
    echo "Listing aws-idp-ai DynamoDB tables..."
    TABLES=$(aws dynamodb list-tables --output text --query 'TableNames' | grep 'aws-idp-ai' | tr '\t' '\n' || echo "")
    
    if [ -z "$TABLES" ]; then
        echo "✅ No aws-idp-ai DynamoDB tables found"
        return 0
    fi
    
    echo "Found tables:"
    echo "$TABLES"
    echo ""
    
    read -p "Do you want to delete these tables? (y/N): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for table in $TABLES; do
            if [ -n "$table" ]; then
                echo "Processing table: $table"
                
                # Disable deletion protection
                echo "  Disabling deletion protection..."
                aws dynamodb update-table --table-name "$table" --deletion-protection-enabled=false 2>/dev/null || echo "  Could not disable deletion protection (may not be enabled)"
                
                # Delete table
                echo "  Deleting table..."
                if aws dynamodb delete-table --table-name "$table" 2>&1; then
                    echo "  ✅ Table $table deletion initiated"
                else
                    echo "  ❌ Could not delete table $table"
                fi
                echo ""
            fi
        done
        
        echo "Waiting 30 seconds for deletions to process..."
        sleep 30
        
        echo "Checking remaining tables..."
        REMAINING=$(aws dynamodb list-tables --output text --query 'TableNames' | grep 'aws-idp-ai' || echo "")
        if [ -z "$REMAINING" ]; then
            echo "✅ All DynamoDB tables deleted successfully"
        else
            echo "⚠️  Some tables may still exist:"
            echo "$REMAINING"
        fi
    else
        echo "DynamoDB cleanup cancelled"
    fi
}

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --stage) STAGE="$2"; shift ;;
        --force) FORCE_RECREATE=true ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --stage STAGE   Stage to clean up (dev/prod)"
            echo "  --force         Force recreate cleanup project"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo ""
echo "========================================="
echo "  AWS IDP AI Pipeline - Cleanup Starter"
echo "========================================="
echo "Stage: $STAGE"
echo ""

# Interactive cleanup menu
echo "Please select cleanup option:"
echo "(Note: For complete cleanup, run option 1 first, then run option 2)"
echo ""
echo "1) Infrastructure Cleanup"
echo "   - Remove main AWS infrastructure (S3, ECR, CloudWatch, CDK stacks, etc.)"
echo "   - Uses CodeBuild for comprehensive resource deletion"
echo "   - Takes 30-60 minutes to complete"
echo ""
echo "2) Remaining Resources Cleanup"
echo "   - Delete remaining DynamoDB tables"
echo "   - Remove Amazon Cognito User Pools"
echo "   - Delete cleanup CodeBuild stack"
echo "   - Final cleanup of leftover resources"
echo ""

while true; do
    read -p "Enter your choice (1 or 2): " choice
    case $choice in
        1)
            echo ""
            echo "🏗️  Selected: Infrastructure Cleanup"
            CLEANUP_STEP="1"
            break
            ;;
        2)
            echo ""
            echo "🗑️  Selected: Remaining Resources Cleanup"
            CLEANUP_STEP="2"
            break
            ;;
        *)
            echo "Invalid choice. Please enter 1 or 2."
            ;;
    esac
done

# Handle step-based execution
if [ "$CLEANUP_STEP" = "2" ]; then
    echo "============================================="
    echo ""
    
    # Check and delete Cognito User Pools
    echo "🔍 Checking for Amazon Cognito User Pools..."
    USER_POOLS=$(aws cognito-idp list-user-pools --max-results 60 --query 'UserPools[?contains(Name, `aws-idp-ai`)].Id' --output text || echo "")
    
    if [ -n "$USER_POOLS" ] && [ "$USER_POOLS" != "None" ]; then
        echo "Found Cognito User Pools:"
        for pool_id in $USER_POOLS; do
            POOL_NAME=$(aws cognito-idp describe-user-pool --user-pool-id "$pool_id" --query 'UserPool.Name' --output text 2>/dev/null || echo "Unknown")
            echo "  - $pool_id ($POOL_NAME)"
        done
        echo ""
        
        read -p "Do you want to delete these Cognito User Pools? (y/N): " -n 1 -r
        echo ""
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            for pool_id in $USER_POOLS; do
                echo "Deleting Cognito User Pool: $pool_id"
                aws cognito-idp delete-user-pool --user-pool-id "$pool_id" 2>/dev/null && echo "  ✅ Deleted" || echo "  ❌ Failed to delete"
            done
        else
            echo "Cognito User Pool deletion skipped"
        fi
    else
        echo "✅ No Cognito User Pools found with 'aws-idp-ai' in name"
    fi
    echo ""
    
    # DynamoDB cleanup
    cleanup_dynamodb_tables
    
    echo ""
    echo "🗑️  Deleting cleanup CodeBuild stack..."
    CLEANUP_STACK="aws-idp-ai-cleanup-codebuild-${STAGE}"
    if aws cloudformation describe-stacks --stack-name "$CLEANUP_STACK" >/dev/null 2>&1; then
        echo "Deleting cleanup stack: $CLEANUP_STACK"
        aws cloudformation delete-stack --stack-name "$CLEANUP_STACK"
        echo "✅ Cleanup stack deletion initiated"
        echo ""
        echo "You can monitor the deletion with:"
        echo "  aws cloudformation describe-stacks --stack-name $CLEANUP_STACK"
    else
        echo "✅ Cleanup stack $CLEANUP_STACK not found or already deleted"
    fi
    echo ""
    echo "✅ Remaining Resources Cleanup completed!"
    exit 0
fi

# Check if cleanup CodeBuild project exists
CLEANUP_PROJECT="aws-idp-ai-cleanup-${STAGE}"
CLEANUP_STACK="aws-idp-ai-cleanup-codebuild-${STAGE}"

# Check if stack exists first
STACK_EXISTS=$(aws cloudformation describe-stacks --stack-name "$CLEANUP_STACK" 2>/dev/null || echo "")

if [ -n "$STACK_EXISTS" ]; then
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name "$CLEANUP_STACK" --query 'Stacks[0].StackStatus' --output text 2>/dev/null)
    echo "Cleanup stack exists with status: $STACK_STATUS"
    
    if [ "$FORCE_RECREATE" == "true" ] || [ "$STACK_STATUS" != "CREATE_COMPLETE" ] && [ "$STACK_STATUS" != "UPDATE_COMPLETE" ]; then
        echo "Deleting existing stack and recreating..."
        aws cloudformation delete-stack --stack-name "$CLEANUP_STACK"
        echo "Waiting for stack deletion..."
        aws cloudformation wait stack-delete-complete --stack-name "$CLEANUP_STACK" 2>/dev/null || true
        STACK_EXISTS=""
    fi
fi

# Create stack if it doesn't exist or was deleted
if [ -z "$STACK_EXISTS" ]; then
    echo "Creating cleanup CodeBuild project..."
    aws cloudformation create-stack \
        --stack-name "$CLEANUP_STACK" \
        --template-body file://cleanup-codebuild.yml \
        --parameters ParameterKey=Stage,ParameterValue="$STAGE" \
        --capabilities CAPABILITY_NAMED_IAM
    
    echo "Waiting for cleanup project to be created..."
    aws cloudformation wait stack-create-complete --stack-name "$CLEANUP_STACK"
    echo "✅ Cleanup project created successfully"
fi

# Verify project exists before starting build
if ! aws codebuild batch-get-projects --names "$CLEANUP_PROJECT" >/dev/null 2>&1; then
    echo "❌ CodeBuild project still not found after creation. Check the stack in AWS Console."
    exit 1
fi

echo ""
echo "Starting cleanup process..."
BUILD_ID=$(aws codebuild start-build --project-name "$CLEANUP_PROJECT" --query 'build.id' --output text)

echo "✅ Infrastructure Cleanup started!"
echo "Build ID: $BUILD_ID"
echo ""
echo "You can monitor the progress using:"
echo "  aws logs tail /aws/codebuild/$CLEANUP_PROJECT --follow"
echo ""
echo "Or check in AWS Console:"
echo "  CodeBuild > Build projects > $CLEANUP_PROJECT"
echo ""
echo "The cleanup will take 30-60 minutes to complete (OpenSearch deletion takes ~30 minutes)."
echo ""
echo "📝 Commands for monitoring:"
echo ""
echo "Check cleanup status:"
echo "  aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].buildStatus' --output text"
echo ""
echo "View logs in real-time:"
echo "  aws logs tail /aws/codebuild/$CLEANUP_PROJECT --follow"
echo ""
echo "After Infrastructure Cleanup completes (SUCCEEDED status), run this script again and select option 2:"
echo "  ./cleanup.sh --stage $STAGE"

