"""
OpenCode MCP Server Settings
Configuration management using Pydantic BaseSettings with environment variables.
"""

from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """OpenCode MCP Server configuration."""

    # OpenCode CLI Configuration
    opencode_command: str = "opencode"
    opencode_default_model: Optional[str] = (
        "openai/gpt-5.5"
    )
    opencode_default_agent: Optional[str] = None

    # Timeout Configuration (per-operation)
    default_timeout: int = 600  # 10 minutes - prompts
    max_timeout: int = 1800  # 30 minutes
    timeout_list_models: int = 30  # 30s for listing models
    timeout_list_sessions: int = 30  # 30s for listing sessions
    timeout_health: int = 15  # 15s for health checks
    timeout_search: int = 45  # 45s for text search and file find (ripgrep)
    timeout_file_ops: int = 15  # 15s for read_file, list_directory, file_status
    timeout_buffer: int = 30  # Buffer between subprocess and MCP timeout

    # Retry Configuration
    retry_max_attempts: int = 2  # Max retry attempts (0 = no retries)
    retry_backoff_factor: float = 1.5  # Exponential backoff multiplier
    retry_on_timeout: bool = True  # Retry on timeout errors

    # Token limits (soft limit via prompt instruction)
    default_max_output_tokens: int = 25000  # Default max output tokens

    # Server Configuration
    server_log_level: str = "INFO"
    mcp_server_name: str = "opencode-mcp"
    mcp_server_version: str = "2.0.0"

    # Security Configuration
    allowed_operations: List[str] = [
        "run",
        "continue",
        "models",
        "export",
        "stats",
        "version",
    ]

    # oh-my-opencode Integration
    ultrawork_enabled: bool = False
    ultrawork_keyword: str = "ulw"  # Keyword to inject (ulw = ultrawork shorthand)

    job_db: Path = Path("~/.local/state/opencode-mcp/jobs.db")
    opencode_serve_host: str = "127.0.0.1"
    opencode_serve_port: int = 4097
    job_stale_after_seconds: int = 180

    # Search & File Limits
    max_search_results: int = 200  # Hard limit on text search matches
    max_file_read_size: int = 100 * 1024  # 100KB max file content returned

    # File Configuration
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_file_extensions: List[str] = [
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".cpp",
        ".c",
        ".h",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        ".cs",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".html",
        ".css",
        ".scss",
        ".md",
        ".txt",
        ".sh",
        ".bash",
        ".sql",
        ".graphql",
    ]

    class Config:
        env_prefix = "OPENCODE_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()
