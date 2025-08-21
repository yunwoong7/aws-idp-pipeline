from phoenix.otel import register
import os
from pathlib import Path
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.trace import set_tracer_provider, Status, StatusCode
from functools import wraps

# Load environment variables using path resolver
try:
    from ..utils.path_resolver import path_resolver
    env_path = path_resolver.project_root / '.env'
    print(f"Using path resolver - env_path: {env_path}")
    load_dotenv(env_path)
except ImportError:
    # Fallback to original logic
    root_dir = Path(__file__).resolve().parents[2]
    env_path = root_dir / '.env'
    print(f"Using fallback - root_dir: {root_dir}")
    print(f"Using fallback - env_path: {env_path}")
    load_dotenv(env_path)

# ==== Load environment variables ====
PHOENIX_API_KEY = os.environ.get("PHOENIX_API_KEY")
PHOENIX_PROJECT_NAME = os.environ.get("PHOENIX_PROJECT_NAME")
PHOENIX_COLLECTOR_ENDPOINT = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")

print(f"PHOENIX_API_KEY: {PHOENIX_API_KEY}")

# ==== Setup Phoenix Tracing ====
def setup_phoenix():
    if PHOENIX_API_KEY:
        try:
            os.environ["PHOENIX_CLIENT_HEADERS"] = f"api_key={PHOENIX_API_KEY}"
            tracer_provider = register(
                project_name=PHOENIX_PROJECT_NAME,
                endpoint="https://app.phoenix.arize.com/v1/traces",
                auto_instrument=True,
                verbose=False
            )
            set_tracer_provider(tracer_provider)  # 전역으로 TracerProvider 설정
        except Exception as e:
            print(f"Error setting up Phoenix tracing: {e}")
            tracer_provider=None
    else:
        print("PHOENIX_API_KEY is not set")
        tracer_provider=None
    
    return tracer_provider