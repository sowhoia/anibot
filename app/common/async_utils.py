import asyncio
from collections.abc import Iterable
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def chunked(iterable: Iterable[T], size: int) -> list[list[T]]:
    """
    Быстро режет итератор на чанки фиксированного размера.
    Не использует генераторы, чтобы не плодить лишних await в вызывающем коде.
    """
    batch: list[T] = []
    out: list[list[T]] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            out.append(batch)
            batch = []
    if batch:
        out.append(batch)
    return out


async def run_with_limited_concurrency(
    batches: Iterable[Iterable[T]],
    concurrency: int,
    worker: Callable[[Iterable[T]], Awaitable[R]],
) -> list[R]:
    """
    Параллельно обрабатывает батчи с ограничением по concurrency.
    Возвращает список результатов worker, сохраняя порядок батчей.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _run(batch: Iterable[T]) -> R:
        async with sem:
            return await worker(batch)

    tasks = [asyncio.create_task(_run(batch)) for batch in batches]
    if not tasks:
        return []
    return await asyncio.gather(*tasks)

