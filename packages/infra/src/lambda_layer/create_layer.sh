#!/bin/bash
# usage: add required packages to REQUIREMENTS below and run
# cd /workspaces/aws-idp-pipeline && ./packages/infra/src/lambda_layer/create_layer.sh
# cdk stack should be written as follows
# const customLayer = new lambda.LayerVersion(this, 'CustomLayer', {
#   code: lambda.Code.fromAsset('./src/lambda_layer/custom_package.zip'),
#   compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
#   description: 'Custom Lambda Layer',
# });

set -e

# script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "📁 script location: $SCRIPT_DIR"

# temporary directory
TEMP_DIR="$SCRIPT_DIR/temp_package"
PYTHON_DIR="$TEMP_DIR/python"
ZIP_PATH="$SCRIPT_DIR/custom_package.zip"

echo "📦 creating temporary directory: $TEMP_DIR"
rm -rf "$TEMP_DIR"
mkdir -p "$PYTHON_DIR"

# package list
# REQUIREMENTS="langchain_aws langchain_core langgraph pydantic aws_xray_sdk opensearch-py pillow"
# REQUIREMENTS="pillow PyMuPDF PyPDF2"
# REQUIREMENTS="opensearch-py"
REQUIREMENTS="boto3 opensearch-py pillow PyMuPDF PyPDF2"

# install
echo "local pip install (warning: compatibility not guaranteed)"
pip install --target "$PYTHON_DIR" \
--platform manylinux2014_x86_64 \
--implementation cp --python-version 3.13 \
--only-binary=:all: --upgrade $REQUIREMENTS

# remove existing zip
[ -f "$ZIP_PATH" ] && rm "$ZIP_PATH"

# create zip
echo "📦 creating zip file..."
cd "$TEMP_DIR"
zip -r "$ZIP_PATH" python > /dev/null

# result
echo "✅ Lambda Layer ZIP file created: $ZIP_PATH"
du -h "$ZIP_PATH"

# clean up
echo "🧹 cleaning up temporary directory..."
rm -rf "$TEMP_DIR"

echo "👋 script completed" 