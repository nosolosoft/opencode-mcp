from src.services.fast_mcp.opencode_server.serve_process import ServeProcess


def test_serve_process_builds_an_isolated_child_environment(monkeypatch, tmp_path) -> None:
    captured = {}

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr(
        "src.services.fast_mcp.opencode_server.serve_process.subprocess.Popen",
        fake_popen,
    )
    process = ServeProcess("opencode", "127.0.0.1", 4097)

    process.start(str(tmp_path))

    assert captured["command"] == ["opencode", "serve", "--hostname", "127.0.0.1", "--port", "4097"]
    assert '"opencode": {"enabled": false}' in captured["environment"]["OPENCODE_CONFIG_CONTENT"]
