"""
Retry Handler
Exponential backoff retry logic for OpenCode command execution.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..settings import settings

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = settings.retry_max_attempts
    backoff_factor: float = settings.retry_backoff_factor
    retry_on_timeout: bool = settings.retry_on_timeout
    retry_on_exit_codes: List[int] = field(default_factory=lambda: [-1])
    # Exit codes that should never be retried (auth errors, etc.)
    no_retry_exit_codes: List[int] = field(default_factory=lambda: [2, 126, 127])

    def should_retry(self, exit_code: int, is_timeout: bool, attempt: int) -> bool:
        """
        Determine if a failed execution should be retried.

        Args:
            exit_code: The process exit code
            is_timeout: Whether the failure was a timeout
            attempt: Current attempt number (0-indexed)

        Returns:
            True if the execution should be retried
        """
        if attempt >= self.max_retries:
            return False

        if exit_code in self.no_retry_exit_codes:
            return False

        if is_timeout and self.retry_on_timeout:
            return True

        if exit_code in self.retry_on_exit_codes:
            return True

        return False

    def get_adjusted_timeout(self, base_timeout: int, attempt: int) -> int:
        """
        Calculate the timeout for a retry attempt with exponential backoff.

        Args:
            base_timeout: Original timeout in seconds
            attempt: Current attempt number (0-indexed)

        Returns:
            Adjusted timeout in seconds
        """
        if attempt == 0:
            return base_timeout

        adjusted = int(base_timeout * (self.backoff_factor ** attempt))
        # Cap at max_timeout from settings
        return min(adjusted, settings.max_timeout)

    def get_backoff_delay(self, attempt: int) -> float:
        """
        Calculate the delay before a retry attempt.

        Args:
            attempt: Current attempt number (1-indexed for retry)

        Returns:
            Delay in seconds before retry
        """
        # Short delay: 1s, 1.5s, 2.25s, etc.
        return self.backoff_factor ** attempt


async def execute_with_retry(
    execute_fn: Callable,
    retry_config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable] = None,
):
    """
    Execute a function with retry logic.

    Args:
        execute_fn: Async callable that returns an OpenCodeResult
        retry_config: Retry configuration (defaults to settings-based config)
        on_retry: Optional callback called before each retry with (attempt, result)

    Returns:
        The final OpenCodeResult (from success or last attempt)
    """
    config = retry_config or RetryConfig()
    last_result = None

    for attempt in range(config.max_retries + 1):
        result = await execute_fn(attempt)
        last_result = result

        if result.success:
            if attempt > 0:
                logger.info(f"Succeeded on retry attempt {attempt}")
                result.retry_count = attempt
            return result

        # Determine if this was a timeout
        is_timeout = result.exit_code == -1 or (
            result.error and "timed out" in result.error.lower()
        )

        if not config.should_retry(result.exit_code, is_timeout, attempt):
            if attempt > 0:
                result.retry_count = attempt
            return result

        # Calculate backoff delay
        delay = config.get_backoff_delay(attempt + 1)
        logger.warning(
            f"Attempt {attempt + 1}/{config.max_retries + 1} failed "
            f"(exit_code={result.exit_code}, timeout={is_timeout}). "
            f"Retrying in {delay:.1f}s..."
        )

        if on_retry:
            await on_retry(attempt + 1, result)

        await asyncio.sleep(delay)

    # All attempts exhausted
    if last_result:
        last_result.retry_count = config.max_retries
    return last_result
