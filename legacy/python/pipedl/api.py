from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import DEFAULT_HOST, DEFAULT_PORT
from .models import ExperimentCreate, SUPPORTED_SHELLS
from .scheduler import Scheduler
from .storage import Storage, read_tail


class LocalApiServer:
    def __init__(
        self,
        storage: Storage,
        scheduler: Scheduler,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ):
        self.storage = storage
        self.scheduler = scheduler
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=3)

    def _make_handler(self):
        storage = self.storage
        scheduler = self.scheduler

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def _json(self, payload, status: int = 200) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                return json.loads(raw.decode("utf-8") or "{}")

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._json({"ok": True})
                    return
                if parsed.path == "/summary":
                    self._json(storage.summary())
                    return
                if parsed.path == "/experiments":
                    self._json({"experiments": storage.list_experiments()})
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/logs"):
                    exp_id = parsed.path.split("/")[2]
                    exp = storage.get_experiment(exp_id)
                    if not exp:
                        self._json({"error": "not found"}, 404)
                        return
                    query = parse_qs(parsed.query)
                    stream = query.get("stream", ["stdout"])[0]
                    path = exp["stderr_path"] if stream == "stderr" else exp["stdout_path"]
                    self._json({"text": read_tail(path)})
                    return
                if parsed.path.startswith("/experiments/"):
                    exp_id = parsed.path.split("/")[2]
                    exp = storage.get_experiment(exp_id)
                    self._json(exp if exp else {"error": "not found"}, 200 if exp else 404)
                    return
                self._json({"error": "not found"}, 404)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/experiments":
                    data = self._read_json()
                    shell = data.get("shell", "bash")
                    if shell not in SUPPORTED_SHELLS:
                        self._json({"error": f"unsupported shell: {shell}"}, 400)
                        return
                    exp = storage.add_experiment(
                        ExperimentCreate(
                            name=data.get("name") or "",
                            command=data["command"],
                            shell=shell,
                            cwd=data.get("cwd") or ".",
                            created_by=data.get("created_by") or "api",
                            tags=data.get("tags") or "",
                            notes=data.get("notes") or "",
                        )
                    )
                    self._json(exp, 201)
                    return
                if parsed.path == "/queue/pause":
                    storage.set_queue_paused(True)
                    self._json(storage.summary())
                    return
                if parsed.path == "/queue/resume":
                    storage.set_queue_paused(False)
                    self._json(storage.summary())
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/stop"):
                    ok = scheduler.stop_current()
                    self._json({"ok": ok})
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/pause"):
                    ok = scheduler.pause_current()
                    self._json({"ok": ok})
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/resume"):
                    ok = scheduler.resume_current()
                    self._json({"ok": ok})
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/cancel"):
                    exp_id = parsed.path.split("/")[2]
                    self._json({"ok": storage.cancel_queued(exp_id)})
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/delete"):
                    exp_id = parsed.path.split("/")[2]
                    self._json({"ok": scheduler.delete_experiment(exp_id)})
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/retry"):
                    exp_id = parsed.path.split("/")[2]
                    exp = storage.retry_experiment(exp_id)
                    self._json(exp if exp else {"error": "retry is only available for finished experiments"}, 201 if exp else 400)
                    return
                if parsed.path.startswith("/experiments/") and parsed.path.endswith("/move"):
                    exp_id = parsed.path.split("/")[2]
                    data = self._read_json()
                    storage.move_queued(exp_id, int(data["position"]))
                    self._json({"ok": True})
                    return
                self._json({"error": "not found"}, 404)

        return Handler
