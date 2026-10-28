import os

import uvicorn
from battlefield_source_runtime.mcp import create_mcp_app
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    if os.getenv("C4I_CONTRACT_VERSION") in ("3", "4", "5"):
        from battlefield_source_runtime.native_mcp import create_native_mcp

        return create_native_mcp(
            "atcis",
            os.getenv("ATCIS_BASE_URL", "http://127.0.0.1:4100"),
            os.getenv("ATCIS_READ_TOKEN", ""),
            os.getenv("ATCIS_MCP_TOKEN", ""),
        )
    return create_mcp_app(
        "atcis",
        os.getenv("ATCIS_BASE_URL", "http://127.0.0.1:4100"),
        os.getenv("ATCIS_READ_TOKEN", ""),
        os.getenv("ATCIS_MCP_TOKEN", ""),
    )


def main():
    load_dotenv()
    os.environ.setdefault("C4I_CONTRACT_VERSION", "4")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("ATCIS_MCP_PORT", "4200")))
