"""Run independent Python services by profile; stop only owned child processes."""

import argparse
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def check_ports(services):
    for name, port in services:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(
                    f"{name}: port {port} is already in use. "
                    "Open the existing UI, or stop the previous server with Ctrl+C before retrying."
                )


def start_service(module, env_overrides=None):
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", f"from {module} import main; main()"],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env_overrides or {})},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    def forward_logs():
        try:
            for line in process.stdout:
                print(f"[{module}] {line.rstrip()}", flush=True)
        finally:
            process.stdout.close()

    reader = threading.Thread(target=forward_logs, daemon=True)
    reader.start()
    return process, reader


def _service_specs(profile):
    platform = ("platform_api.app", int(os.getenv("PLATFORM_PORT", "4300")))
    if profile == "legacy":
        return [
            ("mock_c4i.app", int(os.getenv("C4I_PORT", "4100"))),
            ("c4i_mcp.server", int(os.getenv("MCP_PORT", "4200"))),
            platform,
        ]
    if profile not in ("off", "full"):
        raise ValueError("unknown development profile")
    services = [
        ("mock_atcis.app", int(os.getenv("ATCIS_PORT", "4100"))),
        ("atcis_mcp.server", int(os.getenv("ATCIS_MCP_PORT", "4200"))),
        ("mock_knccs.app", int(os.getenv("KNCCS_PORT", "4110"))),
        ("knccs_mcp.server", int(os.getenv("KNCCS_MCP_PORT", "4210"))),
    ]
    if profile == "full":
        services += [
            ("graph_builder.app", int(os.getenv("BUILDER_PORT", "4420"))),
            ("semantic_api.app", int(os.getenv("SEMANTIC_PORT", "4400"))),
            ("semantic_mcp.server", int(os.getenv("SEMANTIC_MCP_PORT", "4410"))),
        ]
    return services + [platform]


def service_specs(profile, offset=0):
    specs = [(module, port + offset) for module, port in _service_specs(profile)]
    if any(not 1 <= port <= 65535 for _, port in specs):
        raise ValueError("port offset creates an invalid port")
    return specs


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("legacy", "off", "full"), default="legacy")
    parser.add_argument("--port-offset", type=int, default=0)
    args = parser.parse_args()
    specs = service_specs(args.profile, args.port_offset)
    check_ports(specs)
    overrides = {"PLATFORM_PROFILE": "legacy" if args.profile == "legacy" else "heterogeneous"}
    if args.port_offset:
        module_settings = {
            "mock_atcis.app": ("ATCIS_PORT", "ATCIS_BASE_URL"),
            "atcis_mcp.server": ("ATCIS_MCP_PORT", "ATCIS_MCP_URL"),
            "mock_knccs.app": ("KNCCS_PORT", "KNCCS_BASE_URL"),
            "knccs_mcp.server": ("KNCCS_MCP_PORT", "KNCCS_MCP_URL"),
            "graph_builder.app": ("BUILDER_PORT", "BUILDER_BASE_URL"),
            "semantic_api.app": ("SEMANTIC_PORT", "SEMANTIC_BASE_URL"),
            "semantic_mcp.server": ("SEMANTIC_MCP_PORT", "SEMANTIC_MCP_URL"),
            "platform_api.app": ("PLATFORM_PORT", None),
            "mock_c4i.app": ("C4I_PORT", "C4I_BASE_URL"),
            "c4i_mcp.server": ("MCP_PORT", "MCP_SERVER_URL"),
        }
        for module, port in specs:
            port_setting, url_setting = module_settings[module]
            overrides[port_setting] = str(port)
            if url_setting:
                overrides[url_setting] = f"http://127.0.0.1:{port}" + (
                    "/mcp" if "mcp" in module else ""
                )
    if args.profile == "full":
        from neo4j import GraphDatabase

        if not os.getenv("NEO4J_PASSWORD"):
            raise SystemExit("Set NEO4J_PASSWORD in local .env before full profile.")
        try:
            with GraphDatabase.driver(
                os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
                auth=(os.getenv("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
            ) as driver:
                driver.verify_connectivity()
        except Exception as exc:
            raise SystemExit("Neo4j unavailable. Run: docker compose up -d neo4j") from exc
        overrides["BUILDER_ADMIN_TOKEN"] = os.getenv(
            "BUILDER_ADMIN_TOKEN"
        ) or secrets.token_urlsafe(32)
    processes = []
    try:
        for module, port in specs:
            process, reader = start_service(module, overrides)
            processes.append((module, process, reader))
            print(f"{module}: http://127.0.0.1:{port}", flush=True)
        while all(process.poll() is None for _, process, _ in processes):
            time.sleep(0.5)
        for module, process, reader in processes:
            if process.poll() is not None:
                reader.join(timeout=2)
                raise SystemExit(f"{module} exited with code {process.returncode}; see logs above.")
    except KeyboardInterrupt:
        pass
    finally:
        for _, process, _ in processes:
            if process.poll() is None:
                process.terminate()
        for _, process, reader in processes:
            process.wait(timeout=10)
            reader.join(timeout=2)


if __name__ == "__main__":
    main()
