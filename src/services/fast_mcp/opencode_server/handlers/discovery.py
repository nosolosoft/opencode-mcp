"""
Discovery Handler
Handles discovery operations for OpenCode (models, version, status).
"""

import logging
from typing import Optional

from ..opencode_executor import OpenCodeExecutor
from ..models import OpenCodeResult, OpenCodeStatusResponse

logger = logging.getLogger(__name__)


class DiscoveryHandler:
    """Handler for OpenCode discovery operations."""

    def __init__(self, executor: OpenCodeExecutor):
        self.executor = executor

    async def list_models(
        self, provider: Optional[str] = None
    ) -> OpenCodeResult:
        """
        List available models.

        Args:
            provider: Optional provider to filter by

        Returns:
            OpenCodeResult with list of available models
        """
        logger.info(f"Listing models" + (f" for provider: {provider}" if provider else ""))

        result = await self.executor.list_models(provider)

        if result.success:
            logger.info(f"Models listed successfully in {result.execution_time:.1f}s")
        else:
            logger.warning(f"Models listing failed: {result.error}")

        return result

    async def get_version(self) -> OpenCodeResult:
        """
        Get OpenCode CLI version.

        Returns:
            OpenCodeResult with version information
        """
        logger.info("Getting OpenCode version")

        version = await self.executor.get_version()

        if version:
            return OpenCodeResult(
                success=True,
                data={"version": version},
                execution_time=0.0,
            )
        else:
            return OpenCodeResult(
                success=False,
                error="Could not retrieve OpenCode version",
                execution_time=0.0,
            )

    async def get_status(self) -> OpenCodeStatusResponse:
        """
        Check OpenCode CLI availability and status.

        Returns:
            OpenCodeStatusResponse with status information
        """
        logger.info("Checking OpenCode status")

        status = await self.executor.check_status()

        if status.status == "available":
            logger.info(f"OpenCode is available. Version: {status.version}")
        else:
            logger.warning(f"OpenCode is unavailable: {status.error}")

        return status
