"""Start a disposable Rust API, run browser checks, then tear it down."""
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
binary = root / "src-tauri/target/debug" / ("pipedl.exe" if os.name == "nt" else "pipedl")
with tempfile.TemporaryDirectory(prefix="pipedl-ui-") as folder:
    token = Path(folder) / ".pipedl/api-token"
    env = dict(os.environ, PIPEDL_ROOT=folder, PIPEDL_PORT="48129", PIPEDL_TEST_URL="http://127.0.0.1:48129", PIPEDL_TEST_TOKEN=str(token))
    app = subprocess.Popen([str(binary), "--headless"], env=env)
    try:
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError("Test API failed to start")
            if token.exists():
                break
            time.sleep(.1)
        result = subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "run", "test:ui"], cwd=root, env=env)
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        if os.name != "nt":
            app.send_signal(signal.SIGINT)
        else:
            app.terminate()
        try:
            app.wait(timeout=5)
        except subprocess.TimeoutExpired:
            app.kill()
            app.wait()
