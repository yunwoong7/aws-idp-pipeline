"""
Rate limiter for AWS Bedrock API calls
"""
import asyncio
import time
from typing import Optional


class RateLimiter:
    """
    Token bucket rate limiter for API calls
    """
    def __init__(self, rate_per_second: int = 10, burst: int = 15):
        """
        Initialize rate limiter
        
        Args:
            rate_per_second: Sustained rate (tokens refilled per second)
            burst: Maximum burst capacity (bucket size)
        """
        self.rate_per_second = rate_per_second
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary
        
        Args:
            tokens: Number of tokens to acquire
        """
        async with self.lock:
            while self.tokens < tokens:
                # Refill tokens based on elapsed time
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst,
                    self.tokens + elapsed * self.rate_per_second
                )
                self.last_update = now
                
                if self.tokens < tokens:
                    # Wait for tokens to refill
                    wait_time = (tokens - self.tokens) / self.rate_per_second
                    await asyncio.sleep(wait_time)
            
            # Consume tokens
            self.tokens -= tokens


# Global rate limiter for Bedrock API - Ultra conservative
bedrock_rate_limiter = RateLimiter(
    rate_per_second=1,  # 1 request per second - ultra conservative
    burst=2  # Minimal burst capacity
)