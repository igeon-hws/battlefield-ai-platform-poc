import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx
import pytest


@contextmanager
def server(code: str, env=None, executable=None):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [executable or sys.executable, "-c", code.replace("PORT", str(port))],
        env={**os.environ, **(env or {})},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(process.stderr.read().decode(errors="replace"))
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise TimeoutError("server did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        process.wait(timeout=10)
        if process.stderr:
            process.stderr.close()


@pytest.fixture
def c4i_url(tmp_path):
    with server(
        "import uvicorn; from mock_c4i.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
        {
            "C4I_DB": str(tmp_path / "source.db"),
            "C4I_READ_TOKEN": "test-read",
            "C4I_CONTROL_TOKEN": "test-control",
            "C4I_SCENARIO": "west-coast-demo",
        },
    ) as url:
        yield url


@pytest.fixture
def mcp_url(c4i_url):
    with server(
        "import uvicorn; from c4i_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
        {"C4I_BASE_URL": c4i_url, "C4I_READ_TOKEN": "test-read", "MCP_TOKEN": "test-mcp"},
    ) as url:
        yield url + "/mcp"
