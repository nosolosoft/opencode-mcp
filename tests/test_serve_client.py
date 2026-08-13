import httpx
import pytest

from src.services.fast_mcp.opencode_server.serve_client.client import (
    OpenCodeServeClient,
    ServerNotRunningError,
)


@pytest.mark.asyncio
async def test_connect_converts_startup_read_timeout_to_server_not_running(monkeypatch) -> None:
    class SlowClient:
        async def get(self, path: str) -> None:
            raise httpx.ReadTimeout("server is still starting")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "src.services.fast_mcp.opencode_server.serve_client.client.httpx.AsyncClient",
        lambda **kwargs: SlowClient(),
    )
    client = OpenCodeServeClient(timeout=0.01)

    with pytest.raises(ServerNotRunningError):
        await client.connect()

    assert client._client is None
