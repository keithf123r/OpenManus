"""Circuit breaker pattern for search engine fallback with intelligent failure handling."""

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

from pydantic import BaseModel, Field

from app.logger import logger

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failures exceeded threshold, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerStats(BaseModel):
    """Statistics for a circuit breaker."""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    consecutive_failures: int = 0
    state: CircuitState = CircuitState.CLOSED
    state_changed_at: float = Field(default_factory=time.time)


class SearchEngineCircuitBreaker:
    """Circuit breaker for search engines with exponential backoff and failure tracking."""
    
    def __init__(
        self,
        failure_threshold: int = 3,
        success_threshold: int = 2,
        timeout: float = 60.0,
        half_open_timeout: float = 30.0,
        exponential_backoff_base: float = 2.0
    ):
        """Initialize the circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes in half-open before closing
            timeout: Seconds before transitioning from open to half-open
            half_open_timeout: Timeout for requests in half-open state
            exponential_backoff_base: Base for exponential backoff calculation
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.half_open_timeout = half_open_timeout
        self.exponential_backoff_base = exponential_backoff_base
        
        self._stats: Dict[str, CircuitBreakerStats] = defaultdict(CircuitBreakerStats)
        self._lock = asyncio.Lock()
    
    async def call(
        self,
        engine_name: str,
        operation: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """Execute an operation through the circuit breaker.
        
        Args:
            engine_name: Name of the search engine
            operation: Async function to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation
            
        Returns:
            Result from the operation
            
        Raises:
            CircuitOpenError: If circuit is open
            Exception: Any exception from the operation
        """
        async with self._lock:
            stats = self._stats[engine_name]
            self._update_state(engine_name)
            
            if stats.state == CircuitState.OPEN:
                wait_time = self._get_backoff_time(stats)
                raise CircuitOpenError(
                    f"Circuit breaker for {engine_name} is OPEN. "
                    f"Retry after {wait_time:.1f} seconds."
                )
        
        try:
            # Execute with appropriate timeout
            timeout = (
                self.half_open_timeout 
                if stats.state == CircuitState.HALF_OPEN 
                else None
            )
            
            if timeout:
                result = await asyncio.wait_for(
                    operation(*args, **kwargs),
                    timeout=timeout
                )
            else:
                result = await operation(*args, **kwargs)
            
            await self._on_success(engine_name)
            return result
            
        except Exception as e:
            await self._on_failure(engine_name, e)
            raise
    
    async def _on_success(self, engine_name: str) -> None:
        """Handle successful operation."""
        async with self._lock:
            stats = self._stats[engine_name]
            stats.success_count += 1
            stats.last_success_time = time.time()
            stats.consecutive_failures = 0
            
            if stats.state == CircuitState.HALF_OPEN:
                if stats.success_count >= self.success_threshold:
                    logger.info(f"Circuit breaker for {engine_name} transitioning to CLOSED")
                    stats.state = CircuitState.CLOSED
                    stats.state_changed_at = time.time()
                    stats.failure_count = 0
                    stats.success_count = 0
    
    async def _on_failure(self, engine_name: str, error: Exception) -> None:
        """Handle failed operation."""
        async with self._lock:
            stats = self._stats[engine_name]
            stats.failure_count += 1
            stats.consecutive_failures += 1
            stats.last_failure_time = time.time()
            
            logger.warning(
                f"Search engine {engine_name} failed: {error}. "
                f"Consecutive failures: {stats.consecutive_failures}"
            )
            
            if stats.state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit breaker for {engine_name} transitioning to OPEN")
                stats.state = CircuitState.OPEN
                stats.state_changed_at = time.time()
                stats.success_count = 0
            elif (
                stats.state == CircuitState.CLOSED and
                stats.consecutive_failures >= self.failure_threshold
            ):
                logger.info(f"Circuit breaker for {engine_name} transitioning to OPEN")
                stats.state = CircuitState.OPEN
                stats.state_changed_at = time.time()
    
    def _update_state(self, engine_name: str) -> None:
        """Update circuit state based on timeout."""
        stats = self._stats[engine_name]
        
        if stats.state == CircuitState.OPEN:
            time_in_open = time.time() - stats.state_changed_at
            backoff_time = self._get_backoff_time(stats)
            
            if time_in_open >= backoff_time:
                logger.info(f"Circuit breaker for {engine_name} transitioning to HALF_OPEN")
                stats.state = CircuitState.HALF_OPEN
                stats.state_changed_at = time.time()
                stats.failure_count = 0
                stats.success_count = 0
    
    def _get_backoff_time(self, stats: CircuitBreakerStats) -> float:
        """Calculate exponential backoff time based on consecutive failures."""
        base_timeout = self.timeout
        consecutive_failures = min(stats.consecutive_failures, 10)  # Cap at 10
        return base_timeout * (self.exponential_backoff_base ** (consecutive_failures - 1))
    
    def get_status(self, engine_name: str) -> Dict[str, Any]:
        """Get current status of a circuit breaker."""
        stats = self._stats[engine_name]
        self._update_state(engine_name)
        
        status = {
            "engine": engine_name,
            "state": stats.state.value,
            "consecutive_failures": stats.consecutive_failures,
            "failure_count": stats.failure_count,
            "success_count": stats.success_count,
        }
        
        if stats.state == CircuitState.OPEN:
            time_in_open = time.time() - stats.state_changed_at
            backoff_time = self._get_backoff_time(stats)
            remaining = max(0, backoff_time - time_in_open)
            status["retry_after_seconds"] = remaining
        
        return status
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {
            engine: self.get_status(engine)
            for engine in self._stats
        }
    
    def is_available(self, engine_name: str) -> bool:
        """Check if an engine is available (not in OPEN state)."""
        self._update_state(engine_name)
        return self._stats[engine_name].state != CircuitState.OPEN
    
    def reset(self, engine_name: Optional[str] = None) -> None:
        """Reset circuit breaker state."""
        if engine_name:
            self._stats[engine_name] = CircuitBreakerStats()
            logger.info(f"Circuit breaker for {engine_name} reset")
        else:
            self._stats.clear()
            logger.info("All circuit breakers reset")


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass