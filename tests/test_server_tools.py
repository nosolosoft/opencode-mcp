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


def test_job_start_describes_live_model_and_agent_selection() -> None:
    tool = next(tool for tool in build_tools() if tool.name == "opencode_job_start")
    properties = tool.inputSchema["properties"]

    assert "opencode_list_models" in properties["model"]["description"]
    assert "opencode_list_agents" in properties["agent"]["description"]
