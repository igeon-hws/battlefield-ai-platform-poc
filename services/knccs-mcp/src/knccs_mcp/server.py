import os

import uvicorn
from battlefield_source_runtime.mcp import create_mcp_app
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    if os.getenv("C4I_CONTRACT_VERSION") in ("3", "4", "5"):
        from battlefield_source_runtime.native_mcp import create_native_mcp

        return create_native_mcp(
            "knccs",
            os.getenv("KNCCS_BASE_URL", "http://127.0.0.1:4110"),
            os.getenv("KNCCS_READ_TOKEN", ""),
            os.getenv("KNCCS_MCP_TOKEN", ""),
        )
    return create_mcp_app(
        "knccs",
        os.getenv("KNCCS_BASE_URL", "http://127.0.0.1:4110"),
        os.getenv("KNCCS_READ_TOKEN", ""),
        os.getenv("KNCCS_MCP_TOKEN", ""),
    )


def main():
    load_dotenv()
    os.environ.setdefault("C4I_CONTRACT_VERSION", "4")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("KNCCS_MCP_PORT", "4210")))
