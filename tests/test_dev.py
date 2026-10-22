import importlib.util
import socket
from pathlib import Path

import pytest


def load_dev():
    spec = importlib.util.spec_from_file_location(
        "dev_script", Path(__file__).resolve().parents[1] / "scripts/dev.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_busy_port_is_reported_before_launch():
    dev = load_dev()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(SystemExit, match=f"Mock C4I.*{port}"):
            dev.check_ports([("Mock C4I", port)])


def test_child_error_is_visible(tmp_path, capsys):
    dev = load_dev()
    dev.ROOT = tmp_path
    (tmp_path / "broken_service.py").write_text(
        "import sys\ndef main():\n print('startup failed', file=sys.stderr)\n sys.exit(7)\n"
    )
    process, reader = dev.start_service("broken_service")
    assert process.wait(timeout=10) == 7
    reader.join(timeout=5)
    assert "[broken_service] startup failed" in capsys.readouterr().out


def test_source_only_profile_has_no_graph_services_and_full_profile_does():
    dev = load_dev()
    off = {name for name, _ in dev.service_specs("off")}
    full = {name for name, _ in dev.service_specs("full")}
    assert off == {
        "mock_atcis.app",
        "atcis_mcp.server",
        "mock_knccs.app",
        "knccs_mcp.server",
        "platform_api.app",
        "semantic_api.app",
    }
    assert full - off == {"graph_builder.app", "semantic_mcp.server"}
    assert len(dev.service_specs("legacy")) == 3
    with pytest.raises(ValueError):
        dev.service_specs("invalid")


def test_independent_source_fabric_platform_profiles():
    dev = load_dev()
    assert {n for n, _ in dev.service_specs("sources")} == {"mock_atcis.app", "mock_knccs.app"}
    assert {n for n, _ in dev.service_specs("platform")} == {"platform_api.app"}
    fabric = {n for n, _ in dev.service_specs("fabric")}
    assert {
        "atcis_mcp.server",
        "knccs_mcp.server",
        "semantic_api.app",
        "semantic_mcp.server",
        "graph_builder.app",
    } == fabric


def test_port_offset_keeps_profiles_independent_from_existing_demo():
    dev = load_dev()
    original = dict(dev.service_specs("full"))
    shifted = dict(dev.service_specs("full", offset=1000))
    assert all(shifted[module] == port + 1000 for module, port in original.items())


def test_long_running_test_server_drains_stderr():
    import httpx
    from conftest import server

    code = "import sys,uvicorn; from fastapi import FastAPI; sys.stderr.write('x'*100000); sys.stderr.flush(); app=FastAPI(); app.get('/health')(lambda:{'status':'ok'}); uvicorn.run(app,host='127.0.0.1',port=PORT,log_level='error')"
    with server(code) as url:
        assert httpx.get(url + "/health").status_code == 200
