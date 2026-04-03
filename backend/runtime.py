from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, TypeVar
from weakref import WeakKeyDictionary

T = TypeVar("T")


class BlockingTaskRunner:
    """Bound blocking work before it reaches the shared thread pool."""

    def __init__(
        self,
        *,
        max_workers: int,
        max_in_flight_calls: int | None = None,
        thread_name_prefix: str = "",
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._max_in_flight_calls = max(1, max_in_flight_calls or max_workers)
        self._semaphores: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
            WeakKeyDictionary()
        )

    def _semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        semaphore = self._semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self._max_in_flight_calls)
            self._semaphores[loop] = semaphore
        return semaphore

    async def run(self, func: Callable[[], T], *, timeout_seconds: float) -> T:
        semaphore = self._semaphore()
        future: Future[T] | None = None

        async def _submit_and_wait() -> T:
            nonlocal future
            await semaphore.acquire()
            try:
                future = self._executor.submit(func)
            except BaseException:
                semaphore.release()
                raise
            future.add_done_callback(lambda _: semaphore.release())
            return await asyncio.wrap_future(future)

        try:
            return await asyncio.wait_for(_submit_and_wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            if future is not None:
                future.cancel()
            raise

    def shutdown(self, *, wait: bool = False, cancel_futures: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
