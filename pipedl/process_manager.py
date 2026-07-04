from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import SHELL_BASH, SHELL_CMD, SHELL_POWERSHELL, SHELL_WSL


@dataclass
class ManagedProcess:
    popen: subprocess.Popen[bytes]
    process_group: int | None


def hidden_windows_subprocess_kwargs(new_process_group: bool = False) -> dict:
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    creationflags = subprocess.CREATE_NO_WINDOW
    if new_process_group:
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
    return {"creationflags": creationflags, "startupinfo": startupinfo}


def build_command(shell: str, command: str) -> list[str]:
    if shell == SHELL_BASH:
        return ["bash", "-lc", command]
    if shell == SHELL_WSL:
        return ["wsl.exe", "--", "bash", "-lc", command]
    if shell == SHELL_POWERSHELL:
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    if shell == SHELL_CMD:
        return ["cmd.exe", "/C", command]
    raise ValueError(f"Unsupported shell: {shell}")


def start_process(exp: dict) -> ManagedProcess:
    stdout_path = Path(exp["stdout_path"])
    stderr_path = Path(exp["stderr_path"])
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = exp["cwd"] or "."
    cmd = build_command(exp["shell"], exp["command"])

    stdout = stdout_path.open("ab", buffering=0)
    stderr = stderr_path.open("ab", buffering=0)

    kwargs: dict = {
        "cwd": cwd,
        "stdout": stdout,
        "stderr": stderr,
        "stdin": subprocess.DEVNULL,
    }
    process_group: int | None = None
    if os.name == "nt":
        kwargs.update(hidden_windows_subprocess_kwargs(new_process_group=True))
    else:
        kwargs["start_new_session"] = True

    popen = subprocess.Popen(cmd, **kwargs)
    if os.name != "nt":
        process_group = os.getpgid(popen.pid)
    return ManagedProcess(popen=popen, process_group=process_group)


def stop_process(pid: int | None, process_group: int | None = None, timeout: float = 8.0) -> None:
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **hidden_windows_subprocess_kwargs(),
        )
        return

    target_group = process_group
    if target_group is None:
        try:
            target_group = os.getpgid(pid)
        except ProcessLookupError:
            return

    try:
        os.killpg(target_group, signal.SIGTERM)
    except ProcessLookupError:
        return

    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.killpg(target_group, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)

    try:
        os.killpg(target_group, signal.SIGKILL)
    except ProcessLookupError:
        return


def suspend_process(pid: int | None, process_group: int | None = None) -> None:
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"Suspend-Process -Id {int(pid)}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **hidden_windows_subprocess_kwargs(),
        )
        return

    target_group = process_group
    if target_group is None:
        try:
            target_group = os.getpgid(pid)
        except ProcessLookupError:
            return
    try:
        os.killpg(target_group, signal.SIGSTOP)
    except ProcessLookupError:
        return


def resume_process(pid: int | None, process_group: int | None = None) -> None:
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"Resume-Process -Id {int(pid)}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **hidden_windows_subprocess_kwargs(),
        )
        return

    target_group = process_group
    if target_group is None:
        try:
            target_group = os.getpgid(pid)
        except ProcessLookupError:
            return
    try:
        os.killpg(target_group, signal.SIGCONT)
    except ProcessLookupError:
        return


def current_platform_hint() -> str:
    if os.name == "nt":
        return "windows"
    if "microsoft" in Path("/proc/version").read_text(errors="ignore").lower() if Path("/proc/version").exists() else False:
        return "wsl"
    return sys.platform
