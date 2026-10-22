import os
import subprocess
import sys

import httpx
import pytest
from conftest import server


@pytest.mark.parametrize("system,key", [("atcis", "equipment"), ("knccs", "own-forces")])
def test_source_wheel_installs_and_runs_without_other_services(tmp_path, system, key):
    wheels = tmp_path / "wheels"
    for package in (
        "packages/c4i-contracts",
        "packages/geo",
        "packages/source-runtime",
        f"services/mock-{system}",
    ):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(wheels),
                package,
            ],
            check=True,
            capture_output=True,
        )
    venv = tmp_path / "isolated"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "--find-links",
            str(wheels),
            f"mock-{system}==0.1.0",
        ],
        check=True,
        capture_output=True,
    )
    code = f"import importlib.util,uvicorn; from mock_{system}.app import create_app; assert all(importlib.util.find_spec(m) is None for m in ('battlefield_ontology','openai','neo4j','mcp','platform_api','mock_{'knccs' if system == 'atcis' else 'atcis'}')); uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')"
    with server(
        code,
        {
            "PATH": "",
            "OPENAI_API_KEY": "",
            "OPENAI_MODEL": "",
            "C4I_CONTRACT_VERSION": "3",
            f"{system.upper()}_DB": str(tmp_path / "standalone.db"),
            f"{system.upper()}_READ_TOKEN": "",
            f"{system.upper()}_CONTROL_TOKEN": "",
        },
        executable=str(python),
    ) as url:
        assert httpx.get(url + "/").status_code == 200
        snapshot = httpx.get(url + "/api/v1/snapshot").json()
        assert snapshot["systemId"] == system and snapshot["records"][key]
        assert httpx.post(url + "/api/v1/simulation/start").status_code == 200
