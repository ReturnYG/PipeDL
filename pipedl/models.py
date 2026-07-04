from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any


STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_STOPPING = "stopping"
STATUS_STOPPED = "stopped"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = {
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_STOPPED,
    STATUS_CANCELLED,
}

SHELL_BASH = "bash"
SHELL_WSL = "wsl"
SHELL_POWERSHELL = "powershell"
SHELL_CMD = "cmd"
SUPPORTED_SHELLS = {SHELL_BASH, SHELL_WSL, SHELL_POWERSHELL, SHELL_CMD}


@dataclass(frozen=True)
class ExperimentCreate:
    name: str
    command: str
    shell: str = SHELL_BASH
    cwd: str = "."
    created_by: str = "cli"
    tags: str = ""
    notes: str = ""


def now_sql() -> str:
    return "datetime('now')"


def command_from_args(args: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in args)


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
