"""Short HTTP integration check. All subprocess workloads are submitted through PipeDL.

Usage: python scripts/smoke.py path/to/pipedl[.exe]
Uses a disposable data directory and an available local port; never the user's queue.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    binary = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="pipedl-smoke-") as folder:
        root = Path(folder)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, PIPEDL_ROOT=str(root), PIPEDL_PORT=str(port))
        app = subprocess.Popen([binary, "--headless"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        base = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        token = ""

        def call(path, body=None, expected=200, headers=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", **(headers or {})})
            try:
                response = opener.open(req, timeout=10)
            except urllib.error.HTTPError as e:
                response = e
            with response:
                text = response.read().decode()
                assert response.status == expected, (path, response.status, text)
                return json.loads(text)

        def wait_status(exp, statuses):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                current = call("/experiments/" + exp["id"])
                if current["status"] in statuses:
                    return current
                time.sleep(.05)
            raise AssertionError(("timed out", current))

        def action(e, name, body=None, expected=200):
            return call(f"/experiments/{e['id']}/{name}", body or {}, expected)

        def add(name, command):
            return call("/experiments", {"name": name, "command": command, "shell": "powershell" if os.name == "nt" else "bash", "cwd": folder}, 201)

        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if app.poll() is not None:
                    raise RuntimeError(app.stderr.read().decode())
                if (root / ".pipedl/api-token").exists():
                    token = (root / ".pipedl/api-token").read_text().strip()
                    try:
                        call("/health")
                        break
                    except OSError:
                        pass
                time.sleep(.1)
            else:
                raise AssertionError("app did not start")
            call("/summary", expected=401, headers={"Authorization": "Bearer wrong"})
            call("/summary", expected=403, headers={"Origin": "https://untrusted.example"})
            call("/summary", expected=403, headers={"Host": "attacker.example"})
            call("/queue/pause", {})
            one = add("smoke-one", "Write-Output 'first'; Start-Sleep 20" if os.name == "nt" else "echo first; sleep 20")
            two = add("smoke-two", "Write-Output 'second'" if os.name == "nt" else "printf 'second\\n'")
            action(two, "move", {"position": 1})
            assert call("/experiments")["experiments"][0]["id"] == two["id"]
            action(one, "move", {"position": 1})
            # Opening another owner on a different port must fail without touching this queue.
            other = subprocess.run([binary, "--headless"], env={**env, "PIPEDL_PORT": str(port + 1 if port < 65535 else port - 1)}, capture_output=True, timeout=15)
            assert other.returncode != 0
            call("/queue/resume", {})
            wait_status(one, {"running"})
            action(two, "stop", expected=409)
            assert call("/experiments/" + one["id"])["status"] == "running"
            # A spawned PID does not mean a cold PowerShell runtime has reached the script.
            # Establish workload readiness before testing its pause/resume cycle.
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                log = call(f"/experiments/{one['id']}/logs?stream=stdout&offset=0")
                if "first" in log["text"]:
                    break
                time.sleep(.05)
            assert "first" in log["text"], {
                "log": log,
                "experiment": call("/experiments/" + one["id"]),
                "stderr": call(f"/experiments/{one['id']}/logs?stream=stderr&offset=0"),
            }
            action(one, "pause")
            assert call("/experiments/" + one["id"])["status"] == "paused"
            action(one, "resume")
            assert call(f"/experiments/{one['id']}/logs?stream=stdout&offset={log['offset']}")["text"] == ""
            start = time.monotonic()
            action(one, "stop", expected=202)
            assert time.monotonic() - start < 2, "stop request should not wait for graceful timeout"
            wait_status(one, {"stopped"})
            wait_status(two, {"succeeded"})
            failed = add("smoke-failure", "exit 7")
            assert wait_status(failed, {"failed"})["exit_code"] == 7
            retry = action(two, "retry", expected=201)
            assert retry["id"] != two["id"]
            wait_status(retry, {"succeeded"})
            call("/queue/pause", {})
            cancelled = add("smoke-cancel", "echo should-not-run")
            action(cancelled, "cancel")
            assert call("/experiments/" + cancelled["id"])["pid"] is None
            action(cancelled, "delete", expected=202)
            call("/experiments/" + cancelled["id"], expected=404)
            assert len(call("/experiments?limit=1&offset=1")["experiments"]) == 1
            call("/experiments/delete-completed", {"confirm": False}, expected=400)
            assert call("/experiments/" + two["id"])["status"] == "succeeded"
            queued = add("keep-queued", "echo pending")
            result = call("/experiments/delete-completed", {"confirm": True})
            assert result["deleted"] == 2 and result["failures"] == [], result
            for e in (two, retry):
                call("/experiments/" + e["id"], expected=404)
            assert call("/experiments/" + failed["id"])["status"] == "failed"
            assert call("/experiments/" + one["id"])["status"] == "stopped"
            assert call("/experiments/" + queued["id"])["status"] == "queued"
            assert call("/experiments/delete-completed", {"confirm": True})["deleted"] == 0
            # SSE ready event proves authenticated streaming is reachable.
            req = urllib.request.Request(base + "/events", headers={"Authorization": "Bearer " + token})
            with opener.open(req, timeout=5) as stream:
                assert stream.readline().strip() == b"event: change"
            print("PASS: startup, auth/origin/host, single owner, serial queue, ID targeting, pause/resume, stop latency, logs, failure, retry, cancel/delete, pagination, SSE")
        finally:
            try:
                call("/queue/pause", {})
                for e in call("/experiments")["experiments"]:
                    if e["status"] in {"running", "paused"}:
                        action(e, "stop", expected=202)
                        wait_status(e, {"stopped"})
            except Exception:
                pass
            if os.name != "nt":
                app.send_signal(signal.SIGINT)
                try:
                    app.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    app.kill()
            else:
                app.terminate()
            app.communicate(timeout=10)


if __name__ == "__main__":
    main()
