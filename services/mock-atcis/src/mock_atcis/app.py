import json
import os
from pathlib import Path

import uvicorn
from battlefield_source_runtime.app import create_source_app
from dotenv import load_dotenv


def create_app(path=None, *, tick_enabled=True, token=None, control_token=None):
    load_dotenv()
    root = Path(__file__).parent
    seed = json.loads((root / "scenario.json").read_text(encoding="utf-8"))
    return create_source_app(
        "atcis",
        seed,
        Path(path or os.getenv("ATCIS_DB", "var/atcis-v2.db")),
        root / "web_static",
        tick_enabled=tick_enabled,
        token=os.getenv("ATCIS_READ_TOKEN", "") if token is None else token,
        control_token=os.getenv("ATCIS_CONTROL_TOKEN", "")
        if control_token is None
        else control_token,
    )


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("ATCIS_PORT", "4100")))
