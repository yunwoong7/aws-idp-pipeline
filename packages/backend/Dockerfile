# Backend Dockerfile for ECS deployment
# Use ECR Public Gallery Python image to avoid Docker Hub rate limits
FROM public.ecr.aws/docker/library/python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy requirements and install Python dependencies with uv
COPY packages/backend/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY packages/backend/ .

# Create necessary directories
RUN mkdir -p config mcp-workspace

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# Set project root for Docker environment
ENV PROJECT_ROOT=/app
ENV MCP_WORKSPACE_DIR=/app/mcp-workspace

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]