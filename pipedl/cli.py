from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

from .config import get_host, get_port
from .demo import demo_experiment
from .models import SUPPORTED_SHELLS, command_from_args


def api_url(path: str, host: str, port: int) -> str:
    return f"http://{host}:{port}{path}"


def api_request(method: str, path: str, payload: dict | None = None, host: str | None = None, port: int | None = None) -> dict:
    host = host or get_host()
    port = port or get_port()
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(api_url(path, host, port), data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot connect to PipeDL desktop app at http://{host}:{port}. Start the matching PipeDL instance first."
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipedl_cli")
    parser.add_argument("--host", default=get_host(), help="PipeDL API host.")
    parser.add_argument("--port", type=int, default=get_port(), help="PipeDL API port.")
    sub = parser.add_subparsers(dest="command_name", required=True)

    app = sub.add_parser("app", help="Start the local desktop app.")
    app.add_argument("--profile", help="Isolated profile name, for example dev or test.")
    app.add_argument("--root", help="Override PipeDL data root directory for this app instance.")
    app.add_argument("--state-dir", help="Override PipeDL state directory for this app instance.")
    app.add_argument("--runs-dir", help="Override PipeDL runs directory for this app instance.")

    run = sub.add_parser("run", help="Queue an experiment command.")
    run.add_argument("--name", default="")
    run.add_argument("--shell", default="bash", choices=sorted(SUPPORTED_SHELLS))
    run.add_argument("--cwd", default=".")
    run.add_argument("--created-by", default="cli")
    run.add_argument("--tags", default="")
    run.add_argument("--notes", default="")
    run.add_argument("cmd", nargs=argparse.REMAINDER)

    sub.add_parser("list", help="List experiments.")
    sub.add_parser("status", help="Show queue summary.")
    sub.add_parser("demo", help="Queue five simulated training experiments.")

    stop = sub.add_parser("stop", help="Stop the currently running experiment.")
    stop.add_argument("experiment_id", nargs="?")

    cancel = sub.add_parser("cancel", help="Cancel a queued experiment.")
    cancel.add_argument("experiment_id")

    delete = sub.add_parser("delete", help="Delete an experiment and its logs.")
    delete.add_argument("experiment_id")

    retry = sub.add_parser("retry", help="Retry a failed experiment by copying it to the queue tail.")
    retry.add_argument("experiment_id")

    move = sub.add_parser("move", help="Move a queued experiment to a 1-based position.")
    move.add_argument("experiment_id")
    move.add_argument("position", type=int)

    sub.add_parser("pause", help="Pause the queue.")
    sub.add_parser("resume", help="Resume the queue.")
    return parser


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command_name == "app":
        if args.profile:
            os.environ["PIPEDL_PROFILE"] = args.profile
        if args.root:
            os.environ["PIPEDL_ROOT"] = args.root
        if args.state_dir:
            os.environ["PIPEDL_STATE_DIR"] = args.state_dir
        if args.runs_dir:
            os.environ["PIPEDL_RUNS_DIR"] = args.runs_dir
        try:
            from .app import run_app
        except ModuleNotFoundError as exc:
            if exc.name == "tkinter":
                raise SystemExit(
                    "Tkinter is not available in this Python environment. "
                    "Use a Python build with Tk support, or run PipeDL on Windows/Python where tkinter is installed."
                ) from exc
            raise

        run_app(host=args.host, port=args.port)
        return

    if args.command_name == "run":
        cmd = args.cmd
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        if not cmd:
            raise SystemExit("Missing experiment command after --")
        result = api_request(
            "POST",
            "/experiments",
            {
                "name": args.name,
                "command": command_from_args(cmd),
                "shell": args.shell,
                "cwd": args.cwd,
                "created_by": args.created_by,
                "tags": args.tags,
                "notes": args.notes,
            },
            host=args.host,
            port=args.port,
        )
        print_json(result)
        return

    if args.command_name == "list":
        print_json(api_request("GET", "/experiments", host=args.host, port=args.port))
        return

    if args.command_name == "status":
        print_json(api_request("GET", "/summary", host=args.host, port=args.port))
        return

    if args.command_name == "demo":
        created = []
        for index in range(1, 6):
            exp = demo_experiment(index)
            created.append(
                api_request(
                    "POST",
                    "/experiments",
                    {
                        "name": exp.name,
                        "command": exp.command,
                        "shell": exp.shell,
                        "cwd": exp.cwd,
                        "created_by": exp.created_by,
                        "tags": exp.tags,
                        "notes": exp.notes,
                    },
                    host=args.host,
                    port=args.port,
                )
            )
        print_json({"experiments": created})
        return

    if args.command_name == "stop":
        exp_id = args.experiment_id or "current"
        print_json(api_request("POST", f"/experiments/{exp_id}/stop", host=args.host, port=args.port))
        return

    if args.command_name == "cancel":
        print_json(api_request("POST", f"/experiments/{args.experiment_id}/cancel", host=args.host, port=args.port))
        return

    if args.command_name == "delete":
        print_json(api_request("POST", f"/experiments/{args.experiment_id}/delete", host=args.host, port=args.port))
        return

    if args.command_name == "retry":
        print_json(api_request("POST", f"/experiments/{args.experiment_id}/retry", host=args.host, port=args.port))
        return

    if args.command_name == "move":
        print_json(
            api_request(
                "POST",
                f"/experiments/{args.experiment_id}/move",
                {"position": args.position},
                host=args.host,
                port=args.port,
            )
        )
        return

    if args.command_name == "pause":
        print_json(api_request("POST", "/queue/pause", host=args.host, port=args.port))
        return

    if args.command_name == "resume":
        print_json(api_request("POST", "/queue/resume", host=args.host, port=args.port))
        return

    raise SystemExit(f"Unsupported command: {args.command_name}")


if __name__ == "__main__":
    main(sys.argv[1:])
