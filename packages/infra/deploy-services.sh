#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# AWS IDP Pipeline ― Container Services Deployment Script
# -----------------------------------------------------------------------------
#  * Deploy ECR and ECS stacks only
#  * Build and push Docker images to ECR
#  * Update .env file with ALB DNS information
# -----------------------------------------------------------------------------
# Examples:
#   ./deploy-services.sh <aws-profile>                # deploy services
#   ./deploy-services.sh <aws-profile> --destroy      # destroy services
#   ./deploy-services.sh <aws-profile> --build-only   # build images only
#   ./deploy-services.sh <aws-profile> --build-frontend  # build frontend image only
#   ./deploy-services.sh <aws-profile> --build-backend   # build backend image only
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

# ────────────── Service Stack List ──────────────
get_service_stacks() {
  cat <<EOF
aws-idp-ecr
aws-idp-ecs
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

# ────────────── Deploy ECS stack ──────────────
deploy_ecs_stack() {
  local profile="$1"
  
  print_step "6" "Deploying ECS services"
  
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
  
  # Deploy ECS stack
  print_info "Deploying ECS stack..."
  npx cdk deploy aws-idp-ai-ecs \
    --require-approval=never \
    --profile "$profile" \
    --progress=events \
    --rollback=false
  
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

# ────────────── Update .env file ──────────────
update_env_file() {
  local profile="$1"
  local region
  
  region=$(aws configure get region --profile "$profile" 2>/dev/null || echo "us-west-2")
  
  print_step "7" "Updating .env file with service endpoints"
  
  local env_file="../../.env"
  
  if [[ ! -f "$env_file" ]]; then
    print_warning ".env file not found. Run './deploy-infra.sh $profile' first to create it."
    return
  fi
  
  # Get ALB DNS name from CloudFormation
  local alb_dns_name
  alb_dns_name=$(aws cloudformation describe-stacks --stack-name "aws-idp-ai-ecs" \
    --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerDnsName'].OutputValue" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true)
  
  if [[ -n "$alb_dns_name" && "$alb_dns_name" != "None" ]]; then
    print_info "ALB DNS Name: $alb_dns_name"
    
    # Add or update ECS service endpoints in .env file
    if grep -q "# ECS Service Endpoints" "$env_file"; then
      # Update existing section
      sed -i.bak "/# ECS Service Endpoints/,/^$/d" "$env_file"
    fi
    
    # Add new section
    cat >> "$env_file" <<EOF

# ECS Service Endpoints
# NEXT_PUBLIC_ECS_BACKEND_URL=http://$alb_dns_name
ALB_DNS_NAME=$alb_dns_name
FRONTEND_URL=http://$alb_dns_name
BACKEND_API_URL=http://$alb_dns_name/api
ENVIRONMENT=local
EOF
    
    print_success "Updated $env_file with service endpoints"
    
    # Show service URLs
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    print_success "🎉 Service deployment completed successfully!"
    echo ""
    print_info "Service URLs:"
    print_info "  Frontend:    http://$alb_dns_name"
    print_info "  Backend API: http://$alb_dns_name/api"
    echo ""
    print_warning "Note: Services may take a few minutes to be ready"
    print_info "💡 Chat and reinit functions will now use the ECS backend"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  else
    print_warning "Could not retrieve ALB DNS name. .env file not updated."
  fi
}

# ────────────── Main execution logic ──────────────
main() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "   AWS IDP Pipeline - Container Services"
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
        echo "Usage: $0 <aws-profile> [--destroy] [--build-only] [--build-frontend] [--build-backend]"
        echo ""
        echo "Options:"
        echo "  <aws-profile>     AWS profile to use for deployment"
        echo "  --destroy         Destroy existing services"
        echo "  --build-only      Build and push both images only (skip deployment)"
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
  
  # Validate AWS profile argument
  if [[ -z "$aws_profile" ]]; then
    print_error "AWS profile is required"
    echo ""
    echo "Usage: $0 <aws-profile> [--destroy] [--build-only]"
    exit 1
  fi
  
  # Set environment variables
  export AWS_PROFILE="$aws_profile"
  
  # Execute main workflow
  check_prerequisites
  validate_aws_profile "$aws_profile"
  
  if [[ "$destroy_services" == "true" ]]; then
    destroy_service_stacks "$aws_profile"
  elif [[ "$build_frontend" == "true" ]]; then
    check_base_infrastructure "$aws_profile"
    build_and_push_single_image "$aws_profile" "frontend"
  elif [[ "$build_backend" == "true" ]]; then
    check_base_infrastructure "$aws_profile"
    build_and_push_single_image "$aws_profile" "backend"
  elif [[ "$build_only" == "true" ]]; then
    check_base_infrastructure "$aws_profile"
    deploy_ecr_stack "$aws_profile"
    build_and_push_images "$aws_profile"
  else
    check_base_infrastructure "$aws_profile"
    deploy_ecr_stack "$aws_profile"
    build_and_push_images "$aws_profile"
    deploy_ecs_stack "$aws_profile"
    update_env_file "$aws_profile"
  fi
  
  echo ""
}

# Run main function
main "$@"