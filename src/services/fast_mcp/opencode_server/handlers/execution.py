"""
Execution Handler
Handles run and continue operations for OpenCode.
"""

import logging
from typing import List, Optional

from ..opencode_executor import OpenCodeExecutor
from ..models import OpenCodeResult
from ..settings import settings

logger = logging.getLogger(__name__)


def construct_token_limited_prompt(message: str, max_tokens: int) -> str:
    """
    Construct a prompt with effective token limit instruction.

    Uses multi-level emphasis, consequences, and contextual cues
    to encourage models to respect the token limit.

    Adapts instruction based on token range:
    - Low (<2000): CRITICAL emphasis, very strict
    - Medium (2000-10000): IMPORTANT, balanced
    - High (>10000): Soft guidance

    Args:
        message: Original user message
        max_tokens: Maximum output tokens allowed

    Returns:
        Modified message with token limit instructions
    """
    # Determine instruction level based on token range
    if max_tokens < 2000:
        # Low range: Critical emphasis
        header = (
            f"CRITICAL TOKEN LIMIT: Your response MUST NOT exceed {max_tokens} tokens. This is a HARD limit.\n"
            f"- Responses exceeding this limit will be rejected\n"
            f"- Be extremely concise and direct\n"
            f"- Prioritize key information only\n"
            f"- Avoid examples, explanations or elaborations unless explicitly requested\n"
        )
        footer = f"\nREMINDER: Maximum {max_tokens} tokens. Keep your response brief and focused."

    elif max_tokens <= 10000:
        # Medium range: Important but balanced
        header = (
            f"IMPORTANT TOKEN CONSTRAINT: Your response must stay within {max_tokens} tokens.\n"
            f"- Responses exceeding this limit will be truncated\n"
            f"- Be concise but complete\n"
            f"- Structure your response for clarity\n"
            f"- Avoid unnecessary verbosity\n"
        )
        footer = f"\nREMINDER: Stay within {max_tokens} tokens total."

    else:
        # High range: Soft guidance
        header = (
            f"TOKEN BUDGET: Please limit your response to approximately {max_tokens} tokens.\n"
            f"- Long responses will be truncated\n"
            f"- Structure your answer efficiently\n"
            f"- Focus on essential information\n"
        )
        footer = f"\nREMINDER: Target limit is {max_tokens} tokens."

    # Construct final prompt with header + message + footer
    return f"{header}\n{message}{footer}"


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
        use_ultrawork: bool = True,
        cwd: Optional[str] = None,
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
            use_ultrawork: Enable oh-my-opencode multi-agent orchestration (default: True)

        Returns:
            OpenCodeResult with execution results
        """
        logger.info(f"Running OpenCode with message: {message[:100]}...")

        # Inject ultrawork keyword for oh-my-opencode multi-agent orchestration
        if use_ultrawork and settings.ultrawork_enabled:
            modified_message = f"{settings.ultrawork_keyword} {message}"
            logger.info(f"Ultrawork enabled: injecting '{settings.ultrawork_keyword}' keyword")
        else:
            modified_message = message

        # Apply soft token limit via improved prompt instruction
        if max_output_tokens:
            modified_message = construct_token_limited_prompt(modified_message, max_output_tokens)
            logger.info(f"Applying improved token limit: {max_output_tokens}")

        result = await self.executor.run_prompt(
            message=modified_message,
            model=model,
            agent=agent,
            files=files,
            timeout=timeout,
            variant=variant,
            cwd=cwd,
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
            modified_message = construct_token_limited_prompt(message, max_output_tokens)
            logger.info(f"Applying improved token limit to session: {max_output_tokens}")

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
