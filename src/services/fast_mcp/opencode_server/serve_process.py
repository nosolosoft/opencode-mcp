"""Lifecycle for the isolated OpenCode server used by jobs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


class ServeProcess:
    """Start OpenCode with the job MCP disabled in the child process."""

    def __init__(self, command: str, host: str, port: int) -> None:
        self.command = command
        self.host = host
        self.port = port
        self.process: subprocess.Popen[bytes] | None = None

    def start(self, directory: str) -> None:
        """Start the detached HTTP server when it is not already running."""
        if self.process is not None and self.process.poll() is None:
            return
        environment = os.environ.copy()
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            {
                "mcp": {"opencode": {"enabled": False}},
                "default_agent": "build",
            }
        )
        self.process = subprocess.Popen(
            [self.command, "serve", "--hostname", self.host, "--port", str(self.port)],
            cwd=Path(directory),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def stop(self) -> None:
        """Stop only the process owned by this MCP instance."""
        if self.process is None or self.process.poll() is not None:
            self.process = None
            return
        self.process.terminate()
        self.process = None
