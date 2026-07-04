from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__


GITHUB_OWNER = "ReturnYG"
GITHUB_REPO = "PipeDL"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
INSTALLER_PREFIX = "PipeDL-Setup-"
INSTALLER_SUFFIX = ".exe"
USER_AGENT = f"PipeDL/{__version__}"


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    release_url: str
    asset_name: str
    download_url: str
    body: str = ""


def should_check_for_updates() -> bool:
    if os.environ.get("PIPEDL_DISABLE_UPDATE_CHECK") == "1":
        return False
    if sys.platform != "win32":
        return False
    if getattr(sys, "frozen", False):
        return True
    return os.environ.get("PIPEDL_ALLOW_SOURCE_UPDATE_CHECK") == "1"


def parse_version(value: str) -> tuple[int, ...]:
    cleaned = (value or "").strip().lstrip("vV")
    cleaned = cleaned.split("-", 1)[0]
    parts = re.findall(r"\d+", cleaned)
    return tuple(int(part) for part in parts)


def is_newer_version(latest: str, current: str) -> bool:
    latest_parts = parse_version(latest)
    current_parts = parse_version(current)
    if not latest_parts:
        return False
    length = max(len(latest_parts), len(current_parts))
    latest_padded = latest_parts + (0,) * (length - len(latest_parts))
    current_padded = current_parts + (0,) * (length - len(current_parts))
    return latest_padded > current_padded


def fetch_latest_release(timeout: int = 8) -> dict | None:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 400:
            return None
        return json.loads(response.read().decode("utf-8"))


def find_windows_installer_asset(release: dict) -> dict | None:
    assets = release.get("assets") or []
    installer_assets = [
        asset
        for asset in assets
        if (asset.get("name") or "").startswith(INSTALLER_PREFIX)
        and (asset.get("name") or "").endswith(INSTALLER_SUFFIX)
        and asset.get("browser_download_url")
    ]
    if not installer_assets:
        return None
    return sorted(installer_assets, key=lambda item: item.get("name") or "")[-1]


def check_for_update(current_version: str = __version__) -> UpdateInfo | None:
    if not should_check_for_updates():
        return None
    release = fetch_latest_release()
    if not release or release.get("draft") or release.get("prerelease"):
        return None
    latest_version = release.get("tag_name") or release.get("name") or ""
    if not is_newer_version(latest_version, current_version):
        return None
    asset = find_windows_installer_asset(release)
    if not asset:
        return None
    return UpdateInfo(
        version=latest_version.lstrip("vV"),
        release_url=release.get("html_url") or "",
        asset_name=asset.get("name") or "PipeDL-Setup.exe",
        download_url=asset.get("browser_download_url"),
        body=release.get("body") or "",
    )


def download_update(
    info: UpdateInfo,
    progress_callback: Callable[[int, int], None] | None = None,
    timeout: int = 30,
) -> Path:
    update_dir = Path(tempfile.gettempdir()) / "PipeDL-updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    installer_path = update_dir / info.asset_name
    partial_path = installer_path.with_suffix(installer_path.suffix + ".download")
    if partial_path.exists():
        partial_path.unlink()

    request = urllib.request.Request(
        info.download_url,
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with partial_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)
    if installer_path.exists():
        installer_path.unlink()
    shutil.move(str(partial_path), str(installer_path))
    return installer_path


def launch_installer(installer_path: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Automatic installation is only available on Windows.")
    subprocess.Popen(
        [
            str(installer_path),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
        ],
        close_fds=True,
    )
