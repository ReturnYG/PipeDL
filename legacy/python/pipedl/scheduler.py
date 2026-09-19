from __future__ import annotations

import threading
import time

from .models import STATUS_FAILED, STATUS_PAUSED, STATUS_RUNNING, STATUS_STOPPED, STATUS_SUCCEEDED, STATUS_STOPPING
from .process_manager import ManagedProcess, resume_process, start_process, stop_process, suspend_process
from .storage import Storage


class Scheduler:
    def __init__(self, storage: Storage, poll_interval: float = 1.0):
        self.storage = storage
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: ManagedProcess | None = None
        self._current_id: str | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pipedl-scheduler", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def stop_current(self) -> bool:
        with self._lock:
            running = self.storage.get_running()
            if not running:
                return False
            self.storage.set_status(running["id"], STATUS_STOPPING)
            stop_process(running["pid"], running["process_group"])
            return True

    def pause_current(self) -> bool:
        with self._lock:
            running = self.storage.get_running()
            if not running or running["status"] != STATUS_RUNNING:
                return False
            suspend_process(running["pid"], running["process_group"])
            self.storage.set_status(running["id"], STATUS_PAUSED)
            return True

    def resume_current(self) -> bool:
        with self._lock:
            running = self.storage.get_running()
            if not running or running["status"] != STATUS_PAUSED:
                return False
            resume_process(running["pid"], running["process_group"])
            self.storage.set_status(running["id"], STATUS_RUNNING)
            return True

    def delete_experiment(self, exp_id: str) -> bool:
        with self._lock:
            exp = self.storage.get_experiment(exp_id)
            if not exp:
                return False
            if exp["status"] in {STATUS_RUNNING, STATUS_PAUSED, STATUS_STOPPING}:
                self.storage.set_status(exp_id, STATUS_STOPPING)
                stop_process(exp["pid"], exp["process_group"])
                if self._current_id == exp_id and self._current is not None:
                    try:
                        self._current.popen.wait(timeout=1)
                    except Exception:
                        pass
                    self._current = None
                    self._current_id = None
            return self.storage.delete_experiment(exp_id)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                print(f"[PipeDL scheduler] {exc}", flush=True)
            self._stop.wait(self.poll_interval)

    def _tick(self) -> None:
        with self._lock:
            if self._current is not None and self._current_id is not None:
                return_code = self._current.popen.poll()
                if return_code is None:
                    return
                exp = self.storage.get_experiment(self._current_id)
                final_status = STATUS_SUCCEEDED if return_code == 0 else STATUS_FAILED
                if exp and exp["status"] == STATUS_STOPPING:
                    final_status = STATUS_STOPPED
                self.storage.mark_finished(self._current_id, final_status, return_code)
                self._current = None
                self._current_id = None

            if self.storage.queue_paused():
                return
            if self.storage.get_running():
                return

            next_exp = self.storage.next_queued()
            if not next_exp:
                return

            try:
                managed = start_process(next_exp)
            except Exception as exc:
                self.storage.mark_finished(next_exp["id"], STATUS_FAILED, -1)
                stderr_path = next_exp.get("stderr_path")
                if stderr_path:
                    with open(stderr_path, "a", encoding="utf-8") as fh:
                        fh.write(f"PipeDL failed to start process: {exc}\n")
                return

            self._current = managed
            self._current_id = next_exp["id"]
            self.storage.mark_running(next_exp["id"], managed.popen.pid, managed.process_group)
