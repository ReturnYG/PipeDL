from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 48127
DEFAULT_PROFILE = "default"


@dataclass(frozen=True)
class AppPaths:
    root: Path
    state_dir: Path
    db_path: Path
    runs_dir: Path


def get_paths() -> AppPaths:
    root = Path(os.environ.get("PIPEDL_ROOT", default_root_dir(get_profile()))).resolve()
    state_dir = Path(os.environ.get("PIPEDL_STATE_DIR", root / ".pipedl")).resolve()
    runs_dir = Path(os.environ.get("PIPEDL_RUNS_DIR", root / "runs")).resolve()
    return AppPaths(
        root=root,
        state_dir=state_dir,
        db_path=state_dir / "pipedl.db",
        runs_dir=runs_dir,
    )


def ensure_paths(paths: AppPaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)


def get_profile() -> str:
    profile = (os.environ.get("PIPEDL_PROFILE") or DEFAULT_PROFILE).strip()
    return profile or DEFAULT_PROFILE


def get_host() -> str:
    return (os.environ.get("PIPEDL_HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST


def get_port() -> int:
    value = (os.environ.get("PIPEDL_PORT") or "").strip()
    if not value:
        return DEFAULT_PORT
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError(f"PIPEDL_PORT must be an integer, got {value!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"PIPEDL_PORT must be between 1 and 65535, got {port}")
    return port


def default_root_dir(profile: str | None = None) -> Path:
    profile = (profile or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    suffix = "" if profile == DEFAULT_PROFILE else f"-{profile}"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / f"PipeDL{suffix}"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / f"pipedl{suffix}"
    return Path.home() / ".local" / "share" / f"pipedl{suffix}"
