import pytest

from src.services.fast_mcp.opencode_server.models import OpenCodeResult
from src.services.fast_mcp.opencode_server.opencode_executor import OpenCodeExecutor


@pytest.mark.asyncio
async def test_list_models_returns_clean_ids_from_cli_output(monkeypatch) -> None:
    async def execute_command(self, args, **kwargs):
        return OpenCodeResult(
            success=True,
            raw_output=(
                "openai/gpt-5.6-luna\n"
                "google/gemini-3.1-pro-preview\n"
                "openai/gpt-5.6-luna\n"
            ),
        )

    monkeypatch.setattr(OpenCodeExecutor, "execute_command", execute_command)

    result = await OpenCodeExecutor().list_models()

    assert result.data == [
        "openai/gpt-5.6-luna",
        "google/gemini-3.1-pro-preview",
    ]
    assert result.raw_output is None
