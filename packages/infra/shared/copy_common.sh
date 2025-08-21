#!/bin/bash
# Script to copy common modules to each Lambda function
# This script copies common modules to each Lambda function directory.
# Usage: ./copy_common.sh

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Log helpers
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

SHARED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_SOURCE="$SHARED_DIR/python/common"
FUNCTIONS_DIR="$SHARED_DIR/../src/functions"

print_step "1" "Starting common module copy"
print_info "Source: $COMMON_SOURCE"
print_info "Target: $FUNCTIONS_DIR"

# List of Lambda functions to copy to
LAMBDA_FUNCTIONS=(
    "api/indices-management"
    "api/document-management"
    "step-functions/bda-processor"
    "step-functions/bda-status-checker"
    "step-functions/document-indexer"
    "step-functions/pdf-text-extractor"
    "step-functions/get-document-pages"
    "step-functions/react-analysis"
    "step-functions/analysis-finalizer"
    "step-functions/document-summarizer"
)

if [ ! -d "$COMMON_SOURCE" ]; then
    print_error "Common module directory not found: $COMMON_SOURCE"
    exit 1
fi

print_step "2" "Copying common modules to Lambda functions"
for func in "${LAMBDA_FUNCTIONS[@]}"; do
    FUNC_DIR="$FUNCTIONS_DIR/$func"
    TARGET_DIR="$FUNC_DIR/common"
    
    if [ -d "$FUNC_DIR" ]; then
        print_info "Copying to: $func"
        
        # Remove existing common folder
        [ -d "$TARGET_DIR" ] && rm -rf "$TARGET_DIR"
        
        # Copy new common folder
        cp -r "$COMMON_SOURCE" "$TARGET_DIR"
        
        print_success "$func/common copy completed"
    else
        print_warning "Function directory not found: $func"
    fi
done

print_step "3" "Copy operation completed"
print_success "Common modules copied to all Lambda functions successfully!"