#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# AWS IDP AI Analysis ― Comprehensive Infrastructure Deploy Script
# -----------------------------------------------------------------------------
#  - Pre-flight checks (aws, npx, pnpm, jq, CDK)
#  - Optional destroy & preserve VPC
#  - Prepare .toml
#  - CDK bootstrap + build (Nx)
#  - Deploy (all or selected stacks)
#  - Optional OpenSearch Nori package install (Managed OpenSearch)
#  - Generate backend .env and MCP config
# -----------------------------------------------------------------------------
# Usage:
#   ./deploy-infra.sh <aws-profile> [options]
# Options:
#   --destroy             Destroy existing infra before deploy
#   --preserve-vpc        Preserve VPC stack when destroying/deploying
#   --stacks "A B C"     Deploy only specified stacks (space-separated)
#   --skip-nori           Skip Nori plugin installation
#   --env-only            Only create .env and MCP config (no deploy)
#   --env-perm <mode>     .env file permission (default: 664)
#   --help                Show help
# -----------------------------------------------------------------------------

set -euo pipefail
set -o errtrace

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Log helpers (unified style)
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

# Extra helper for VPC tagged logs (consistent style)
print_vpc() {
  echo -e "\033[0;36m[VPC]\033[0m $1"
}

usage() {
  cat <<EOF
Usage: $0 <aws-profile> [options]

Options:
  --destroy             Destroy existing infra before deploy
  --preserve-vpc        Preserve VPC stack when destroying/deploying
  --stacks "A B C"     Deploy only specified stacks (space-separated)
  --skip-nori           Skip Nori plugin installation
  --env-only            Only create .env and MCP config (no deploy)
  --env-perm <mode>     .env file permission (default: 664)
  --help                Show help
EOF
  exit 1
}

# Cleanup on exit
cleanup_on_exit() {
  local exit_code=$?
  [[ $exit_code -ne 0 ]] && print_error "Script failed with exit code $exit_code"
  [[ -f tmp.json ]] && rm -f tmp.json
  exit $exit_code
}
trap cleanup_on_exit EXIT
trap 'print_error "Error on line $LINENO: $BASH_COMMAND"; exit 1' ERR

# OS detection
detect_os() {
  case "$(uname -s)" in
    MINGW*|CYGWIN*|MSYS*) echo "windows" ;;
    Darwin*) echo "macos" ;;
    Linux*) echo "linux" ;;
    *) echo "unknown" ;;
  esac
}

# Pre-flight checks
check_prerequisites() {
  print_info "Checking prerequisites..."
  local missing_tools=()
  command -v aws >/dev/null 2>&1 || missing_tools+=("aws-cli")
  command -v npx >/dev/null 2>&1 || missing_tools+=("node/npm (npx)")
  command -v pnpm >/dev/null 2>&1 || missing_tools+=("pnpm")
  command -v jq >/dev/null 2>&1 || missing_tools+=("jq")
  if [[ ${#missing_tools[@]} -gt 0 ]]; then
    print_error "Missing required tools: ${missing_tools[*]}"
    exit 1
  fi
  if ! npx cdk --version >/dev/null 2>&1; then
    print_error "CDK not available. Install via 'npm install -g aws-cdk' or add to dev deps."
    exit 1
  fi
  print_info "Prerequisites OK"
}

# Params
(( $# < 1 )) && { print_error "Missing AWS profile"; usage; }
export AWS_PROFILE=$1; shift || true
PRESERVE_VPC=false
DESTROY_INFRASTRUCTURE=false
SKIP_NORI=false
ENV_ONLY=false
ENV_PERM="664"
CUSTOM_STACKS=""

while (( $# )); do
  case "$1" in
    --destroy)        DESTROY_INFRASTRUCTURE=true ;;
    --preserve-vpc)   PRESERVE_VPC=true ;;
    --skip-nori)      SKIP_NORI=true ;;
    --env-only)       ENV_ONLY=true ;;
    --env-perm)       shift; ENV_PERM="${1:-664}" ;;
    --stacks)         shift; CUSTOM_STACKS="${1:-}" ;;
    --help|-h)        usage ;;
    *)                print_error "Unknown option: $1"; usage ;;
  esac
  shift || true
done

# Validate credentials
aws sts get-caller-identity --profile "$AWS_PROFILE" >/dev/null 2>&1 || {
  print_error "Invalid or missing credentials for profile: $AWS_PROFILE"; exit 1;
}

# .env permissions (cross-platform best-effort)
set_file_permissions() { local f="$1" p="${2:-644}"; chmod "$p" "$f" 2>/dev/null || true; }

# Stack helpers
stack_exists() { aws cloudformation describe-stacks --stack-name "$1" --profile "$AWS_PROFILE" >/dev/null 2>&1; }
get_stack_status() {
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].StackStatus" --output text --profile "$AWS_PROFILE" 2>/dev/null || echo "NOT_EXISTS"
}
wait_for_stack_deletion() {
  local stack_name="$1" max_wait=600 elapsed=0
  print_info "Waiting for deletion of stack: $stack_name"
  while stack_exists "$stack_name" && (( elapsed < max_wait )); do
    local status=$(get_stack_status "$stack_name")
    print_info "Status: $status (waited ${elapsed}s)"
    [[ "$status" == "DELETE_FAILED" ]] && { print_error "Deletion failed for $stack_name"; return 1; }
    sleep 30; elapsed=$((elapsed + 30))
  done
  stack_exists "$stack_name" && { print_error "Timeout waiting for $stack_name deletion"; return 1; }
  print_info "Deletion complete: $stack_name"
}

# Prepare .toml
setup_config() {
  print_step "1" "Preparing .toml"
  if [[ ! -f config/dev.toml ]]; then
    print_error "Missing config/dev.toml in $(pwd). Ensure packages/infra/config/dev.toml exists."
    exit 1
  fi
  if [[ ! -f .toml ]]; then
    cp config/dev.toml .toml || { print_error "Failed to copy config/dev.toml to .toml"; exit 1; }
    print_info "Copied dev.toml → .toml"
  else
    print_info ".toml already exists; keeping current settings"
  fi
}

# Bootstrap CDK
bootstrap_cdk() {
  print_step "2" "Bootstrapping CDK"
  npx cdk bootstrap --profile "$AWS_PROFILE" || true
}

# Download Lambda Layers from GitHub if missing
download_lambda_layers() {
  print_step "2.5" "Checking Lambda Layer zip files"

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

# Build
build_cdk() {
  print_step "3" "Building CDK app via Nx"
  cd ../../
  pnpm nx run infra:build --no-cloud
  cd packages/infra
}

# Remove conflicting CloudWatch Log Groups (no prompt)
remove_conflicting_log_groups() {
  print_step "3.5" "Removing conflicting CloudWatch Log Groups"
  aws logs delete-log-group --log-group-name "/aws-idp-ai/vpc/flowlogs" --profile "$AWS_PROFILE" 2>/dev/null || true
}

# Remove conflicting DynamoDB tables (no prompt)
ddb_table_exists() {
  local t="$1"
  aws dynamodb describe-table --table-name "$t" --profile "$AWS_PROFILE" >/dev/null 2>&1
}

wait_for_ddb_deletion() {
  local t="$1"; local timeout=600; local elapsed=0
  while ddb_table_exists "$t" && (( elapsed < timeout )); do
    print_info "Waiting for DynamoDB table deletion: $t (${elapsed}s)"
    sleep 10; elapsed=$((elapsed+10))
  done
}

remove_conflicting_dynamodb_tables() {
  print_step "3.6" "Removing conflicting DynamoDB tables"
  local ACCOUNT_ID REGION
  ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text --profile "$AWS_PROFILE")
  REGION=$(aws configure get region --profile "$AWS_PROFILE" || echo "us-west-2")

  # Known table logical names (updated for new schema)
  local TBL_DOCS="aws-idp-ai-documents-${ACCOUNT_ID}-${REGION}-dynamodb"
  local TBL_PAGES="aws-idp-ai-pages-${ACCOUNT_ID}-${REGION}-dynamodb"
  local TBL_SEGMENTS="aws-idp-ai-segments-${ACCOUNT_ID}-${REGION}-dynamodb" 
  local TBL_INDICES="aws-idp-ai-indices-${ACCOUNT_ID}-${REGION}-dynamodb"
  local TBL_WS="aws-idp-ai-websocket-connections-${ACCOUNT_ID}-${REGION}-dynamodb"

  for T in "$TBL_DOCS" "$TBL_PAGES" "$TBL_SEGMENTS" "$TBL_INDICES" "$TBL_WS"; do
    if ddb_table_exists "$T"; then
      print_warning "Deleting existing DynamoDB table: $T"
      aws dynamodb delete-table --table-name "$T" --profile "$AWS_PROFILE" 2>/dev/null || true
      wait_for_ddb_deletion "$T"
      print_info "Deleted table (or no longer exists): $T"
    fi
  done
}

# Destroy (optional)
get_stack_deletion_order() {
  cat <<EOF
aws-idp-ai-api-gateway
aws-idp-ai-websocket-api
aws-idp-ai-workflow
aws-idp-ai-dynamodb-streams
aws-idp-ai-document-management
aws-idp-ai-indices-management
aws-idp-ai-opensearch
aws-idp-ai-dynamodb
aws-idp-ai-s3
aws-idp-ai-lambda-layer
aws-idp-ai-vpc
EOF
}

destroy_infrastructure() {
  print_step "0" "Destroying existing infrastructure"
  
  # Get all existing stacks
  local existing_stacks
  existing_stacks=$(get_stack_deletion_order)
  
  if $PRESERVE_VPC; then
    print_vpc "Preserving VPC: will delete stacks except VPC"
    existing_stacks=$(echo "$existing_stacks" | grep -v vpc || true)
  fi
  
  # Delete stacks in reverse dependency order
  local stack_count=0
  while IFS= read -r stack_name; do
    [[ -z "$stack_name" ]] && continue
    if stack_exists "$stack_name"; then
      print_info "Deleting stack: $stack_name"
      if aws cloudformation delete-stack --stack-name "$stack_name" --profile "$AWS_PROFILE"; then
        wait_for_stack_deletion "$stack_name" || {
          print_warning "Failed to wait for deletion of $stack_name, continuing..."
        }
        ((stack_count++))
      else
        print_warning "Failed to initiate deletion of $stack_name"
      fi
    else
      print_info "Stack $stack_name does not exist, skipping"
    fi
  done <<< "$existing_stacks"
  
  print_info "Deleted $stack_count stacks"
}

# Deploy
deploy_infrastructure() {
  print_step "4" "Deploying infrastructure"
  
  local deploy_cmd="npx cdk deploy"
  local deploy_args="--require-approval=never --profile \"$AWS_PROFILE\" --verbose"
  
  if [[ -n "$CUSTOM_STACKS" ]]; then
    print_info "Deploying selected stacks: $CUSTOM_STACKS"
    eval "$deploy_cmd $CUSTOM_STACKS $deploy_args" || {
      print_error "Failed to deploy custom stacks: $CUSTOM_STACKS"
      return 1
    }
  elif $PRESERVE_VPC; then
    print_vpc "Excluding VPC stack from deployment"
    # Deploy in dependency order to avoid issues (exclude User-Management)
    local stacks=(
      aws-idp-ai-vpc
      aws-idp-ai-lambda-layer
      aws-idp-ai-s3
      aws-idp-ai-dynamodb
      aws-idp-ai-opensearch
      aws-idp-ai-indices-management
      aws-idp-ai-document-management
      aws-idp-ai-dynamodb-streams
      aws-idp-ai-websocket-api
      aws-idp-ai-workflow
      aws-idp-ai-api-gateway
    )
    local filtered=( )
    for s in "${stacks[@]}"; do
      [[ "$s" != "aws-idp-ai-vpc" ]] && filtered+=("$s")
    done
    
    print_info "Deploying stacks in order: ${filtered[*]}"
    eval "$deploy_cmd ${filtered[*]} $deploy_args" || {
      print_error "Failed to deploy infrastructure stacks"
      return 1
    }
  else
    # Deploy only base infrastructure stacks (exclude ECR/ECS/User-Management)
    local stacks=(
      aws-idp-ai-vpc
      aws-idp-ai-lambda-layer
      aws-idp-ai-s3
      aws-idp-ai-dynamodb
      aws-idp-ai-opensearch
      aws-idp-ai-indices-management
      aws-idp-ai-document-management
      aws-idp-ai-dynamodb-streams
      aws-idp-ai-websocket-api
      aws-idp-ai-workflow
      aws-idp-ai-api-gateway
    )
    print_info "Deploying base stacks (excluding ECR/ECS): ${stacks[*]}"
    eval "$deploy_cmd ${stacks[*]} $deploy_args" || {
      print_error "Failed to deploy base infrastructure stacks"
      return 1
    }
  fi
  
  print_success "Infrastructure deployment completed successfully"
}

# Optional Nori install for Managed OpenSearch
install_nori_plugin() {
  $SKIP_NORI && { print_info "Skipping Nori install"; return; }
  print_step "5" "Installing OpenSearch Nori package (if domain is ready)"
  local DOMAIN_NAME
  DOMAIN_NAME=$(aws opensearch list-domain-names --query "DomainNames[0].DomainName" --output text --profile "$AWS_PROFILE" 2>/dev/null | head -1)
  if [[ -z "$DOMAIN_NAME" || "$DOMAIN_NAME" == "None" ]]; then
    print_warning "No OpenSearch domain found → skipping Nori install"
    return
  fi
  local PROCESSING
  PROCESSING=$(aws opensearch describe-domain --domain-name "$DOMAIN_NAME" --query "DomainStatus.Processing" --output text --profile "$AWS_PROFILE" 2>/dev/null || echo "true")
  if [[ "$PROCESSING" == "true" ]]; then
    print_warning "Domain processing; install Nori later"
    return
  fi
  if ! aws opensearch associate-package --domain-name "$DOMAIN_NAME" --package-id G256321959 --profile "$AWS_PROFILE" >/dev/null 2>&1; then
    print_warning "Nori install request failed or unsupported in this region. Install manually if needed."
  else
    print_info "Nori install requested. It may take several minutes."
  fi
}

# MCP dirs and .env
create_mcp_directories() {
  local PROJECT_ROOT; PROJECT_ROOT=$(cd ../.. && pwd)
  export MCP_WORKSPACE_DIR="$PROJECT_ROOT/mcp-workspace"
  [[ -d "$MCP_WORKSPACE_DIR" ]] || { mkdir -p "$MCP_WORKSPACE_DIR" && chmod 755 "$MCP_WORKSPACE_DIR" 2>/dev/null || true; }
}

setup_ENV() {
  print_step "6" "Creating backend .env file"
  create_mcp_directories
  local ACCOUNT_ID REGION
  ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text --profile "$AWS_PROFILE")
  REGION=$(aws configure get region --profile "$AWS_PROFILE" || echo "us-west-2")

  # Try to fetch API Gateway endpoint if present
  local API_URL
  API_URL=$(aws cloudformation describe-stacks \
    --stack-name "aws-idp-ai-api-gateway" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayEndpoint'].OutputValue" \
    --output text --profile "$AWS_PROFILE" 2>/dev/null || echo "")

  # Try to fetch WebSocket API endpoint
  local WEBSOCKET_URL=""
  WEBSOCKET_URL=$(aws cloudformation describe-stacks \
    --stack-name "aws-idp-ai-websocket-api" \
    --query "Stacks[0].Outputs[?OutputKey=='WebSocketApiEndpointOutput'].OutputValue" \
    --output text --profile "$AWS_PROFILE" 2>/dev/null || echo "")
  
  # WebSocket stage name
  local WEBSOCKET_STAGE=""
  WEBSOCKET_STAGE=$(aws cloudformation describe-stacks \
    --stack-name "aws-idp-ai-websocket-api" \
    --query "Stacks[0].Outputs[?OutputKey=='WebSocketStageNameOutput'].OutputValue" \
    --output text --profile "$AWS_PROFILE" 2>/dev/null || echo "dev")
  
  # Construct full WebSocket URL
  if [[ -n "$WEBSOCKET_URL" && -n "$WEBSOCKET_STAGE" ]]; then
    WEBSOCKET_URL="${WEBSOCKET_URL}/${WEBSOCKET_STAGE}"
  fi

  local ENV_PATH="../../.env"
  [[ -f "../../.env.example" ]] && cp ../../.env.example "$ENV_PATH" || :
  [[ -f "$ENV_PATH" ]] || touch "$ENV_PATH"
  set_file_permissions "$ENV_PATH" "$ENV_PERM"

  # Get DynamoDB table names
  local TBL_DOCS="aws-idp-ai-documents-${ACCOUNT_ID}-${REGION}-dynamodb"
  local TBL_PAGES="aws-idp-ai-pages-${ACCOUNT_ID}-${REGION}-dynamodb"
  local TBL_SEGMENTS="aws-idp-ai-segments-${ACCOUNT_ID}-${REGION}-dynamodb"
  local TBL_INDICES="aws-idp-ai-indices-${ACCOUNT_ID}-${REGION}-dynamodb"
  local TBL_WS="aws-idp-ai-websocket-connections-${ACCOUNT_ID}-${REGION}-dynamodb"

  # Try to get OpenSearch endpoint
  local OS_ENDPOINT=""
  OS_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "aws-idp-ai-opensearch" \
    --query "Stacks[0].Outputs[?OutputKey=='DomainEndpoint'].OutputValue" \
    --output text --profile "$AWS_PROFILE" 2>/dev/null || echo "")

  # Try to get S3 bucket name
  local S3_BUCKET=""
  S3_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "aws-idp-ai-s3" \
    --query "Stacks[0].Outputs[?OutputKey=='DocumentsBucketName'].OutputValue" \
    --output text --profile "$AWS_PROFILE" 2>/dev/null || echo "")

  cat > "$ENV_PATH" <<EOF
# AWS Configuration
AWS_REGION=$REGION
AWS_PROFILE=$AWS_PROFILE
AWS_ACCOUNT_ID=$ACCOUNT_ID
STAGE=dev

# API Configuration
API_BASE_URL=$API_URL
NEXT_PUBLIC_API_BASE_URL=$API_URL
NEXT_PUBLIC_BACKEND_PORT=8000
NEXT_PUBLIC_LOCAL_BACKEND_URL=http://localhost:8000

# WebSocket Configuration
NEXT_PUBLIC_WEBSOCKET_URL=$WEBSOCKET_URL

# OpenSearch Configuration
OPENSEARCH_INDEX=aws-idp-ai-analysis
OPENSEARCH_REGION=$REGION
OPENSEARCH_ENDPOINT=$OS_ENDPOINT

# DynamoDB Table Names
DOCUMENTS_TABLE_NAME=$TBL_DOCS
PAGES_TABLE_NAME=$TBL_PAGES
SEGMENTS_TABLE_NAME=$TBL_SEGMENTS
INDICES_TABLE_NAME=$TBL_INDICES
WEBSOCKET_CONNECTIONS_TABLE_NAME=$TBL_WS

# S3 Configuration
DOCUMENTS_BUCKET_NAME=$S3_BUCKET

# Application Settings
DEBUG_MODE=false
MCP_WORKSPACE_DIR=$MCP_WORKSPACE_DIR

# Chat Agent / MCP settings
DB_PATH=conversation_checkpoints.db
USE_PERSISTENCE=false
MCP_HEALTH_CHECK_TIMEOUT=10.0
SUMMARIZATION_THRESHOLD=12
DEFAULT_TIMEOUT=300.0
MAX_RETRIES=3
RETRY_DELAY=1.0
EOF
  print_info ".env created at $ENV_PATH"
}

env_only_mode() {
  print_info "=== Environment Setup Only Mode ==="
  setup_ENV
  print_info "Done."
}

# Enhanced error handling for main deployment flow
handle_deployment_failure() {
  local exit_code=$1
  local step_name="${2:-unknown step}"
  
  print_error "Deployment failed at: $step_name (exit code: $exit_code)"
  print_warning "To troubleshoot:"
  print_warning "1. Check CloudFormation console for stack events"
  print_warning "2. Review CDK/CloudWatch logs for detailed error information"
  print_warning "3. Consider running with --env-only to generate .env without deploying"
  print_warning "4. Use --stacks to deploy individual stacks for debugging"
  
  return $exit_code
}

main() {
  cd "$(dirname "$0")"
  print_info "=== AWS IDP AI Infrastructure Deployment ==="
  print_info "Profile: $AWS_PROFILE | Region: $(aws configure get region --profile "$AWS_PROFILE" 2>/dev/null || echo "default")"
  
  check_prerequisites || { handle_deployment_failure $? "Prerequisites check"; return 1; }

  $ENV_ONLY && { env_only_mode; return 0; }

  setup_config || { handle_deployment_failure $? "Configuration setup"; return 1; }
  bootstrap_cdk || { handle_deployment_failure $? "CDK bootstrap"; return 1; }
  download_lambda_layers || { handle_deployment_failure $? "Lambda layers download"; return 1; }
  build_cdk || { handle_deployment_failure $? "CDK build"; return 1; }

  # Force-remove known conflicting log groups to avoid AlreadyExists
  remove_conflicting_log_groups || print_warning "Failed to remove conflicting log groups, continuing..."

  # Force-remove known conflicting DynamoDB tables to avoid AlreadyExists
  # remove_conflicting_dynamodb_tables  # Disabled - let CDK handle table lifecycle

  if $DESTROY_INFRASTRUCTURE; then
    destroy_infrastructure || { handle_deployment_failure $? "Infrastructure destruction"; return 1; }
  fi

  deploy_infrastructure || { handle_deployment_failure $? "Infrastructure deployment"; return 1; }
  install_nori_plugin || print_warning "Nori plugin installation failed, continuing..."
  setup_ENV || { handle_deployment_failure $? "Environment setup"; return 1; }
  
  print_success "🎉 AWS IDP AI Infrastructure deployment completed successfully!"
  print_info "Next steps:"
  print_info "1. Review the generated .env file in the project root"
  print_info "2. Use ./deploy-services.sh to deploy ECR/ECS container services"
  print_info "3. Check CloudFormation outputs for endpoint URLs"
}

main "$@"


