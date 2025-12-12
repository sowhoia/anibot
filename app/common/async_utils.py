"""
Асинхронные утилиты.

Функции для работы с concurrency, батчами и асинхронными операциями.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, TypeVar

from loguru import logger

T = TypeVar("T")
R = TypeVar("R")


def chunked(iterable: Iterable[T], size: int) -> list[list[T]]:
    """
    Разбивает итерируемый объект на чанки фиксированного размера.

    Args:
        iterable: Исходный итерируемый объект
        size: Размер чанка

    Returns:
        Список чанков

    Examples:
        >>> chunked([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
    """
    if size <= 0:
        raise ValueError("Chunk size must be positive")

    batch: list[T] = []
    result: list[list[T]] = []

    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            result.append(batch)
            batch = []

    if batch:
        result.append(batch)

    return result


def chunked_iter(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    """
    Генератор чанков (lazy версия chunked).

    Args:
        iterable: Исходный итерируемый объект
        size: Размер чанка

    Yields:
        Чанки указанного размера
    """
    if size <= 0:
        raise ValueError("Chunk size must be positive")

    batch: list[T] = []

    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []

    if batch:
        yield batch


@dataclass
class TaskResult(Exception):
    """Результат выполнения задачи."""

    value: Any = None
    error: Exception | None = None
    index: int = 0

    @property
    def success(self) -> bool:
        return self.error is None


async def run_with_limited_concurrency(
    batches: Iterable[Iterable[T]],
    concurrency: int,
    worker: Callable[[Iterable[T]], Awaitable[R]],
    on_error: Callable[[Exception, int], None] | None = None,
    return_exceptions: bool = False,
) -> list[R | TaskResult]:
    """
    Параллельно обрабатывает батчи с ограничением concurrency.

    Args:
        batches: Итерируемый объект батчей
        concurrency: Максимальное количество параллельных задач
        worker: Асинхронная функция-обработчик
        on_error: Callback для обработки ошибок (exc, batch_index)
        return_exceptions: Возвращать ошибки вместо выброса

    Returns:
        Список результатов в порядке батчей

    Examples:
        >>> async def process(batch):
        ...     return sum(batch)
        >>> results = await run_with_limited_concurrency(
        ...     [[1, 2], [3, 4]],
        ...     concurrency=2,
        ...     worker=process,
        ... )
        >>> results
        [3, 7]
    """
    if concurrency <= 0:
        raise ValueError("Concurrency must be positive")

    sem = asyncio.Semaphore(concurrency)
    batch_list = list(batches)

    async def _run(batch: Iterable[T], index: int) -> R | TaskResult:
        async with sem:
            try:
                return await worker(batch)
            except Exception as exc:
                if on_error:
                    on_error(exc, index)
                if return_exceptions:
                    return TaskResult(error=exc, index=index)
                raise

    tasks = [
        asyncio.create_task(_run(batch, i))
        for i, batch in enumerate(batch_list)
    ]

    if not tasks:
        return []

    if return_exceptions:
        return list(await asyncio.gather(*tasks, return_exceptions=True))
    return list(await asyncio.gather(*tasks))


async def run_tasks_with_timeout(
    tasks: list[Awaitable[T]],
    timeout: float,
    return_exceptions: bool = False,
) -> list[T | Exception | None]:
    """
    Выполняет задачи с общим таймаутом.

    Args:
        tasks: Список корутин
        timeout: Таймаут в секундах
        return_exceptions: Возвращать ошибки вместо выброса

    Returns:
        Список результатов (или None для незавершенных задач)
    """
    async_tasks = [asyncio.create_task(t) for t in tasks]

    try:
        done, pending = await asyncio.wait(
            async_tasks,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED,
        )
    except asyncio.CancelledError:
        for task in async_tasks:
            task.cancel()
        raise

    # Отменяем незавершенные задачи
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    results: list[T | Exception | None] = []
    for task in async_tasks:
        if task in done:
            try:
                results.append(task.result())
            except Exception as exc:
                if return_exceptions:
                    results.append(exc)
                else:
                    raise
        else:
            results.append(None)

    return results


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    **kwargs,
) -> T:
    """
    Выполняет асинхронную функцию с retry и exponential backoff.

    Args:
        func: Асинхронная функция
        *args: Позиционные аргументы функции
        max_retries: Максимальное количество попыток
        delay: Начальная задержка между попытками (секунды)
        backoff: Множитель для увеличения задержки
        max_delay: Максимальная задержка между попытками
        exceptions: Tuple исключений для retry
        **kwargs: Именованные аргументы функции

    Returns:
        Результат функции

    Raises:
        Exception: Последнее исключение после всех попыток
    """
    last_error: Exception | None = None
    current_delay = delay

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as exc:
            last_error = exc

            if attempt < max_retries:
                logger.warning(
                    "Attempt {}/{} failed: {}. Retrying in {:.1f}s",
                    attempt,
                    max_retries,
                    exc,
                    current_delay,
                )
                await asyncio.sleep(current_delay)
                current_delay = min(current_delay * backoff, max_delay)
            else:
                logger.error(
                    "All {} attempts failed. Last error: {}",
                    max_retries,
                    exc,
                )

    raise last_error  # type: ignore


class AsyncBatcher:
    """
    Батчер для группировки асинхронных операций.

    Собирает элементы и выполняет batch-обработку при достижении
    размера батча или таймаута.

    Examples:
        >>> async def process_batch(items):
        ...     print(f"Processing {len(items)} items")
        >>> batcher = AsyncBatcher(process_batch, batch_size=10, timeout=5.0)
        >>> await batcher.add("item1")
        >>> await batcher.add("item2")
        >>> await batcher.flush()
    """

    def __init__(
        self,
        processor: Callable[[list[T]], Awaitable[None]],
        batch_size: int = 100,
        timeout: float = 5.0,
    ) -> None:
        """
        Args:
            processor: Функция обработки батча
            batch_size: Максимальный размер батча
            timeout: Таймаут для автоматического flush (секунды)
        """
        self._processor = processor
        self._batch_size = batch_size
        self._timeout = timeout
        self._items: list[T] = []
        self._lock = asyncio.Lock()
        self._timer_task: asyncio.Task | None = None

    async def add(self, item: T) -> None:
        """Добавляет элемент в батч."""
        async with self._lock:
            self._items.append(item)

            if len(self._items) >= self._batch_size:
                await self._flush_internal()
            elif self._timer_task is None:
                self._timer_task = asyncio.create_task(self._timer())

    async def flush(self) -> None:
        """Принудительно обрабатывает накопленные элементы."""
        async with self._lock:
            await self._flush_internal()

    async def _flush_internal(self) -> None:
        """Внутренний метод flush без блокировки."""
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

        if self._items:
            items = self._items
            self._items = []
            await self._processor(items)

    async def _timer(self) -> None:
        """Таймер для автоматического flush."""
        try:
            await asyncio.sleep(self._timeout)
            async with self._lock:
                await self._flush_internal()
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        """Завершает работу батчера."""
        await self.flush()
        if self._timer_task:
            self._timer_task.cancel()


async def gather_with_semaphore(
    *coros: Awaitable[T],
    limit: int = 10,
) -> list[T]:
    """
    Выполняет корутины с ограничением параллельности.

    Args:
        *coros: Корутины для выполнения
        limit: Максимальное количество параллельных задач

    Returns:
        Список результатов
    """
    sem = asyncio.Semaphore(limit)

    async def _limited(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    return await asyncio.gather(*(_limited(c) for c in coros))
