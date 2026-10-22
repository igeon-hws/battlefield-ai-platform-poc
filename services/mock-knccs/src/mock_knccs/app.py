import json
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


def create_app(path=None, *, tick_enabled=True, token=None, control_token=None):
    load_dotenv()
    if os.getenv("C4I_CONTRACT_VERSION") == "3":
        from mock_knccs.native import create_app as native_app

        return native_app(path, tick_enabled=tick_enabled, token=token, control_token=control_token)
    root = Path(__file__).parent
    from battlefield_source_runtime.app import create_source_app

    seed = json.loads((root / "scenario.json").read_text(encoding="utf-8"))
    return create_source_app(
        "knccs",
        seed,
        Path(path or os.getenv("KNCCS_DB", "var/knccs-v2.db")),
        root / "web_static",
        tick_enabled=tick_enabled,
        token=os.getenv("KNCCS_READ_TOKEN", "") if token is None else token,
        control_token=os.getenv("KNCCS_CONTROL_TOKEN", "")
        if control_token is None
        else control_token,
    )


def main():
    load_dotenv()
    os.environ.setdefault("C4I_CONTRACT_VERSION", "3")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("KNCCS_PORT", "4110")))
