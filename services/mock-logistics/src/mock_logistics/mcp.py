"""Read-only MCP adapter to the public logistics HTTP API."""

import os

import uvicorn
from battlefield_source_runtime.native_mcp import create_native_mcp
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    return create_native_mcp(
        "logistics",
        os.getenv("LOGISTICS_BASE_URL", "http://127.0.0.1:4120"),
        os.getenv("LOGISTICS_READ_TOKEN", ""),
        os.getenv("LOGISTICS_MCP_TOKEN", ""),
    )


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("LOGISTICS_MCP_PORT", "4220")))
