# Backend Dockerfile for ECS deployment
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy requirements and install Python dependencies with uv
COPY packages/backend/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy .env file for environment variables and remove AWS_PROFILE
COPY .env .env.tmp
RUN grep -v '^AWS_PROFILE=' .env.tmp > .env && rm .env.tmp

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

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["python", "main.py"]