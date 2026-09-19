#!/usr/bin/env bash
# Isolated local Ubuntu fallback for hosts too old for WebKitGTK 4.1.
set -euo pipefail
PIPEDL_PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec env LD_LIBRARY_PATH="$PIPEDL_PROJECT_ROOT/.tools/proot/usr/lib/x86_64-linux-gnu" \
  "$PIPEDL_PROJECT_ROOT/.tools/proot/usr/bin/proot-modern" -0 \
  -r "$PIPEDL_PROJECT_ROOT/.tools/ubuntu" -b /dev -b /proc -b /sys -b /tmp \
  -b "$PIPEDL_PROJECT_ROOT" -w "$PIPEDL_PROJECT_ROOT" \
  /usr/bin/env -u LD_LIBRARY_PATH "$@"
