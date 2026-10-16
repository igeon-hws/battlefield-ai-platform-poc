import os
import subprocess
import sys
from zipfile import ZipFile

import httpx
from conftest import server


def test_standalone_c4i_wheel_contains_own_ui_and_no_platform_dependency(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(tmp_path),
            "services/mock-c4i",
        ],
        check=True,
        capture_output=True,
    )
    wheel = next(tmp_path.glob("mock_c4i*.whl"))
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "mock_c4i/web_static/index.html" in names
        assert any(name.startswith("mock_c4i/web_static/assets/") for name in names)
        metadata = archive.read(next(name for name in names if name.endswith("METADATA"))).decode()
        assert "Requires-Dist: platform-api" not in metadata
        assert "Requires-Dist: openai" not in metadata


def test_c4i_runtime_without_node_or_llm_configuration(tmp_path):
    code = "import sys,uvicorn; from mock_c4i.app import create_app; assert 'openai' not in sys.modules and 'platform_api' not in sys.modules; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')"
    with server(
        code,
        {
            "PATH": "",
            "OPENAI_API_KEY": "",
            "OPENAI_MODEL": "",
            "C4I_DB": str(tmp_path / "standalone.db"),
            "C4I_READ_TOKEN": "",
            "C4I_CONTROL_TOKEN": "",
        },
        executable=os.getenv("C4I_STANDALONE_PYTHON"),
    ) as url:
        assert httpx.get(url + "/").status_code == 200
        assert len(httpx.get(url + "/api/v1/snapshot").json()["entities"]) == 120
        assert httpx.get(url + "/api/v1/missing").status_code == 404
