#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# AWS IDP Pipeline ― Container Services Deployment Script
# -----------------------------------------------------------------------------
#  * Deploy Cognito authentication (required)
#  * Deploy ECR and ECS stacks with Cognito integration
#  * Build and push Docker images to ECR
#  * Update .env file with service information
# -----------------------------------------------------------------------------
# Usage:
#   ./deploy-services.sh <aws-profile> [options]
#
# Options:
#   --destroy                     Destroy existing services
#   --build-only                  Build and push images only (skip deployment)
#   --build-frontend              Build and push frontend image only
#   --build-backend               Build and push backend image only
# -----------------------------------------------------------------------------

set -euo pipefail

# Set umask only on Unix-like systems
case "$(uname -s)" in
  MINGW*|CYGWIN*|MSYS*) 
    # Windows Git Bash - umask may not work properly
    ;;
  *)
    # Unix-like systems
    umask 0002
    ;;
esac

# ────────────── cleanup and error handling ──────────────
cleanup_on_exit() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    print_error "Script failed with exit code $exit_code"
  fi
  
  exit $exit_code
}

trap cleanup_on_exit EXIT

# ────────────── Terminal output helpers ──────────────
print_error() {
  echo -e "\033[0;31m[ERROR]\033[0m $1" >&2
}

print_warning() {
  echo -e "\033[1;33m[WARNING]\033[0m $1"
}

print_info() {
  echo -e "\033[0;34m[INFO]\033[0m $1"
}

print_success() {
  echo -e "\033[0;32m[SUCCESS]\033[0m $1"
}

print_step() {
  local step_number="$1"
  local message="$2"
  echo ""
  echo -e "\033[1;36m┌─ Step $step_number: $message\033[0m"
  echo -e "\033[1;36m└──────────────────────────────────────\033[0m"
}

# ────────────── OS Detection ──────────────
get_os_type() {
  case "$(uname -s)" in
    Darwin*)
      echo "macOS"
      ;;
    Linux*)
      echo "Linux"
      ;;
    MINGW*|CYGWIN*|MSYS*)
      echo "Windows"
      ;;
    *)
      echo "Unknown"
      ;;
  esac
}

# ────────────── Self-signed certificate generation ──────────────
generate_self_signed_cert() {
  local domain="aws-idp-ai.internal"
  local cert_dir="certs"
  
  print_info "Generating self-signed certificate for $domain..."
  mkdir -p "$cert_dir"

  openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
    -keyout "$cert_dir/private.key" \
    -out "$cert_dir/certificate.pem" \
    -subj "/CN=$domain" \
    -addext "subjectAltName=DNS:$domain" >/dev/null 2>&1

  openssl x509 -in "$cert_dir/certificate.pem" -out "$cert_dir/certificate.pem" -outform PEM >/dev/null 2>&1
  
  print_success "Self-signed certificate generated in $cert_dir/"
}

import_certificate_to_acm() {
  local profile="$1"
  local cert_dir="certs"
  local cert_file="$cert_dir/certificate.pem"
  local key_file="$cert_dir/private.key"

  print_info "Importing certificate to AWS Certificate Manager..." >&2
  
  local certificate_arn
  certificate_arn=$(aws acm import-certificate \
    --certificate fileb://$cert_file \
    --private-key fileb://$key_file \
    --profile "$profile" \
    --output text \
    --query 'CertificateArn')

  if [[ $? -eq 0 && -n "$certificate_arn" ]]; then
    print_success "Certificate imported with ARN: $certificate_arn" >&2
    # Only output the ARN to stdout
    echo "$certificate_arn"
  else
    print_error "Failed to import certificate to ACM" >&2
    exit 1
  fi
}

# ────────────── Service Stack List ──────────────
get_service_stacks() {
  cat <<EOF
aws-idp-ai-cognito
aws-idp-ai-ecr
aws-idp-ai-ecs
aws-idp-ai-user-management
EOF
}

# ────────────── Prerequisite checks ──────────────
check_prerequisites() {
  print_step "1" "Checking prerequisites"
  
  # Check Docker
  if ! command -v docker >/dev/null 2>&1; then
    print_error "Docker is not installed or not in PATH"
    print_info "Please install Docker from: https://docs.docker.com/get-docker/"
    exit 1
  fi
  
  # Check if Docker daemon is running
  if ! docker info >/dev/null 2>&1; then
    print_error "Docker daemon is not running"
    print_info "Please start Docker and try again"
    exit 1
  fi
  
  print_info "Docker version: $(docker --version) ✓"
  
  # Check AWS CLI
  if ! command -v aws >/dev/null 2>&1; then
    print_error "AWS CLI is not installed"
    exit 1
  fi
  
  # Check pnpm
  if ! command -v pnpm >/dev/null 2>&1; then
    print_error "pnpm is not installed"
    exit 1
  fi
  
  # Check jq (needed for Cognito features)
  if ! command -v jq >/dev/null 2>&1; then
    print_error "jq is not installed (required for Cognito features)"
    exit 1
  fi
  
  # Check OpenSSL (needed for self-signed certificate generation)
  if ! command -v openssl >/dev/null 2>&1; then
    print_error "openssl is not installed (required for certificate generation)"
    exit 1
  fi
  
  # Check CDK
  if ! npx cdk --version >/dev/null 2>&1; then
    print_error "CDK not available via npx. Please ensure CDK is installed in project dependencies."
    exit 1
  else
    print_info "CDK available via npx ✓"
  fi
  
  print_success "All prerequisites satisfied"
}

# ────────────── AWS profile validation ──────────────
validate_aws_profile() {
  local profile="$1"
  
  print_step "2" "Validating AWS profile: $profile"
  
  # Check if profile exists
  if ! aws configure list-profiles 2>/dev/null | grep -q "^$profile$"; then
    print_error "AWS profile '$profile' does not exist"
    exit 1
  fi
  
  # Test AWS access
  local caller_identity
  if ! caller_identity=$(aws sts get-caller-identity --profile "$profile" 2>/dev/null); then
    print_error "Failed to authenticate with AWS profile '$profile'"
    exit 1
  fi
  
  local account_id
  account_id=$(echo "$caller_identity" | jq -r '.Account')
  
  print_info "AWS Account ID: $account_id"
  print_success "AWS profile validation successful"
}

# ────────────── Check base infrastructure ──────────────
check_base_infrastructure() {
  local profile="$1"
  local region
  region=$(aws configure get region --profile "$profile" 2>/dev/null || echo "us-west-2")

  print_step "3" "Checking base infrastructure"

  # Check if VPC stack exists
  if ! aws cloudformation describe-stacks --stack-name "aws-idp-ai-vpc" --profile "$profile" --region "$region" >/dev/null 2>&1; then
    print_error "Base infrastructure not found. Please run './deploy-infra.sh $profile' first."
    print_info ""
    print_info "The base infrastructure deployment creates:"
    print_info "  • VPC and networking components"
    print_info "  • API Gateway and Lambda functions"
    print_info "  • DynamoDB tables and S3 buckets"
    print_info "  • .env file for local development"
    exit 1
  fi

  print_success "Base infrastructure found"
}

# ────────────── Download Lambda Layers from GitHub ──────────────
download_lambda_layers() {
  print_step "3.5" "Checking Lambda Layer zip files"

  local LAYER_DIR="./src/lambda_layer"
  local GITHUB_REPO="https://raw.githubusercontent.com/yunwoong7/lambda-layers-assets/main/aws-idp-assets"

  local layers=(
    "custom_layer_common.zip"
    "custom_layer_opensearch.zip"
    "custom_layer_image_processing.zip"
    "custom_layer_analysis_package.zip"
  )

  local missing_layers=()

  # Check which layers are missing
  for layer in "${layers[@]}"; do
    if [[ ! -f "$LAYER_DIR/$layer" ]]; then
      missing_layers+=("$layer")
    fi
  done

  # Download missing layers
  if [[ ${#missing_layers[@]} -gt 0 ]]; then
    print_info "Missing ${#missing_layers[@]} Lambda layer(s), downloading from GitHub..."

    for layer in "${missing_layers[@]}"; do
      print_info "Downloading $layer..."
      if curl -L -f -o "$LAYER_DIR/$layer" "$GITHUB_REPO/$layer" 2>/dev/null; then
        print_success "Downloaded: $layer"
      else
        print_error "Failed to download $layer from $GITHUB_REPO/$layer"
        print_info "Please check if the file exists in the GitHub repository"
        exit 1
      fi
    done

    print_success "All Lambda layers downloaded successfully"
  else
    print_info "All Lambda layer zip files already exist ✓"
  fi
}

# ────────────── Build and push individual Docker image ──────────────
build_and_push_single_image() {
  local profile="$1"
  local service="$2"  # "frontend" or "backend"
  local region
  local account_id
  local api_gw_url
  
  region=$(aws configure get region --profile "$profile" 2>/dev/null || echo "us-west-2")
  account_id=$(aws sts get-caller-identity --profile "$profile" --query 'Account' --output text)

  # Resolve API Gateway endpoint from CloudFormation outputs
  api_gw_url=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-api-gateway" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayEndpoint'].OutputValue" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true)
  if [[ -z "$api_gw_url" || "$api_gw_url" == "None" ]]; then
    print_warning "API Gateway URL not found; falling back to empty value"
    api_gw_url=""
  fi
  
  print_step "4" "Building and pushing $service Docker image"
  
  # ECR login
  print_info "Logging in to ECR..."
  aws ecr get-login-password --region "$region" --profile "$profile" | \
    docker login --username AWS --password-stdin "$account_id.dkr.ecr.$region.amazonaws.com"
  
  # Get ECR repository URI from CloudFormation
  local repo_uri
  local output_key
  if [[ "$service" == "backend" ]]; then
    output_key="BackendRepositoryUri"
  else
    output_key="FrontendRepositoryUri"
  fi
  
  repo_uri=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-ecr" \
    --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true)
  
  if [[ -z "$repo_uri" || "$repo_uri" == "None" ]]; then
    print_error "$service ECR repository URI not found in CloudFormation outputs"
    print_info "Please ensure ECR stack is deployed first"
    exit 1
  fi
  
  print_info "$service ECR URI: $repo_uri"
  
  # Navigate to project root
  cd ../../
  
  # Build and push image
  print_info "Building $service Docker image..."
  if [[ "$service" == "frontend" ]]; then
    # Pass build args for Next.js public envs
    docker build --platform linux/amd64 \
      -f "packages/$service/Dockerfile" \
      --build-arg NEXT_PUBLIC_API_BASE_URL="$api_gw_url" \
      -t "aws-idp-$service:latest" .
  else
    docker build --platform linux/amd64 -f "packages/$service/Dockerfile" -t "aws-idp-$service:latest" .
  fi
  docker tag "aws-idp-$service:latest" "$repo_uri:latest"
  docker push "$repo_uri:latest"
  print_success "$service image pushed: $repo_uri:latest"
  
  # Clean up local images
  print_info "Cleaning up local Docker images..."
  docker rmi "aws-idp-$service:latest" "$repo_uri:latest" 2>/dev/null || true
  
  # Return to infra directory
  cd packages/infra/
  
  # Force ECS service update
  print_info "Forcing ECS service update for $service..."
  aws ecs update-service --cluster aws-idp-cluster-dev --service "aws-idp-$service-dev" --force-new-deployment --profile "$profile" >/dev/null
  print_success "ECS service update initiated for $service"
}

# ────────────── Build and push Docker images ──────────────
build_and_push_images() {
  local profile="$1"
  local region
  local account_id
  local api_gw_url
  
  region=$(aws configure get region --profile "$profile" 2>/dev/null || echo "us-west-2")
  account_id=$(aws sts get-caller-identity --profile "$profile" --query 'Account' --output text)

  # Resolve API Gateway endpoint from CloudFormation outputs
  api_gw_url=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-api-gateway" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayEndpoint'].OutputValue" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true)
  if [[ -z "$api_gw_url" || "$api_gw_url" == "None" ]]; then
    print_warning "API Gateway URL not found; falling back to empty value"
    api_gw_url=""
  fi
  
  print_step "5" "Building and pushing Docker images"
  
  # ECR login
  print_info "Logging in to ECR..."
  aws ecr get-login-password --region "$region" --profile "$profile" | \
    docker login --username AWS --password-stdin "$account_id.dkr.ecr.$region.amazonaws.com"
  
  # Get ECR repository URIs from CloudFormation
  local backend_repo_uri
  local frontend_repo_uri
  
  backend_repo_uri=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-ecr" \
    --query "Stacks[0].Outputs[?OutputKey=='BackendRepositoryUri'].OutputValue" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true)
  
  frontend_repo_uri=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-ecr" \
    --query "Stacks[0].Outputs[?OutputKey=='FrontendRepositoryUri'].OutputValue" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true)
  
  if [[ -z "$backend_repo_uri" || -z "$frontend_repo_uri" || "$backend_repo_uri" == "None" || "$frontend_repo_uri" == "None" ]]; then
    print_error "ECR repository URIs not found in CloudFormation outputs"
    print_info "Please ensure ECR stack is deployed first"
    exit 1
  fi
  
  print_info "Backend ECR URI: $backend_repo_uri"
  print_info "Frontend ECR URI: $frontend_repo_uri"
  
  # Navigate to project root
  cd ../../
  
  # Build Backend Docker Image
  print_info "Building backend Docker image..."
  docker build --platform linux/amd64 -f packages/backend/Dockerfile -t aws-idp-backend:latest .
  docker tag aws-idp-backend:latest "$backend_repo_uri:latest"
  docker push "$backend_repo_uri:latest"
  print_success "Backend image pushed: $backend_repo_uri:latest"
  
  # Build Frontend Docker Image
  print_info "Building frontend Docker image..."
  docker build --platform linux/amd64 \
    -f packages/frontend/Dockerfile \
    --build-arg NEXT_PUBLIC_API_BASE_URL="$api_gw_url" \
    -t aws-idp-frontend:latest .
  docker tag aws-idp-frontend:latest "$frontend_repo_uri:latest"
  docker push "$frontend_repo_uri:latest"
  print_success "Frontend image pushed: $frontend_repo_uri:latest"
  
  # Clean up local images
  print_info "Cleaning up local Docker images..."
  docker rmi aws-idp-backend:latest aws-idp-frontend:latest \
             "$backend_repo_uri:latest" "$frontend_repo_uri:latest" 2>/dev/null || true
  
  # Return to infra directory
  cd packages/infra/
}

# ────────────── Deploy Cognito stacks ──────────────
deploy_cognito_stacks() {
  local profile="$1"
  local admin_email="$2"
  local domain_name="${3:-}"
  local hosted_zone_id="${4:-}"
  local hosted_zone_name="${5:-}"
  local existing_user_pool="${6:-}"
  local existing_domain="${7:-}"
  local cert_arn="${8:-}"
  
  print_step "3.5" "Deploying Cognito authentication"
  
  # Prepare CDK context for Cognito
  local cdk_context="-c adminUserEmail=$admin_email"
  
  if [[ -n "$domain_name" && -n "$hosted_zone_id" && -n "$hosted_zone_name" ]]; then
    cdk_context="$cdk_context -c useCustomDomain=true"
    cdk_context="$cdk_context -c domainName=$domain_name"
    cdk_context="$cdk_context -c hostedZoneId=$hosted_zone_id"
    cdk_context="$cdk_context -c hostedZoneName=$hosted_zone_name"
  fi
  
  if [[ -n "$cert_arn" ]]; then
    cdk_context="$cdk_context -c existingCertificateArn=$cert_arn"
  fi
  
  if [[ -n "$existing_user_pool" ]]; then
    cdk_context="$cdk_context -c existingUserPoolId=$existing_user_pool"
  fi
  
  if [[ -n "$existing_domain" ]]; then
    cdk_context="$cdk_context -c existingUserPoolDomain=$existing_domain"
  fi
  
  # Deploy Cognito stack
  print_info "Deploying Cognito User Pool..."
  npx cdk deploy aws-idp-ai-cognito $cdk_context --require-approval=never --profile "$profile"
  
  # Deploy Certificate stack only if custom domain is configured
  if [[ -n "$domain_name" && -n "$hosted_zone_id" && -n "$hosted_zone_name" ]]; then
    print_info "Deploying SSL Certificate..."
    npx cdk deploy aws-idp-ai-certificate $cdk_context --require-approval=never --profile "$profile"
  else
    print_info "Using existing SSL Certificate (ARN: ${cert_arn})"
  fi
  
  print_success "Cognito authentication stacks deployed"
}

# ────────────── Deploy ECR stack first ──────────────
deploy_ecr_stack() {
  local profile="$1"
  
  print_step "4" "Deploying ECR repositories"
  
  # Install dependencies
  print_info "Installing dependencies..."
  pnpm install
  
  # Build CDK TypeScript files only
  if [[ -f tsconfig.json ]]; then
    print_info "Building CDK TypeScript..."
    npx tsc --build
  fi
  
  # Deploy ECR stack first
  print_info "Deploying ECR stack..."
  npx cdk deploy aws-idp-ai-ecr \
    --require-approval=never \
    --profile "$profile" \
    --progress=events
  
  print_success "ECR stack deployment completed"
}

# ────────────── Deploy User Management stack ──────────────
deploy_user_management_stack() {
  local profile="$1"
  local admin_email="$2"
  local domain_name="${3:-}"
  local hosted_zone_id="${4:-}"
  local hosted_zone_name="${5:-}"
  local existing_user_pool="${6:-}"
  local existing_domain="${7:-}"

  print_step "6.5" "Deploying User Management stack with Cognito integration"

  # Prepare CDK context for User Management
  local cdk_context="-c adminUserEmail=$admin_email"

  if [[ -n "$domain_name" && -n "$hosted_zone_id" && -n "$hosted_zone_name" ]]; then
    cdk_context="$cdk_context -c useCustomDomain=true"
    cdk_context="$cdk_context -c domainName=$domain_name"
    cdk_context="$cdk_context -c hostedZoneId=$hosted_zone_id"
    cdk_context="$cdk_context -c hostedZoneName=$hosted_zone_name"
  fi

  if [[ -n "$existing_user_pool" ]]; then
    cdk_context="$cdk_context -c existingUserPoolId=$existing_user_pool"
  fi

  if [[ -n "$existing_domain" ]]; then
    cdk_context="$cdk_context -c existingUserPoolDomain=$existing_domain"
  fi

  # Deploy User Management stack
  print_info "Deploying User Management stack..."
  print_info "CDK Context: $cdk_context"
  npx cdk deploy aws-idp-ai-user-management $cdk_context --require-approval=never --profile "$profile" --progress=events --rollback=false

  print_success "User Management stack deployment completed"
}

# ────────────── Deploy ECS stack ──────────────
deploy_ecs_stack() {
  local profile="$1"
  local admin_email="$2"
  local domain_name="${3:-}"
  local hosted_zone_id="${4:-}"
  local hosted_zone_name="${5:-}"
  local existing_user_pool="${6:-}"
  local existing_domain="${7:-}"
  local cert_arn="${8:-}"

  print_step "6" "Deploying ECS services with Cognito integration"
  
  # Check and clean up existing ALB logs S3 bucket
  local region
  local account_id
  region=$(aws configure get region --profile "$profile" 2>/dev/null || echo "us-west-2")
  account_id=$(aws sts get-caller-identity --profile "$profile" --query 'Account' --output text)
  
  local alb_logs_bucket="aws-idp-alb-logs-dev-$account_id"
  
  if aws s3api head-bucket --bucket "$alb_logs_bucket" --profile "$profile" >/dev/null 2>&1; then
    print_info "Existing ALB logs S3 bucket detected: $alb_logs_bucket"
    print_info "Automatically deleting existing ALB logs bucket..."
    # Empty bucket first
    aws s3 rm "s3://$alb_logs_bucket" --recursive --profile "$profile" 2>/dev/null || true
    # Delete bucket
    aws s3api delete-bucket --bucket "$alb_logs_bucket" --profile "$profile" 2>/dev/null || true
    print_success "ALB logs bucket deleted"
  fi
  
  # Prepare CDK context for ECS deployment with Cognito
  local cdk_context="-c adminUserEmail=$admin_email"
  
  if [[ -n "$domain_name" && -n "$hosted_zone_id" && -n "$hosted_zone_name" ]]; then
    cdk_context="$cdk_context -c useCustomDomain=true"
    cdk_context="$cdk_context -c domainName=$domain_name"
    cdk_context="$cdk_context -c hostedZoneId=$hosted_zone_id"
    cdk_context="$cdk_context -c hostedZoneName=$hosted_zone_name"
  fi
  
  if [[ -n "$cert_arn" ]]; then
    cdk_context="$cdk_context -c existingCertificateArn=$cert_arn"
  fi
  
  if [[ -n "$existing_user_pool" ]]; then
    cdk_context="$cdk_context -c existingUserPoolId=$existing_user_pool"
  fi
  
  if [[ -n "$existing_domain" ]]; then
    cdk_context="$cdk_context -c existingUserPoolDomain=$existing_domain"
  fi
  
  # Deploy ECS stack with Cognito integration
  print_info "Deploying ECS stack with Cognito authentication..."
  print_info "CDK Context: $cdk_context"
  npx cdk deploy aws-idp-ai-ecs $cdk_context --require-approval=never --profile "$profile" --progress=events --rollback=false
  
  print_success "ECS stack deployment completed"
}

# ────────────── Destroy service stacks ──────────────
destroy_service_stacks() {
  local profile="$1"
  
  print_step "4" "Destroying service stacks"
  
  # Get service stacks in reverse order for safe deletion
  local stacks_to_destroy
  stacks_to_destroy=$(get_service_stacks | tac | tr '\n' ' ')
  
  print_warning "Destroying Service Stacks:"
  echo "$stacks_to_destroy" | tr ' ' '\n' | sed 's/^/  • /'
  
  # Confirm destruction
  read -p "Are you sure you want to destroy containerized services? (yes/no): " confirm
  if [[ $confirm != "yes" ]]; then
    print_info "Destruction cancelled"
    exit 0
  fi
  
  # Destroy stacks
  print_warning "Starting CDK destruction..."
  # shellcheck disable=SC2086
  npx cdk destroy $stacks_to_destroy \
    --force \
    --profile "$profile"
  
  print_success "Service stacks destruction completed"
}

# ────────────── Update .env file and create Cognito info ──────────────
update_env_file() {
  local profile="$1"
  local admin_email="$2"
  local domain_name="${3:-}"
  local hosted_zone_name="${4:-}"
  local region
  
  region=$(aws configure get region --profile "$profile" 2>/dev/null || echo "us-west-2")
  
  print_step "7" "Updating .env file with service information"
  
  local env_file="../../.env"
  
  if [[ ! -f "$env_file" ]]; then
    print_warning ".env file not found. Run './deploy-infra.sh $profile' first to create it."
    return
  fi
  
  # Get stack outputs
  local account_id
  account_id=$(aws sts get-caller-identity --profile "$profile" --query 'Account' --output text)
  
  local alb_dns_name user_pool_id user_pool_client_id user_pool_domain
  
  alb_dns_name=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-ecs" \
    --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerDnsName'].OutputValue" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true)
    
  user_pool_id=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-cognito" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
    --output text --profile "$profile" 2>/dev/null || true)
    
  user_pool_client_id=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-cognito" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
    --output text --profile "$profile" 2>/dev/null || true)
    
  user_pool_domain=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-cognito" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolDomain'].OutputValue" \
    --output text --profile "$profile" 2>/dev/null || true)
  
  # Determine application URL
  local app_url protocol
  if [[ -n "$domain_name" && -n "$hosted_zone_name" ]]; then
    app_url="https://$domain_name.$hosted_zone_name"
    protocol="https"
  elif [[ -n "$alb_dns_name" ]]; then
    app_url="https://$alb_dns_name"
    protocol="https"
  else
    app_url="https://placeholder.domain"
    protocol="https"
  fi
  
  if [[ -n "$alb_dns_name" && "$alb_dns_name" != "None" ]]; then
    print_info "ALB DNS Name: $alb_dns_name"
    
    # Remove existing ECS and Cognito sections
    if grep -q "# ECS Service Endpoints" "$env_file"; then
      sed -i.bak "/# ECS Service Endpoints/,/^$/d" "$env_file"
    fi
    if grep -q "# Cognito Authentication Configuration" "$env_file"; then
      sed -i.bak "/# Cognito Authentication Configuration/,/^$/d" "$env_file"
    fi
    
    # Add new sections
    cat >> "$env_file" <<EOF

# ECS Service Endpoints
ALB_DNS_NAME=$alb_dns_name
FRONTEND_URL=$app_url
BACKEND_API_URL=$app_url/api
ENVIRONMENT=production

# Cognito Authentication Configuration
COGNITO_USER_POOL_ID=$user_pool_id
COGNITO_USER_POOL_CLIENT_ID=$user_pool_client_id
COGNITO_USER_POOL_DOMAIN=$user_pool_domain
COGNITO_REGION=$region
APPLICATION_URL=$app_url
COGNITO_CALLBACK_URL=$app_url/oauth2/idpresponse
COGNITO_LOGOUT_URL=$app_url
ADMIN_USER_EMAIL=$admin_email
EOF
    
    print_success "Updated $env_file with service and authentication information"
    
    # Show deployment summary
    show_deployment_summary "$app_url" "$admin_email" "$user_pool_id"
  else
    print_warning "Could not retrieve ALB DNS name. .env file not updated."
  fi
}


# ────────────── Show deployment summary ──────────────
show_deployment_summary() {
  local app_url="$1"
  local admin_email="$2"
  local user_pool_id="$3"
  
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  print_success "AWS IDP Pipeline deployment completed successfully"
  echo ""
  print_info "Authentication: Cognito User Pool"
  print_info "Application URL: $app_url"
  print_info "Admin Email: $admin_email"
  echo ""
  print_warning "Next Steps:"
  print_info "1. Access your application at $app_url"
  print_info "2. Sign in with:"
  echo "   Username: ${admin_email%%@*}"
  echo "   Temporary Password: TempPass123! (must be changed on first login)"
  print_info "3. You will be prompted to set a new password on first login"
  print_info "4. Services may take a few minutes to be fully ready"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ────────────── Main execution logic ──────────────
main() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "   AWS IDP Pipeline - Container Services with Cognito"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  
  # Parse arguments
  local aws_profile=""
  local destroy_services=false
  local build_only=false
  local build_frontend=false
  local build_backend=false
  
  while [[ $# -gt 0 ]]; do
    case $1 in
      --destroy)
        destroy_services=true
        shift
        ;;
      --build-only)
        build_only=true
        shift
        ;;
      --build-frontend)
        build_frontend=true
        shift
        ;;
      --build-backend)
        build_backend=true
        shift
        ;;
      -*)
        print_error "Unknown option: $1"
        echo ""
        echo "Usage: $0 <aws-profile> [options]"
        echo ""
        echo "Options:"
        echo "  --destroy         Destroy existing services"
        echo "  --build-only      Build and push images only (skip deployment)"
        echo "  --build-frontend  Build and push frontend image only"
        echo "  --build-backend   Build and push backend image only"
        echo ""
        exit 1
        ;;
      *)
        if [[ -z "$aws_profile" ]]; then
          aws_profile="$1"
        else
          print_error "Multiple AWS profiles specified: '$aws_profile' and '$1'"
          exit 1
        fi
        shift
        ;;
    esac
  done
  
  # Validate required arguments
  if [[ -z "$aws_profile" ]]; then
    print_error "AWS profile is required"
    echo ""
    echo "Usage: $0 <aws-profile> [options]"
    exit 1
  fi
  
  # Set environment variables
  export AWS_PROFILE="$aws_profile"
  
  # Interactive configuration for full deployment
  local admin_email=""
  local domain_name=""
  local hosted_zone_id=""
  local hosted_zone_name=""
  local existing_user_pool=""
  local existing_domain=""
  local cert_arn=""
  
  if [[ "$destroy_services" != "true" && "$build_frontend" != "true" && "$build_backend" != "true" && "$build_only" != "true" ]]; then
    echo "AWS IDP Pipeline - Container Services with Cognito"
    echo "This tool will deploy containerized services with Cognito authentication."
    echo ""
    
    # Admin email (required)
    while [[ -z "$admin_email" ]]; do
      read -p "Admin User Email (required): " admin_email
      if [[ ! "$admin_email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        print_error "Invalid email format. Please try again."
        admin_email=""
      fi
    done
    
    # Existing Cognito User Pool (optional)
    read -p "Existing Cognito User Pool ID (enter to create new): " existing_user_pool
    if [[ -n "$existing_user_pool" ]]; then
      read -p "Existing Cognito User Pool Domain (enter to skip): " existing_domain
    fi
    
    # Certificate Configuration
    echo ""
    echo "Certificate Configuration:"
    echo "For ALB to work with Cognito authentication, you need an SSL certificate."
    echo ""
    read -p "Existing SSL Certificate ARN (enter to generate self-signed): " cert_arn
    
    # Generate self-signed certificate if none provided
    if [[ -z "$cert_arn" ]]; then
      print_info "No certificate ARN provided. Generating self-signed certificate..."
      
      # Clean up existing aws-idp-ai.internal certificates
      print_info "Cleaning up existing certificates..."
      local existing_certs
      existing_certs=$(aws acm list-certificates --query 'CertificateSummaryList[?DomainName==`aws-idp-ai.internal`].CertificateArn' --output text --profile "$aws_profile" 2>/dev/null || true)
      
      if [[ -n "$existing_certs" ]]; then
        for cert_arn_to_delete in $existing_certs; do
          print_info "Deleting certificate: $cert_arn_to_delete"
          aws acm delete-certificate --certificate-arn "$cert_arn_to_delete" --profile "$aws_profile" 2>/dev/null || true
        done
      fi
      
      # Clean up existing certificate files
      rm -rf certs/ 2>/dev/null || true
      
      generate_self_signed_cert
      cert_arn=$(import_certificate_to_acm "$aws_profile")
      print_success "Using generated certificate ARN: $cert_arn"
    fi
    
    # Show configuration summary
    echo ""
    echo "Deploying AWS IDP Pipeline with the following configuration:"
    echo "AWS Profile: $aws_profile"
    echo "Admin User Email: $admin_email"
    if [[ -n "$existing_user_pool" ]]; then
      echo "Cognito: Using existing User Pool $existing_user_pool"
    else
      echo "Cognito: Creating new User Pool"
    fi
    echo "SSL Certificate: $cert_arn"
    echo "Domain: ALB DNS with HTTPS"
    echo ""
    read -p "Please confirm (y/n): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
      print_info "Deployment cancelled"
      exit 0
    fi
  fi
  
  # Execute main workflow
  check_prerequisites
  validate_aws_profile "$aws_profile"
  
  if [[ "$destroy_services" == "true" ]]; then
    destroy_service_stacks "$aws_profile"
  elif [[ "$build_frontend" == "true" ]]; then
    check_base_infrastructure "$aws_profile"
    download_lambda_layers
    build_and_push_single_image "$aws_profile" "frontend"
  elif [[ "$build_backend" == "true" ]]; then
    check_base_infrastructure "$aws_profile"
    download_lambda_layers
    build_and_push_single_image "$aws_profile" "backend"
  elif [[ "$build_only" == "true" ]]; then
    check_base_infrastructure "$aws_profile"
    download_lambda_layers
    deploy_ecr_stack "$aws_profile"
    build_and_push_images "$aws_profile"
  else
    check_base_infrastructure "$aws_profile"
    download_lambda_layers
    # Deploy in sequence: Cognito -> Certificate -> ECR -> ECS -> User Management
    deploy_cognito_stacks "$aws_profile" "$admin_email" "$domain_name" "$hosted_zone_id" "$hosted_zone_name" "$existing_user_pool" "$existing_domain" "$cert_arn"
    deploy_ecr_stack "$aws_profile"
    build_and_push_images "$aws_profile"
    deploy_ecs_stack "$aws_profile" "$admin_email" "$domain_name" "$hosted_zone_id" "$hosted_zone_name" "$existing_user_pool" "$existing_domain" "$cert_arn"
    deploy_user_management_stack "$aws_profile" "$admin_email" "$domain_name" "$hosted_zone_id" "$hosted_zone_name" "$existing_user_pool" "$existing_domain"
    update_env_file "$aws_profile" "$admin_email" "$domain_name" "$hosted_zone_name"
  fi
  
  echo ""
}

# Run main function
main "$@"