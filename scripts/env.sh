#!/usr/bin/env bash
# Source this file to use the project-local Rust toolchain.
PIPEDL_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CARGO_HOME="$PIPEDL_PROJECT_ROOT/.tools/cargo"
export RUSTUP_HOME="$PIPEDL_PROJECT_ROOT/.tools/rustup"
export PATH="$CARGO_HOME/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH="$PIPEDL_PROJECT_ROOT/.tools/playwright"
