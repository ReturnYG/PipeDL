# Local HTTP API

Start PipeDL first, check `GET /health`, submit commands and record the returned `id`. Do not launch long-running experiments directly or detach them.

All endpoints except `/health` need `Authorization: Bearer <token>`. Read `<data>/.pipedl/api-token` or copy it in Settings. JSON uses `Content-Type: application/json`. API binding is loopback-only. WSL-to-Windows localhost connectivity depends on networking mode; if unavailable, invoke a Windows-side HTTP client rather than exposing the API on all interfaces.

| Method | Route | Behavior |
|---|---|---|
| GET | `/health` | Health and version |
| GET | `/info` | Data root, platform and supported shells |
| GET | `/summary` | Counts and queue pause state |
| GET | `/experiments?status=active&offset=0&limit=50` | Page, `total`, `summary`; limit 1–500, default 100 |
| POST | `/experiments` | Register; returns task, HTTP 201 |
| POST | `/experiments/delete-completed` | `{"confirm":true}`; permanently remove all successful records/logs across pages |
| GET | `/experiments/{id}` | Full record |
| GET | `/experiments/{id}/logs?stream=stdout&offset=0` | Up to 64 KiB, `text`, byte `offset`, `reset`, `more` |
| GET | `/events` | SSE `change`; refetch on any event/reconnect |
| POST | `/experiments/{id}/pause` | Pause owned process tree |
| POST | `/experiments/{id}/resume` | Resume owned paused task |
| POST | `/experiments/{id}/stop` | HTTP 202 after requesting stop; await terminal state |
| POST | `/experiments/{id}/cancel` | Cancel queued task |
| POST | `/experiments/{id}/delete` | HTTP 202; stop active task before deleting record/logs |
| POST | `/experiments/{id}/retry` | New ID; preserve original history; HTTP 201 |
| POST | `/experiments/{id}/move` | `{"position":1}` in the entire queued set |
| POST | `/experiments/{id}/resolve` | Resolve quarantined run after old PID disappears |
| POST | `/queue/pause` | Stop launching tasks; current task unaffected |
| POST | `/queue/resume` | Resume; refused while quarantined runs remain |

`status` accepts `active`, `history`, `all` or an exact status. Pagination never limits scheduling/reordering. No log offset starts at the last 64 KiB. Save the returned byte offset; clear old text when `reset=true`. Render logs as text, never HTML. SSE notifications are not a durable event journal.

```json
{"name":"baseline","command":"python -u train.py --config configs/baseline.yaml","shell":"bash","cwd":"/absolute/project","created_by":"agent:codex","tags":"baseline,gpu0","notes":"Optional"}
```

`command` and `cwd` are required. Empty/omitted name becomes `Exp.01`, `Exp.02`, etc. Apply the selected shell's quoting conventions. POST requests are not automatically retried: a timeout may mean creation succeeded; inspect the queue before resubmitting.

Send `{}` for empty action bodies. Unknown tasks return 404; authentication 401; rejected origin/host 403; state/validation conflicts 409. Malformed JSON/types use Axum 400/422 responses; oversized bodies are rejected. Application errors use `{"error":"..."}`.

Pause does not release GPU memory. Windows native stop terminates the Job Object; POSIX/WSL stop requests TERM then escalates after eight seconds. WSL uses the default distribution and a Linux process-group marker; changing the default distribution during a running task is unsupported. Failed controls are reported without claiming success.

## Bulk removal of successful experiments

`POST /experiments/delete-completed` requires `{"confirm":true}` and the same Bearer token as other mutations. It removes every `succeeded` experiment and its owned log directory across all pages. Failed, stopped, cancelled, orphaned, queued and active experiments are retained. The response is `{"deleted":3,"failures":[]}`; individual filesystem/database failures are reported as `{id,error}` entries and are not counted as deleted. Calling again when no successful records remain returns zero.

The desktop exposes this operation in History with a second confirmation dialog. Cancelling that dialog sends no deletion request.
