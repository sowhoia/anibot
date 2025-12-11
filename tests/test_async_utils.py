import asyncio

import pytest

from app.common.async_utils import chunked, run_with_limited_concurrency


def test_chunked_splits_iterable():
    data = list(range(5))
    assert chunked(data, size=2) == [[0, 1], [2, 3], [4]]


@pytest.mark.asyncio
async def test_run_with_limited_concurrency_preserves_results():
    calls: list[int] = []

    async def worker(batch):
        await asyncio.sleep(0.01)
        calls.append(len(list(batch)))
        return len(calls)

    batches = chunked(range(6), size=2)
    res = await run_with_limited_concurrency(batches, concurrency=2, worker=worker)

    assert len(res) == 3
    assert sorted(calls) == [2, 2, 2]
