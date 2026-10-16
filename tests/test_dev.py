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
