#!/usr/bin/env bash
set -euo pipefail
PIPEDL_PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
shopt -s nullglob
binaries=("$PIPEDL_PROJECT_ROOT"/.tools/playwright/chromium-*/chrome-linux*/chrome-local)
exec "${binaries[0]}" "$@"
