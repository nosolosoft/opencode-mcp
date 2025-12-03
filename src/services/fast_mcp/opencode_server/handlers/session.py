"""
Session Handler
Handles session management operations for OpenCode.
"""

import logging
from typing import Optional

from ..opencode_executor import OpenCodeExecutor
from ..models import OpenCodeResult

logger = logging.getLogger(__name__)


class SessionHandler:
    """Handler for OpenCode session management operations."""

    def __init__(self, executor: OpenCodeExecutor):
        self.executor = executor

    async def export_session(self, session_id: str) -> OpenCodeResult:
        """
        Export a session as JSON.

        Args:
            session_id: The session ID to export

        Returns:
            OpenCodeResult with exported session data
        """
        logger.info(f"Exporting session: {session_id}")

        result = await self.executor.export_session(session_id)

        if result.success:
            logger.info(f"Session exported successfully in {result.execution_time:.1f}s")
        else:
            logger.warning(f"Session export failed: {result.error}")

        return result

    async def get_stats(self) -> OpenCodeResult:
        """
        Get OpenCode usage statistics.

        Returns:
            OpenCodeResult with usage statistics
        """
        logger.info("Getting OpenCode stats")

        result = await self.executor.get_stats()

        if result.success:
            logger.info(f"Stats retrieved successfully in {result.execution_time:.1f}s")
        else:
            logger.warning(f"Stats retrieval failed: {result.error}")

        return result
