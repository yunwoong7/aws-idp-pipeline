#!/bin/bash

# AWS IDP AI Pipeline - Cleanup Starter Script
# This script deploys a CodeBuild project to perform the cleanup

set -e

STAGE="dev"
FORCE_RECREATE=false

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --stage) STAGE="$2"; shift ;;
        --force) FORCE_RECREATE=true ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --stage STAGE    Stage to clean up (dev/prod)"
            echo "  --force          Force recreate cleanup project"
            echo "  --help           Show this help message"
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

echo "✅ Cleanup started!"
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

# Ask user preference
read -p "Do you want to wait for completion? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Monitoring cleanup progress (checking every 5 minutes)..."
    echo ""
    
    # Wait for build to complete with longer intervals
    WAIT_COUNT=0
    MAX_WAIT=36  # 36 * 5 minutes = 3 hours max (matching CodeBuild timeout)
    
    while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
        BUILD_STATUS=$(aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].buildStatus' --output text 2>/dev/null)
        
        if [ "$BUILD_STATUS" = "IN_PROGRESS" ]; then
            WAIT_COUNT=$((WAIT_COUNT + 1))
            echo "[$((WAIT_COUNT * 5)) minutes] Still running... (Status: $BUILD_STATUS)"
            sleep 300  # 5 minutes
        elif [ "$BUILD_STATUS" = "SUCCEEDED" ]; then
            echo ""
            echo "✅ Cleanup successful after ~$((WAIT_COUNT * 5)) minutes!"
            echo "Now deleting the cleanup stack itself..."
            aws cloudformation delete-stack --stack-name $CLEANUP_STACK
            echo "✅ Cleanup stack deletion initiated"
            break
        elif [ "$BUILD_STATUS" = "FAILED" ] || [ "$BUILD_STATUS" = "STOPPED" ]; then
            echo ""
            echo "❌ Cleanup $BUILD_STATUS. Check the logs in CodeBuild console."
            echo "To manually delete the cleanup stack, run:"
            echo "  aws cloudformation delete-stack --stack-name $CLEANUP_STACK"
            break
        fi
    done
    
    if [ $WAIT_COUNT -eq $MAX_WAIT ]; then
        echo "⏱️  Timeout after 3 hours. Check status manually in CodeBuild console."
    fi
else
    echo ""
    echo "📝 Commands for later:"
    echo ""
    echo "Check cleanup status:"
    echo "  aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].buildStatus' --output text"
    echo ""
    echo "After cleanup completes, delete the cleanup stack:"
    echo "  aws cloudformation delete-stack --stack-name $CLEANUP_STACK"
    echo ""
    echo "Or run this one-liner to check and delete if successful:"
    echo "  [ \$(aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].buildStatus' --output text) = 'SUCCEEDED' ] && aws cloudformation delete-stack --stack-name $CLEANUP_STACK && echo 'Cleanup stack deleted' || echo 'Build not yet successful'"
fi