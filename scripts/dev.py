"""Run three independent Python services. Ctrl+C stops only these child processes."""

import os
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


def start_service(module):
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", f"from {module} import main; main()"],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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


def main():
    load_dotenv(ROOT / ".env")
    c4i_port = int(os.getenv("C4I_PORT", "4100"))
    mcp_port = int(os.getenv("MCP_PORT", "4200"))
    platform_port = int(os.getenv("PLATFORM_PORT", "4300"))
    check_ports([("Mock C4I", c4i_port), ("MCP", mcp_port), ("Platform", platform_port)])
    processes = []
    try:
        for module in ("mock_c4i.app", "c4i_mcp.server", "platform_api.app"):
            process, reader = start_service(module)
            processes.append((module, process, reader))
        print(
            f"Mock C4I http://127.0.0.1:{c4i_port} | Platform http://127.0.0.1:{platform_port}",
            flush=True,
        )
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
