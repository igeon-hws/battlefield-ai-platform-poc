import os

import uvicorn
from battlefield_source_runtime.mcp import create_mcp_app
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    return create_mcp_app(
        "knccs",
        os.getenv("KNCCS_BASE_URL", "http://127.0.0.1:4110"),
        os.getenv("KNCCS_READ_TOKEN", ""),
        os.getenv("KNCCS_MCP_TOKEN", ""),
    )


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("KNCCS_MCP_PORT", "4210")))
