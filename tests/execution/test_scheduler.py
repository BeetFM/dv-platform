import os
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.execution.scheduler import ResourceLimits, ResourceRequest, admitted_workers, run_ordered
from dv_platform.infrastructure.locking import DirectoryLock


class ResourceSchedulerTests(unittest.TestCase):
    def test_admission_obeys_every_limit(self) -> None:
        limits = ResourceLimits(modules=8, processes=6, memory_mb=1000, license_tokens=3)
        request = ResourceRequest(processes=2, memory_mb=400, license_tokens=1)
        self.assertEqual(admitted_workers(limits, request, 20), 2)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            run_ordered(("task",), lambda value: value, limits=limits, request=ResourceRequest(memory_mb=2000))

    def test_results_remain_in_input_order_without_oversubscription(self) -> None:
        lock = threading.Lock()
        active = 0
        peak = 0

        def worker(value: int) -> int:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01 * (4 - value))
            with lock:
                active -= 1
            return value * 2

        results = run_ordered(
            (1, 2, 3),
            worker,
            limits=ResourceLimits(3, 2, 1024, 2),
            request=ResourceRequest(1, 128, 1),
        )
        self.assertEqual(results, (2, 4, 6))
        self.assertLessEqual(peak, 2)

    def test_worker_crash_cancels_queued_tasks(self) -> None:
        started: list[int] = []

        def worker(value: int) -> int:
            started.append(value)
            if value == 1:
                raise RuntimeError("worker crash")
            time.sleep(0.05)
            return value

        with self.assertRaisesRegex(RuntimeError, "worker crash"):
            run_ordered(
                range(10),
                worker,
                limits=ResourceLimits(2, 2, 1024, 2),
                request=ResourceRequest(1, 128, 1),
            )
        self.assertLessEqual(len(started), 2)

    def test_pre_cancelled_wave_starts_no_tasks(self) -> None:
        cancellation = threading.Event()
        cancellation.set()
        started: list[int] = []
        with self.assertRaisesRegex(InterruptedError, "cancelled"):
            run_ordered(
                range(3),
                lambda value: started.append(value) or value,
                limits=ResourceLimits(2, 2, 1024, 2),
                request=ResourceRequest(1, 128, 1),
                cancel_event=cancellation,
            )
        self.assertEqual(started, [])

    def test_stale_publication_lock_is_recovered(self) -> None:
        with TemporaryDirectory() as directory:
            lock_path = Path(directory) / ".aggregate.lock"
            lock_path.mkdir()
            (lock_path / "owner.json").write_text("invalid", encoding="utf-8")
            old = time.time() - 10
            os.utime(lock_path, (old, old))
            with DirectoryLock(lock_path, timeout_seconds=0.2, stale_seconds=0.01):
                self.assertTrue(lock_path.is_dir())
            self.assertFalse(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
