"""Task scheduler — async job execution engine.

─────────────────────────────────────────────────────────
MODULES
─────────────────────────────────────────────────────────
_primitives.py  Low-level asyncio queue + named task registry
_scheduler.py   JobsScheduler with trampoline loops
hooks.py        FastAPI lifespan (startup / shutdown)


─────────────────────────────────────────────────────────
STARTUP
─────────────────────────────────────────────────────────
lifespan_event (hooks.py) runs on app boot:

    healthcheck ──> bootstrap() ──> create worker task
          ┌─────────────┴─────────────┐
    kernel jobs (no DB)        user jobs (DB-backed)
    fixed interval, never      poll due rows, pause
    stops                      on error, stop when
                               no active jobs remain

─────────────────────────────────────────────────────────
LOOP PROCESSING
─────────────────────────────────────────────────────────
Two independent execution paths run concurrently:

  ┌─────────────────────────────────────────────────┐
  |              NAMED TASKS (_tasks dict)          |
  |                                                 |
  |  run_task(key, coro)                            |
  |       |                                         |
  |       v                                         |
  |  asyncio.create_task ──> _tasks["key"] = task   |
  |       |                                         |
  |       v                                         |
  |  ┌── trampoline loop ──────────────────────┐    |
  |  |                                         |    |
  |  |  kernel:  handler() -> sleep(interval)  |    |
  |  |           repeat forever                |    |
  |  |                                         |    |
  |  |  db-backed:                             |    |
  |  |    poll active jobs -> filter due       |    |
  |  |    -> _execute_batch() -> sleep         |    |
  |  |    stop when no active jobs remain      |    |
  |  |    pause job on error (is_active=False) |    |
  |  └─────────────────────────────────────────┘    |
  └─────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────┐
  |              QUEUE + WORKER                     |
  |                                                 |
  |  submit(name, handler)                          |
  |       |                                         |
  |       v                                         |
  |  _queue.put_nowait(QueueTask)                   |
  |       |                                         |
  |       v                                         |
  |  worker() loop (single consumer):               |
  |    await _queue.get()                           |
  |    await task.handler()   <-- sequential        |
  |    _queue.task_done()                           |
  |                                                 |
  |  Used for: one-shot tasks (manual job runs,     |
  |            article extension inference)         |
  └─────────────────────────────────────────────────┘


─────────────────────────────────────────────────────────
SHUTDOWN
─────────────────────────────────────────────────────────
  primitives.shutdown()  cancel all named tasks
  worker_task.cancel()   stop the queue consumer
"""

__all__ = (
    "JobType",
    "all_job_types",
    "get_job_type",
    "jobs_scheduler",
    "lifespan_event",
    "submit",
)

from src.domain.jobs.registry import JobType, all_job_types, get_job_type

from ._primitives import submit
from ._scheduler import jobs_scheduler
from .hooks import lifespan_event
