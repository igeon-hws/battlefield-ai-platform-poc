import os

import uvicorn
from battlefield_source_runtime.mcp import create_mcp_app
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    return create_mcp_app(
        "atcis",
        os.getenv("ATCIS_BASE_URL", "http://127.0.0.1:4100"),
        os.getenv("ATCIS_READ_TOKEN", ""),
        os.getenv("ATCIS_MCP_TOKEN", ""),
    )


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("ATCIS_MCP_PORT", "4200")))
