from src.services.fast_mcp.opencode_server.server import build_tools


def test_public_tool_catalog_contains_only_job_and_discovery_tools() -> None:
    names = {tool.name for tool in build_tools()}

    assert names == {
        "opencode_job_start",
        "opencode_job_status",
        "opencode_job_result",
        "opencode_job_respond",
        "opencode_job_cancel",
        "opencode_job_list",
        "opencode_list_agents",
        "opencode_list_models",
        "opencode_list_sessions",
        "opencode_health_check",
    }
