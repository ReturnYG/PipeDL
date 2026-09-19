# PipeDL agent instructions

PipeDL owns the experiment queue. Register long-running training, evaluation and benchmark commands through HTTP; do not use direct background commands, nohup, detached terminals or setsid unless the user explicitly requests bypassing PipeDL.

1. Check `GET http://127.0.0.1:48127/health` (or `PIPEDL_PORT`). If unavailable, ask the user to start PipeDL; do not bypass the queue.
2. Read `<data-root>/.pipedl/api-token` or copy the token in Settings. Default root: `%LOCALAPPDATA%/PipeDL` on Windows; `$XDG_DATA_HOME/pipedl` / `~/.local/share/pipedl` on Linux. Respect `PIPEDL_ROOT` and `PIPEDL_PROFILE`.
3. Submit JSON to `POST /experiments` with `Authorization: Bearer <token>` and `Content-Type: application/json`.
4. Report the returned experiment `id`. Never print the token.

```json
{"name":"baseline","command":"python -u train.py --config configs/baseline.yaml","shell":"bash","cwd":"/absolute/project","created_by":"agent:codex"}
```

Use bash for Linux/WSL-hosted PipeDL, powershell/cmd for native Windows tasks, and wsl for Windows-hosted PipeDL launching the default WSL distribution. WSL requires a Linux absolute cwd; other runners require an existing absolute host directory.

See `docs/agent-integration.md`. There is no control CLI in 0.3.

## Development

Active code is in `src-tauri/` and `ui/`. `legacy/python/` is preserved for rollback, not a production entry point. Use disposable roots and separate ports for tests. Short build/unit/integration checks are not long-running experiments; subprocess test workloads must still go through the test instance API.

Keep frontend build, Rust tests and `scripts/smoke.py` passing. Commit lockfiles, not `.tools/`, bundles or runtime data.
