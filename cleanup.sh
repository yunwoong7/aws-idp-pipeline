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

# Empty all S3 buckets first
echo "Emptying S3 buckets..."
ALL_BUCKETS=$(aws s3api list-buckets --query 'Buckets[?contains(Name, `aws-idp`)].Name' --output text 2>/dev/null)

for bucket in $ALL_BUCKETS; do
    echo -n "Force emptying bucket: $bucket... "
    # Delete all objects including versions (suppress output)
    aws s3 rm s3://${bucket} --recursive >/dev/null 2>&1
    # Delete all object versions (for versioned buckets) - suppress output
    aws s3api delete-objects --bucket ${bucket} \
        --delete "$(aws s3api list-object-versions --bucket ${bucket} --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" >/dev/null 2>&1 || true
    # Delete all delete markers - suppress output
    aws s3api delete-objects --bucket ${bucket} \
        --delete "$(aws s3api list-object-versions --bucket ${bucket} --query='{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" >/dev/null 2>&1 || true
    echo "✅ Done"
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

echo ""
echo "Step 2: Deleting all CDK stacks..."
# Navigate to infra directory and run CDK destroy
CURRENT_DIR=$(pwd)
cd packages/infra 2>/dev/null || cd ../packages/infra 2>/dev/null || cd ../../packages/infra 2>/dev/null || {
    echo "Could not find packages/infra directory"
    exit 1
}

# Install necessary dependencies if needed
if ! command -v tsx >/dev/null 2>&1; then
    echo "Installing required dependencies..."
    npm install tsx --save-dev 2>/dev/null || pnpm add -D tsx 2>/dev/null || true
fi

# Create .toml file if it doesn't exist
if [ ! -f ".toml" ]; then
    echo "Creating .toml configuration..."
    cat > .toml << 'EOF'
[app]
ns = "aws-idp-ai"
stage = "dev"
EOF
fi

# Destroy all CDK stacks
echo "Running CDK destroy --all..."
npx cdk destroy --all --force

cd "$CURRENT_DIR"

echo ""
echo "Step 3: Cleaning up CDK bootstrap..."
cd packages/infra 2>/dev/null || cd ../packages/infra 2>/dev/null || cd ../../packages/infra 2>/dev/null || {
    echo "Could not find packages/infra directory for bootstrap cleanup"
}

echo "Running cdk bootstrap --cleanup..."
npx cdk bootstrap --cleanup

cd "$CURRENT_DIR"

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