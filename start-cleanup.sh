#!/bin/bash

# AWS IDP AI Pipeline - Cleanup Starter Script
# This script deploys a CodeBuild project to perform the cleanup

set -e

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

echo ""
echo "========================================="
echo "  AWS IDP AI Pipeline - Cleanup Starter"
echo "========================================="
echo "Stage: $STAGE"
echo ""

# Check if cleanup CodeBuild project exists
CLEANUP_PROJECT="aws-idp-ai-cleanup-${STAGE}"
if aws codebuild batch-get-projects --names "$CLEANUP_PROJECT" >/dev/null 2>&1; then
    echo "Cleanup CodeBuild project already exists: $CLEANUP_PROJECT"
else
    echo "Creating cleanup CodeBuild project..."
    aws cloudformation create-stack \
        --stack-name "aws-idp-ai-cleanup-codebuild-${STAGE}" \
        --template-body file://cleanup-codebuild.yml \
        --parameters ParameterKey=Stage,ParameterValue="$STAGE" \
        --capabilities CAPABILITY_NAMED_IAM
    
    echo "Waiting for cleanup project to be created..."
    aws cloudformation wait stack-create-complete --stack-name "aws-idp-ai-cleanup-codebuild-${STAGE}"
    echo "✅ Cleanup project created successfully"
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
echo "The cleanup will take 15-30 minutes to complete."