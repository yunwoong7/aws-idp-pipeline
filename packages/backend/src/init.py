"""
FastAPI application initialization module
"""

from fastapi import FastAPI
from aws_lambda_powertools import Tracer

# create FastAPI application instance
app = FastAPI(
    title="AWS IDP AI Analysis API",
    description=" AWS IDP AI Analysis API Server",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False  # disable automatic redirect
)

# initialize AWS Lambda Powertools Tracer
tracer = Tracer()