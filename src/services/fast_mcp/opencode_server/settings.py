"""
OpenCode MCP Server Settings
Configuration management using Pydantic BaseSettings with environment variables.
"""

from typing import Optional, List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """OpenCode MCP Server configuration."""

    # OpenCode CLI Configuration
    opencode_command: str = "opencode"
    opencode_default_model: Optional[str] = "google/antigravity-claude-opus-4-5-thinking"
    opencode_default_agent: Optional[str] = None

    # Timeout Configuration
    default_timeout: int = 600  # 10 minutes
    max_timeout: int = 1800  # 30 minutes

    # Server Configuration
    server_log_level: str = "INFO"
    mcp_server_name: str = "opencode-mcp"
    mcp_server_version: str = "1.0.0"

    # Security Configuration
    allowed_operations: List[str] = [
        "run", "continue", "models", "export", "stats", "version"
    ]

    # File Configuration
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_file_extensions: List[str] = [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
        ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".cs",
        ".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css", ".scss",
        ".md", ".txt", ".sh", ".bash", ".sql", ".graphql"
    ]

    class Config:
        env_prefix = "OPENCODE_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()
