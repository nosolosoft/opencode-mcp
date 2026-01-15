"""
Execution Handler
Handles run and continue operations for OpenCode.
"""

import logging
from typing import List, Optional

from ..opencode_executor import OpenCodeExecutor
from ..models import OpenCodeResult

logger = logging.getLogger(__name__)


class ExecutionHandler:
    """Handler for OpenCode execution operations."""

    def __init__(self, executor: OpenCodeExecutor):
        self.executor = executor

    async def run(
        self,
        message: str,
        model: Optional[str] = None,
        agent: Optional[str] = None,
        files: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        variant: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        Run OpenCode with a prompt.

        Args:
            message: The prompt/message to send
            model: Optional model in provider/model format
            agent: Optional agent to use
            files: Optional list of files to attach
            timeout: Optional timeout in seconds
            max_output_tokens: Optional maximum tokens for response (soft limit)
            variant: Optional model variant (minimal/low/medium/high) for Gemini models

        Returns:
            OpenCodeResult with execution results
        """
        logger.info(f"Running OpenCode with message: {message[:100]}...")

        # Apply soft token limit via prompt instruction
        if max_output_tokens:
            modified_message = (
                f"IMPORTANT: Limit your response to a maximum of {max_output_tokens} tokens.\n\n"
                f"{message}"
            )
            logger.info(f"Applying soft token limit: {max_output_tokens}")
        else:
            modified_message = message

        result = await self.executor.run_prompt(
            message=modified_message,
            model=model,
            agent=agent,
            files=files,
            timeout=timeout,
            variant=variant,
        )

        if result.success:
            logger.info(f"Run completed successfully in {result.execution_time:.1f}s")
        else:
            logger.warning(f"Run failed: {result.error}")

        return result

    async def continue_session(
        self,
        session_id: str,
        message: Optional[str] = None,
        timeout: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
    ) -> OpenCodeResult:
        """
        Continue an existing OpenCode session.

        Args:
            session_id: The session ID to continue
            message: Optional follow-up message
            timeout: Optional timeout in seconds
            max_output_tokens: Optional maximum tokens for response (soft limit)

        Returns:
            OpenCodeResult with execution results
        """
        logger.info(f"Continuing session: {session_id}")

        # Apply soft token limit if message provided
        modified_message = message
        if message and max_output_tokens:
            modified_message = (
                f"IMPORTANT: Limit your response to a maximum of {max_output_tokens} tokens.\n\n"
                f"{message}"
            )
            logger.info(f"Applying soft token limit to session: {max_output_tokens}")

        result = await self.executor.continue_session(
            session_id=session_id,
            message=modified_message,
            timeout=timeout,
        )

        if result.success:
            logger.info(
                f"Session continued successfully in {result.execution_time:.1f}s"
            )
        else:
            logger.warning(f"Continue session failed: {result.error}")

        return result

    async def execute_generic(
        self,
        prompt: str,
        model: Optional[str] = None,
        agent: Optional[str] = None,
        session: Optional[str] = None,
        continue_session: bool = False,
        timeout: Optional[int] = None,
    ) -> OpenCodeResult:
        """
        Execute a generic OpenCode command.

        This is the most flexible execution method that supports
        all optional parameters.

        Args:
            prompt: The prompt/task for OpenCode
            model: Optional model in provider/model format
            agent: Optional agent to use
            session: Optional session ID to continue
            continue_session: Whether to continue last session
            timeout: Optional timeout in seconds

        Returns:
            OpenCodeResult with execution results
        """
        logger.info(f"Executing generic command: {prompt[:100]}...")

        # Build args - flags FIRST, prompt LAST
        args = ["run"]

        if model:
            args.extend(["--model", model])
        if agent:
            args.extend(["--agent", agent])
        if session:
            args.extend(["--session", session])
        if continue_session:
            args.append("--continue")

        # Add prompt as LAST positional argument
        args.append(prompt)

        result = await self.executor.execute_command(args, timeout=timeout)

        if result.success:
            logger.info(
                f"Command completed successfully in {result.execution_time:.1f}s"
            )
        else:
            logger.warning(f"Command failed: {result.error}")

        return result
