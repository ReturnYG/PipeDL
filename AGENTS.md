# PipeDL agent instructions

PipeDL owns the experiment queue. Register long-running training, evaluation and benchmark commands through HTTP; do not use direct background commands, nohup, detached terminals or setsid unless the user explicitly requests bypassing PipeDL.

1. Check `GET http://127.0.0.1:48127/health` (or `PIPEDL_PORT`). If unavailable, ask the user to start PipeDL; do not bypass the queue.
2. Read `<data-root>/.pipedl/api-token` or copy the token in Settings. Default root: `%LOCALAPPDATA%/PipeDL` on Windows; `$XDG_DATA_HOME/pipedl` / `~/.local/share/pipedl` on Linux. Respect `PIPEDL_ROOT` and `PIPEDL_PROFILE`.
3. Submit JSON to `POST /experiments` with `Authorization: Bearer <token>` and `Content-Type: application/json`.
4. Check the HTTP response and report the returned experiment `id` and actual status. Registration does not mean the task is already running. Never print the token. If a creation request times out, inspect the queue before resubmitting to avoid duplicate experiments.

```json
{"name":"baseline","command":"python -u train.py --config configs/baseline.yaml","shell":"bash","cwd":"/absolute/project","created_by":"agent:codex"}
```

Use bash for Linux/WSL-hosted PipeDL, powershell/cmd for native Windows tasks, and wsl for Windows-hosted PipeDL launching the default WSL distribution. WSL requires a Linux absolute cwd; other runners require an existing absolute host directory.

Use authenticated `GET /info` to identify the app's host platform, data root and supported shells; the agent may run on a different host. If WSL cannot reach Windows localhost, invoke a Windows-side HTTP client. Do not expose the API on all interfaces.

See [the HTTP API reference](https://github.com/ReturnYG/PipeDL/blob/main/docs/agent-integration.md). There is no control CLI in 0.3; do not use legacy `pipedl_cli` instructions.

## Status and deletion

Only `succeeded` means successful completion. Failed, stopped and cancelled experiments must not be reported as successful. After `POST /experiments/{id}/stop` returns HTTP 202, query the record until it reaches a terminal state before claiming it has stopped.

Delete history only within the user's explicit authorization. `POST /experiments/delete-completed` with `{"confirm":true}` permanently removes all `succeeded` records and their logs across all pages, retaining other statuses. The confirmation flag is a protocol requirement, not user authorization. The desktop requires a second confirmation dialog; agents must obtain explicit authorization for this scope if it has not already been given. Report both `deleted` and any `failures` from the response.

## Development

Active code is in `src-tauri/` and `ui/`. The removed Python implementation is available in Git tag `v0.3.2` under `legacy/python/`, not as a production entry point. Use disposable roots and separate ports for tests. Short build/unit/integration checks are not long-running experiments; subprocess test workloads must still go through the test instance API.

Keep frontend build, Rust tests and `scripts/smoke.py` passing. Commit lockfiles, not `.tools/`, bundles or runtime data.
