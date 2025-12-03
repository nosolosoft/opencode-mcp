"""
OpenCode MCP Server Models
Pydantic models for request/response validation.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OpenCodeResult(BaseModel):
    """Result from OpenCode CLI execution."""

    success: bool = Field(description="Whether the command executed successfully")
    data: Optional[Dict[str, Any] | List[Any] | str] = Field(
        default=None, description="Response data from OpenCode"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    session_id: Optional[str] = Field(
        default=None, description="Session ID for continuation"
    )
    execution_time: float = Field(
        default=0.0, description="Execution time in seconds"
    )
    exit_code: int = Field(default=0, description="CLI exit code")
    raw_output: Optional[str] = Field(
        default=None, description="Raw stdout output"
    )
    stderr: Optional[str] = Field(
        default=None, description="Stderr output if any"
    )


class OpenCodeRunRequest(BaseModel):
    """Request model for opencode_run tool."""

    message: str = Field(description="Message/prompt to send to OpenCode")
    model: Optional[str] = Field(
        default=None, description="Model in provider/model format"
    )
    agent: Optional[str] = Field(default=None, description="Agent to use")
    files: Optional[List[str]] = Field(
        default=None, description="Files to attach to message"
    )
    timeout: int = Field(default=300, description="Timeout in seconds")


class OpenCodeContinueRequest(BaseModel):
    """Request model for opencode_continue_session tool."""

    session_id: str = Field(description="Session ID to continue")
    message: Optional[str] = Field(
        default=None, description="Optional follow-up message"
    )
    timeout: int = Field(default=300, description="Timeout in seconds")


class OpenCodeExecuteRequest(BaseModel):
    """Request model for execute_opencode_command tool."""

    prompt: str = Field(description="Prompt/task for OpenCode")
    model: Optional[str] = Field(
        default=None, description="Model in provider/model format"
    )
    agent: Optional[str] = Field(default=None, description="Agent to use")
    session: Optional[str] = Field(
        default=None, description="Session ID to continue"
    )
    continue_session: bool = Field(
        default=False, description="Whether to continue last session"
    )
    timeout: int = Field(default=300, description="Timeout in seconds")


class OpenCodeModelsRequest(BaseModel):
    """Request model for opencode_list_models tool."""

    provider: Optional[str] = Field(
        default=None, description="Filter by provider (optional)"
    )


class OpenCodeExportRequest(BaseModel):
    """Request model for opencode_export_session tool."""

    session_id: str = Field(description="Session ID to export")


class OpenCodeStatusResponse(BaseModel):
    """Response model for opencode_get_status tool."""

    status: str = Field(description="Status: available or unavailable")
    version: Optional[str] = Field(default=None, description="OpenCode CLI version")
    cli_path: Optional[str] = Field(default=None, description="Path to OpenCode CLI")
    available_models: Optional[List[str]] = Field(
        default=None, description="List of available models"
    )
    error: Optional[str] = Field(default=None, description="Error if unavailable")
