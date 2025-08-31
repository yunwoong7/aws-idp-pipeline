#!/bin/bash

echo ""
echo "==========================================================================="
echo "  🚀 AWS IDP AI Pipeline - Automated Deployment                           "
echo "---------------------------------------------------------------------------"
echo "  This script will deploy the AWS IDP AI Pipeline using CloudShell        "
echo "  and CodeBuild for a seamless deployment experience.                     "
echo ""
echo "  📋 Prerequisites:                                                        "
echo "     - AWS CLI configured with appropriate permissions                     "
echo "     - Bedrock models enabled in us-east-1 region                         "
echo "     - Valid email address for Cognito admin user                         "
echo ""
echo "  🔧 Features:                                                             "
echo "     - Cognito authentication (mandatory for security)                     "
echo "     - Self-signed HTTPS certificates                                      "
echo "     - Automatic container builds and deployments                          "
echo "     - Cross-platform compatibility (Windows/Mac/Linux)                    "
echo "==========================================================================="
echo ""

# Default parameters
STAGE="dev"
ENABLE_COGNITO="true"
USE_CUSTOM_DOMAIN="false"
DOMAIN_NAME=""
HOSTED_ZONE_NAME=""
REPO_URL="https://github.com/yunwoong7/aws-idp-pipeline.git"
VERSION="main"

# Function to prompt for email with validation
prompt_for_email() {
    while true; do
        read -p "Enter admin user email address: " ADMIN_USER_EMAIL
        if [[ "$ADMIN_USER_EMAIL" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
            break
        else
            echo "Invalid email format. Please enter a valid email address."
        fi
    done
}

# Function to prompt for stage
prompt_for_stage() {
    echo "Select deployment stage:"
    echo "1) dev (default)"
    echo "2) prod"
    read -p "Enter choice [1-2]: " choice
    case $choice in
        2) STAGE="prod" ;;
        *) STAGE="dev" ;;
    esac
}

# Function to prompt for custom domain
prompt_for_custom_domain() {
    read -p "Do you want to use a custom domain? (y/N): " answer
    case ${answer:0:1} in
        y|Y )
            USE_CUSTOM_DOMAIN="true"
            read -p "Enter domain name (e.g., idp-ai): " DOMAIN_NAME
            read -p "Enter hosted zone name (e.g., example.com): " HOSTED_ZONE_NAME
            ;;
        * )
            USE_CUSTOM_DOMAIN="false"
            echo "Using self-signed certificate with ALB DNS name"
            ;;
    esac
}

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --admin-email) ADMIN_USER_EMAIL="$2"; shift ;;
        --stage) STAGE="$2"; shift ;;
        --disable-cognito) ENABLE_COGNITO="false" ;;
        --use-custom-domain) USE_CUSTOM_DOMAIN="true" ;;
        --domain-name) DOMAIN_NAME="$2"; shift ;;
        --hosted-zone-name) HOSTED_ZONE_NAME="$2"; shift ;;
        --repo-url) REPO_URL="$2"; shift ;;
        --version) VERSION="$2"; shift ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --admin-email EMAIL         Admin user email for Cognito"
            echo "  --stage STAGE              Deployment stage (dev/prod)"
            echo "  --disable-cognito          Disable Cognito authentication"
            echo "  --use-custom-domain        Use custom domain"
            echo "  --domain-name NAME         Custom domain name"
            echo "  --hosted-zone-name ZONE    Route53 hosted zone"
            echo "  --repo-url URL             Repository URL"
            echo "  --version VERSION          Branch or tag to deploy"
            echo "  --help                     Show this help message"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Interactive prompts if not provided via arguments
if [[ -z "$ADMIN_USER_EMAIL" ]]; then
    prompt_for_email
fi

if [[ "$USE_CUSTOM_DOMAIN" == "false" && -z "$DOMAIN_NAME" ]]; then
    prompt_for_custom_domain
fi

# Display configuration
echo ""
echo "Configuration:"
echo "--------------"
echo "Admin Email: $ADMIN_USER_EMAIL"
echo "Stage: $STAGE"
echo "Cognito: $ENABLE_COGNITO"
echo "Custom Domain: $USE_CUSTOM_DOMAIN"
if [[ "$USE_CUSTOM_DOMAIN" == "true" ]]; then
    echo "Domain Name: $DOMAIN_NAME"
    echo "Hosted Zone: $HOSTED_ZONE_NAME"
fi
echo "Repository: $REPO_URL"
echo "Version: $VERSION"
echo ""

# Confirm deployment
while true; do
    read -p "Do you want to proceed with deployment? (y/N): " answer
    case ${answer:0:1} in
        y|Y )
            echo "Starting deployment..."
            break
            ;;
        n|N )
            echo "Deployment cancelled."
            exit 0
            ;;
        * )
            echo "Please enter y or n."
            ;;
    esac
done

# Validate CloudFormation template
echo "Validating CloudFormation template..."
aws cloudformation validate-template --template-body file://deploy.yml > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
    echo "❌ Template validation failed. Please ensure deploy.yml exists and is valid."
    exit 1
fi

StackName="aws-idp-ai-codebuild-deploy-${STAGE}"

# Deploy CloudFormation stack
echo "Deploying CloudFormation stack for CodeBuild..."
aws cloudformation deploy \
  --stack-name $StackName \
  --template-file deploy.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    AdminUserEmail="$ADMIN_USER_EMAIL" \
    Stage="$STAGE" \
    EnableCognito="$ENABLE_COGNITO" \
    UseCustomDomain="$USE_CUSTOM_DOMAIN" \
    DomainName="$DOMAIN_NAME" \
    HostedZoneName="$HOSTED_ZONE_NAME" \
    RepoUrl="$REPO_URL" \
    Version="$VERSION"

if [[ $? -ne 0 ]]; then
    echo "❌ CloudFormation deployment failed"
    exit 1
fi

echo "Waiting for stack creation to complete..."
spin='-\|/'
i=0
while true; do
    status=$(aws cloudformation describe-stacks --stack-name $StackName --query 'Stacks[0].StackStatus' --output text 2>/dev/null)
    if [[ "$status" == "CREATE_COMPLETE" || "$status" == "UPDATE_COMPLETE" ]]; then
        break
    elif [[ "$status" == "ROLLBACK_COMPLETE" || "$status" == "DELETE_FAILED" || "$status" == "CREATE_FAILED" || "$status" == "UPDATE_ROLLBACK_COMPLETE" ]]; then
        echo ""
        echo "❌ Stack deployment failed with status: $status"
        exit 1
    fi
    printf "\r${spin:i++%${#spin}:1}"
    sleep 1
done
echo -e "\n✅ Stack deployed successfully\n"

# Get CodeBuild project name
outputs=$(aws cloudformation describe-stacks --stack-name $StackName --query 'Stacks[0].Outputs')
projectName=$(echo $outputs | jq -r '.[] | select(.OutputKey=="ProjectName").OutputValue')

if [[ -z "$projectName" ]]; then
    echo "❌ Failed to retrieve CodeBuild project name"
    exit 1
fi

# Start CodeBuild
echo "Starting CodeBuild project: $projectName..."
buildId=$(aws codebuild start-build --project-name $projectName --query 'build.id' --output text)

if [[ -z "$buildId" ]]; then
    echo "❌ Failed to start CodeBuild project"
    exit 1
fi

# Wait for build completion
echo "Build started. Waiting for completion..."
echo "You can monitor the build in the AWS Console: CodeBuild > Build projects > $projectName"
echo ""

while true; do
    buildStatus=$(aws codebuild batch-get-builds --ids $buildId --query 'builds[0].buildStatus' --output text)
    phases=$(aws codebuild batch-get-builds --ids $buildId --query 'builds[0].phases[?phaseStatus==`IN_PROGRESS`].phaseType' --output text)
    
    if [[ ! -z "$phases" ]]; then
        echo -ne "\rCurrent phase: $phases    "
    fi
    
    if [[ "$buildStatus" == "SUCCEEDED" || "$buildStatus" == "FAILED" || "$buildStatus" == "STOPPED" ]]; then
        echo ""
        break
    fi
    sleep 5
done

echo "Build completed with status: $buildStatus"

if [[ "$buildStatus" != "SUCCEEDED" ]]; then
    echo "❌ Build failed. Fetching logs..."
    
    buildDetail=$(aws codebuild batch-get-builds --ids $buildId --query 'builds[0].logs.{groupName: groupName, streamName: streamName}' --output json)
    logGroupName=$(echo $buildDetail | jq -r '.groupName')
    logStreamName=$(echo $buildDetail | jq -r '.streamName')
    
    if [[ ! -z "$logGroupName" ]] && [[ "$logGroupName" != "null" ]]; then
        echo "Fetching recent error logs..."
        aws logs tail $logGroupName --since 5m --filter-pattern "ERROR" 2>/dev/null || true
    fi
    
    echo ""
    echo "For full logs, run:"
    echo "aws logs tail $logGroupName --follow"
    exit 1
fi

# Get deployment results
echo ""
echo "==========================================================================="
echo "  ✅ Deployment Successful!                                               "
echo "---------------------------------------------------------------------------"

buildDetail=$(aws codebuild batch-get-builds --ids $buildId --query 'builds[0].logs.{groupName: groupName, streamName: streamName}' --output json)
logGroupName=$(echo $buildDetail | jq -r '.groupName')
logStreamName=$(echo $buildDetail | jq -r '.streamName')

# Extract URLs and credentials from logs
logs=$(aws logs get-log-events --log-group-name $logGroupName --log-stream-name $logStreamName --start-from-head --limit 1000)

frontendUrl=$(echo "$logs" | grep -o 'FrontendURL = [^ ]*' | cut -d' ' -f3 | tr -d '\n,' | head -1)
adminUsername=$(echo "$logs" | grep -o 'AdminUsername = [^ ]*' | cut -d' ' -f3 | tr -d '\n,' | head -1)
tempPassword=$(echo "$logs" | grep -o 'TemporaryPassword = [^ ]*' | cut -d' ' -f3 | tr -d '\n,' | head -1)

echo ""
echo "  🌐 Application URL: $frontendUrl"

if [[ "$ENABLE_COGNITO" == "true" ]]; then
    echo ""
    echo "  🔐 Cognito Authentication:"
    echo "     Username: $adminUsername"
    echo "     Password: $tempPassword"
    echo "     ⚠️  You must change the password on first login"
fi

echo ""
echo "  📋 Next Steps:"
echo "     1. Access the application using the URL above"
if [[ "$ENABLE_COGNITO" == "true" ]]; then
    echo "     2. Log in with the provided credentials"
    echo "     3. Change your password when prompted"
    echo "     4. Start uploading and analyzing documents"
else
    echo "     2. Start uploading and analyzing documents"
fi

echo ""
echo "  🗑️  To delete all resources:"
echo "     ./cleanup.sh --stage $STAGE"
echo ""
echo "==========================================================================="

# Save deployment info
echo "{
  \"stackName\": \"$StackName\",
  \"projectName\": \"$projectName\",
  \"frontendUrl\": \"$frontendUrl\",
  \"adminUsername\": \"$adminUsername\",
  \"stage\": \"$STAGE\",
  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
}" > deployment-info-${STAGE}.json

echo ""
echo "Deployment information saved to: deployment-info-${STAGE}.json"