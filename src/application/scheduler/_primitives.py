"""Generic asyncio task scheduler.

Two mechanisms:
- Queue + worker: one-shot tasks processed sequentially
- Named tasks: long-running asyncio tasks, cancellable by key
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass

from loguru import logger

_queue: asyncio.Queue["QueueTask"] = asyncio.Queue()
_tasks: dict[str, asyncio.Task] = {}


@dataclass(frozen=True)
class QueueTask:
    name: str
    handler: Callable[[], Awaitable[None]]


def submit(name: str, handler: Callable[[], Awaitable[None]]) -> None:
    """Enqueue a one-shot task for immediate execution."""

    _queue.put_nowait(QueueTask(name=name, handler=handler))
    logger.debug(f"Task queued: {name}")


def run_task(key: str, coroutine: Coroutine) -> None:
    """Start a named asyncio task.

    Cancels any existing task with the same key first.
    The task is automatically removed from the registry
    when it completes.
    """

    cancel_task(key)

    task = asyncio.create_task(coroutine)
    _tasks[key] = task
    task.add_done_callback(lambda _: _tasks.pop(key, None))


def cancel_task(key: str) -> None:
    """Cancel a named task by key."""

    existing = _tasks.pop(key, None)
    if existing is not None:
        existing.cancel()
        logger.debug(f"Task cancelled: {key}")


def shutdown() -> None:
    """Cancel all named tasks. Call on application shutdown."""

    for key in list(_tasks):
        cancel_task(key)


async def worker() -> None:
    """Process one-shot tasks from the queue."""

    while True:
        task = await _queue.get()
        try:
            await task.handler()
        except Exception as e:
            logger.error(f"Task '{task.name}' failed: {e}")
        finally:
            _queue.task_done()
