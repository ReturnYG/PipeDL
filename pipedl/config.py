from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 48127


@dataclass(frozen=True)
class AppPaths:
    root: Path
    state_dir: Path
    db_path: Path
    runs_dir: Path


def get_paths() -> AppPaths:
    root = Path(os.environ.get("PIPEDL_ROOT", default_root_dir())).resolve()
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


def default_root_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "PipeDL"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "pipedl"
    return Path.home() / ".local" / "share" / "pipedl"
