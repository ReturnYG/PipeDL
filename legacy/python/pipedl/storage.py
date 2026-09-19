from __future__ import annotations

import sqlite3
import shutil
import uuid
from pathlib import Path
from typing import Any

from .config import AppPaths, ensure_paths
from .models import (
    ExperimentCreate,
    STATUS_CANCELLED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    TERMINAL_STATUSES,
    row_to_dict,
)


class Storage:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        ensure_paths(paths)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.paths.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    shell TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    status TEXT NOT NULL,
                    queue_position INTEGER NOT NULL,
                    pid INTEGER,
                    process_group INTEGER,
                    exit_code INTEGER,
                    created_by TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    stdout_path TEXT,
                    stderr_path TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    ended_at TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS queue_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    paused INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                INSERT OR IGNORE INTO queue_state (id, paused) VALUES (1, 0);
                """
            )

    def add_experiment(self, data: ExperimentCreate) -> dict[str, Any]:
        exp_id = uuid.uuid4().hex[:12]
        run_dir = self.paths.runs_dir / exp_id
        run_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = str(run_dir / "stdout.log")
        stderr_path = str(run_dir / "stderr.log")
        with self.connect() as conn:
            name = data.name.strip() or self._next_default_name(conn)
            row = conn.execute(
                "SELECT COALESCE(MAX(queue_position), 0) + 1 AS pos FROM experiments WHERE status = ?",
                (STATUS_QUEUED,),
            ).fetchone()
            position = int(row["pos"])
            conn.execute(
                """
                INSERT INTO experiments (
                    id, name, command, shell, cwd, status, queue_position,
                    created_by, tags, notes, stdout_path, stderr_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exp_id,
                    name,
                    data.command,
                    data.shell,
                    data.cwd,
                    STATUS_QUEUED,
                    position,
                    data.created_by,
                    data.tags,
                    data.notes,
                    stdout_path,
                    stderr_path,
                ),
            )
        return self.get_experiment(exp_id)

    def _next_default_name(self, conn: sqlite3.Connection) -> str:
        rows = conn.execute("SELECT name FROM experiments WHERE name LIKE 'Exp.%'").fetchall()
        max_index = 0
        for row in rows:
            value = str(row["name"])
            try:
                max_index = max(max_index, int(value.split(".", 1)[1]))
            except (IndexError, ValueError):
                continue
        return f"Exp.{max_index + 1:02d}"

    def get_experiment(self, exp_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM experiments WHERE id = ?", (exp_id,)).fetchone()
            return row_to_dict(row) if row else None

    def list_experiments(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM experiments
                ORDER BY
                    CASE status
                        WHEN 'running' THEN 0
                        WHEN 'paused' THEN 0
                        WHEN 'queued' THEN 1
                        ELSE 2
                    END,
                    queue_position ASC,
                    created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [row_to_dict(row) for row in rows]

    def get_running(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM experiments
                WHERE status IN (?, ?)
                ORDER BY started_at ASC
                LIMIT 1
                """,
                (STATUS_RUNNING, STATUS_PAUSED),
            ).fetchone()
            return row_to_dict(row) if row else None

    def next_queued(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM experiments
                WHERE status = ?
                ORDER BY queue_position ASC, created_at ASC
                LIMIT 1
                """,
                (STATUS_QUEUED,),
            ).fetchone()
            return row_to_dict(row) if row else None

    def mark_running(self, exp_id: str, pid: int, process_group: int | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE experiments
                SET status = ?, pid = ?, process_group = ?, started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (STATUS_RUNNING, pid, process_group, exp_id),
            )

    def mark_finished(self, exp_id: str, status: str, exit_code: int | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE experiments
                SET status = ?, exit_code = ?, ended_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, exit_code, exp_id),
            )

    def set_status(self, exp_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE experiments SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, exp_id),
            )

    def cancel_queued(self, exp_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE experiments
                SET status = ?, ended_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = ?
                """,
                (STATUS_CANCELLED, exp_id, STATUS_QUEUED),
            )
            return cur.rowcount > 0

    def delete_experiment(self, exp_id: str, delete_logs: bool = True) -> bool:
        exp = self.get_experiment(exp_id)
        if not exp:
            return False
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM experiments WHERE id = ?", (exp_id,))
        self.compact_queue()
        if delete_logs:
            self._delete_run_dir(exp)
        return cur.rowcount > 0

    def retry_experiment(self, exp_id: str) -> dict[str, Any] | None:
        exp = self.get_experiment(exp_id)
        if not exp or exp["status"] not in TERMINAL_STATUSES:
            return None
        retry_name = exp["name"] if exp["name"].endswith(" retry") else f"{exp['name']} retry"
        return self.add_experiment(
            ExperimentCreate(
                name=retry_name,
                command=exp["command"],
                shell=exp["shell"],
                cwd=exp["cwd"],
                created_by=f"retry:{exp['id']}",
                tags=exp["tags"],
                notes=exp["notes"],
            )
        )

    def move_queued(self, exp_id: str, position: int) -> None:
        queued = [exp for exp in self.list_experiments() if exp["status"] == STATUS_QUEUED]
        ids = [exp["id"] for exp in queued if exp["id"] != exp_id]
        index = max(0, min(position - 1, len(ids)))
        ids.insert(index, exp_id)
        with self.connect() as conn:
            for idx, item_id in enumerate(ids, start=1):
                conn.execute(
                    """
                    UPDATE experiments
                    SET queue_position = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = ?
                    """,
                    (idx, item_id, STATUS_QUEUED),
                )

    def compact_queue(self) -> None:
        queued = [exp for exp in self.list_experiments() if exp["status"] == STATUS_QUEUED]
        with self.connect() as conn:
            for idx, exp in enumerate(queued, start=1):
                conn.execute(
                    """
                    UPDATE experiments
                    SET queue_position = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = ?
                    """,
                    (idx, exp["id"], STATUS_QUEUED),
                )

    def queue_paused(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT paused FROM queue_state WHERE id = 1").fetchone()
            return bool(row["paused"])

    def set_queue_paused(self, paused: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE queue_state SET paused = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (1 if paused else 0,),
            )

    def summary(self) -> dict[str, int | bool]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM experiments GROUP BY status"
            ).fetchall()
            counts = {row["status"]: int(row["count"]) for row in rows}
        return {
            "running": counts.get("running", 0),
            "paused_processes": counts.get("paused", 0),
            "queued": counts.get("queued", 0),
            "succeeded": counts.get("succeeded", 0),
            "failed": counts.get("failed", 0),
            "stopped": counts.get("stopped", 0),
            "cancelled": counts.get("cancelled", 0),
            "paused": self.queue_paused(),
        }

    def _delete_run_dir(self, exp: dict[str, Any]) -> None:
        stdout_path = exp.get("stdout_path")
        if not stdout_path:
            return
        run_dir = Path(stdout_path).parent.resolve()
        runs_root = self.paths.runs_dir.resolve()
        if run_dir == runs_root or runs_root not in run_dir.parents:
            return
        shutil.rmtree(run_dir, ignore_errors=True)


def read_tail(path: str | Path | None, max_bytes: int = 65536) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    size = file_path.stat().st_size
    with file_path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(-max_bytes, 2)
        return fh.read().decode(errors="replace")
