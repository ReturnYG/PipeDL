# PipeDL

**Your experiments, in order.** A local desktop workspace for experiment queues.

PipeDL 0.3 uses **Tauri 2 + Rust + React/TypeScript + authenticated HTTP API**. Python is not required by the application; experiment commands can still use any Python environment.

## Features

- Serial experiment scheduling; creation, pause/resume, stop, cancel, delete, retry and reordering.
- Distinct success/failure cards; remove all successful experiments across pages after a second confirmation, preserving failures and active work.
- Web UI with queue/history, pagination, searchable current page, details and bounded incremental stdout/stderr.
- Immediate state notifications over SSE. Process control and SQLite never run on the UI thread.
- One HTTP API for the desktop and scripts. No separately installed control CLI.
- SQLite history, per-experiment log files, automatic backup of the legacy database.
- System tray: closing the window keeps the queue running. Quit refuses while an owned task is active.
- Windows PowerShell/CMD/Bash/WSL runners; Linux Bash runner. POSIX process groups and Windows Job Objects manage descendants.
- Interrupted runs are quarantined after restart; inherited PIDs are never blindly signalled.

## Run and build

Use Node.js 22+ and stable Rust. Windows needs MSVC C++ build tools, Windows SDK and WebView2. Linux desktop builds need GTK3, WebKitGTK 4.1, Ayatana AppIndicator, librsvg and a C compiler (Ubuntu 24.04 recommended).

```bash
npm ci
npm run desktop
npm run package -- --bundles nsis   # Windows installer
npm run package -- --bundles deb    # Linux package
```

Project-local tools are under `.tools/`; source `scripts/env.sh` for Rust. `scripts/in-ubuntu.sh` executes commands in the local Ubuntu environment on older WSL hosts. See [development](docs/development.md).

Locally verified Windows deliverables are placed in `artifacts/`: run `PipeDL.exe` directly, or use the NSIS setup executable. Fully exit the old app before opening the same data directory. See [design and performance changes](docs/architecture.md).

The same executable supports `--headless` for integration testing or an explicitly chosen API-only deployment. This is a queue owner, not a command-submission CLI:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --no-default-features -- --headless
```

## Data and authentication

Windows data: `%LOCALAPPDATA%/PipeDL`. Linux data: `$XDG_DATA_HOME/pipedl` or `~/.local/share/pipedl`.

The API listens **only on `127.0.0.1:48127`**. `/health` is public. Other endpoints require `Authorization: Bearer <token>`. The persistent token is in `<data>/.pipedl/api-token`; the desktop reads it automatically and Settings can copy it. Credentials never appear in URLs or application logs.

`PIPEDL_PROFILE=dev` selects a separate data directory; `PIPEDL_ROOT` overrides the whole root; `PIPEDL_PORT` selects another port. Use both a separate root/profile and port for development. Legacy `PIPEDL_HOST`, `PIPEDL_STATE_DIR` and `PIPEDL_RUNS_DIR` are not supported.

```bash
export PIPEDL_ROOT="$PWD/.test-data/dev"
export PIPEDL_PORT=48128
npm run desktop
```

## Submit

```bash
TOKEN=$(cat "$HOME/.local/share/pipedl/.pipedl/api-token")
curl --fail http://127.0.0.1:48127/experiments -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name":"baseline","command":"python -u train.py","shell":"bash","cwd":"/absolute/project/path","created_by":"agent:codex"}'
```

Use `powershell`/`cmd` with an absolute Windows directory, or `wsl` with an absolute Linux directory when the app runs on Windows. `bash` means Bash installed on the app host. [Full API](docs/agent-integration.md).

## Verify

```bash
npm run build
cargo test --manifest-path src-tauri/Cargo.toml --no-default-features
cargo build --manifest-path src-tauri/Cargo.toml --no-default-features
python3 scripts/smoke.py src-tauri/target/debug/pipedl
# Start an isolated API first; see docs/development.md.
npm run test:ui
```

CI checks core behavior, the real HTTP workflow, frontend and Windows desktop build. Python is used only for the portable integration test.

## Upgrade

Read [migration and rollback](docs/migration.md). The old implementation is archived in `legacy/python/` and excluded from the new distribution. Stop active experiments and fully exit before upgrading. Closing the window only hides it in the tray.

Settings opens the official release page. Unattended installer execution is not carried over; a signed update channel requires release signing keys before activation.
