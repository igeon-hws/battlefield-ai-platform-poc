import asyncio

import pytest
from graph_builder.worker import GraphBuilder


async def test_background_writer_retries_transient_database_loss():
    worker = GraphBuilder(None, {})
    restarted = asyncio.Event()
    calls = []

    async def run():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("database temporarily unavailable")
        restarted.set()
        await asyncio.Event().wait()

    worker.run = run
    task = asyncio.create_task(worker.run_forever())
    try:
        await asyncio.wait_for(restarted.wait(), timeout=3)
        assert len(calls) == 2
        assert "ConnectionError" in worker.last_error
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
