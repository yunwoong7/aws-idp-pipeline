#!/bin/bash

# run_eval.sh - Script to run promptfoo evaluation with proper environment setup

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$BACKEND_DIR")")"

echo "Script directory: $SCRIPT_DIR"
echo "Backend directory: $BACKEND_DIR"
echo "Project root: $PROJECT_ROOT"

# Set environment variables
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# Change to the eval directory
cd "$SCRIPT_DIR"

# Check if .env file exists and source it
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Loading environment from $PROJECT_ROOT/.env"
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

if [ -f "$BACKEND_DIR/.env" ]; then
    echo "Loading environment from $BACKEND_DIR/.env"
    set -a
    source "$BACKEND_DIR/.env"
    set +a
fi

# Run promptfoo evaluation
echo "Running promptfoo evaluation..."

# Check if user wants to use real agent or simple agent
if [ "$1" = "--real" ]; then
    echo "Using real agent implementation"
    # Modify config to use real agent
    sed -i.bak 's/# - file:\/\/\.\/promptfoo_chat_agent\.py/- file:\/\/\.\/promptfoo_chat_agent\.py/g' promptfooconfig.yaml
    sed -i.bak 's/- file:\/\/\.\/promptfoo_simple_agent\.py/# - file:\/\/\.\/promptfoo_simple_agent\.py/g' promptfooconfig.yaml
else
    echo "Using simplified agent implementation"
    # Ensure we're using simple agent
    sed -i.bak 's/^[[:space:]]*- file:\/\/\.\/promptfoo_chat_agent\.py/# - file:\/\/\.\/promptfoo_chat_agent\.py/g' promptfooconfig.yaml
    sed -i.bak 's/^[[:space:]]*# - file:\/\/\.\/promptfoo_simple_agent\.py/- file:\/\/\.\/promptfoo_simple_agent\.py/g' promptfooconfig.yaml
fi

# Run the evaluation
promptfoo eval

# Restore backup if it exists
if [ -f "promptfooconfig.yaml.bak" ]; then
    echo "Restoring original config..."
    mv promptfooconfig.yaml.bak promptfooconfig.yaml
fi

echo "Evaluation complete!"