"""Deterministic resource-aware admission for bounded local task waves."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Generic, TypeVar

TaskT = TypeVar("TaskT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class ResourceLimits:
    modules: int
    processes: int
    memory_mb: int
    license_tokens: int

    def validate(self) -> None:
        if min(self.modules, self.processes, self.memory_mb, self.license_tokens) < 1:
            raise ValueError("scheduler resource limits must be positive")


@dataclass(frozen=True)
class ResourceRequest:
    processes: int = 1
    memory_mb: int = 1
    license_tokens: int = 1

    def validate(self) -> None:
        if min(self.processes, self.memory_mb, self.license_tokens) < 1:
            raise ValueError("scheduler resource requests must be positive")


@dataclass(frozen=True)
class ScheduledResult(Generic[ResultT]):
    index: int
    value: ResultT


def admitted_workers(limits: ResourceLimits, request: ResourceRequest, task_count: int) -> int:
    """Return the exact safe concurrency bound for one homogeneous wave."""

    limits.validate()
    request.validate()
    if task_count < 1:
        return 0
    return min(
        task_count,
        limits.modules,
        limits.processes // request.processes,
        limits.memory_mb // request.memory_mb,
        limits.license_tokens // request.license_tokens,
    )


def run_ordered(  # noqa: C901
    tasks: Iterable[TaskT],
    worker: Callable[[TaskT], ResultT],
    *,
    limits: ResourceLimits,
    request: ResourceRequest,
    cancel_event: threading.Event | None = None,
) -> tuple[ResultT, ...]:
    """Run admitted tasks with deterministic results and fail-fast cleanup."""

    queued = tuple(tasks)
    if not queued:
        return ()
    cancellation = cancel_event or threading.Event()
    workers = admitted_workers(limits, request, len(queued))
    if workers < 1:
        raise ValueError("task resource request exceeds scheduler limits")
    results: list[ResultT | None] = [None] * len(queued)
    next_index = 0
    futures: dict[Future[ResultT], int] = {}
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dv-platform")
    try:
        while next_index < len(queued) and len(futures) < workers:
            futures[executor.submit(_run_unless_cancelled, cancellation, worker, queued[next_index])] = next_index
            next_index += 1
        while futures:
            if cancellation.is_set():
                raise InterruptedError("scheduled task wave cancelled")
            completed, _pending = wait(tuple(futures), timeout=0.05, return_when=FIRST_COMPLETED)
            if not completed:
                continue
            failed = next((future for future in completed if future.exception() is not None), None)
            if failed is not None:
                failed.result()
            for future in sorted(completed, key=lambda item: futures[item]):
                index = futures.pop(future)
                results[index] = future.result()
                if next_index < len(queued) and not cancellation.is_set():
                    futures[executor.submit(_run_unless_cancelled, cancellation, worker, queued[next_index])] = (
                        next_index
                    )
                    next_index += 1
    except BaseException:
        cancellation.set()
        for future in futures:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    if any(item is None for item in results):
        raise RuntimeError("scheduler completed without every ordered result")
    return tuple(item for item in results if item is not None)


def _run_unless_cancelled(
    cancellation: threading.Event,
    worker: Callable[[TaskT], ResultT],
    task: TaskT,
) -> ResultT:
    if cancellation.is_set():
        raise InterruptedError("scheduled task cancelled before admission")
    return worker(task)
