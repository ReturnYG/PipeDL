# PipeDL

PipeDL is a local desktop program for managing deep learning experiments launched from CLI commands. It provides a queue, process monitoring, live logs, and a CLI/API entry point for users or AI agents.

This first version uses only Python's standard library:

- Tkinter desktop GUI with card-style experiment rows
- SQLite storage
- Localhost-only HTTP API
- CLI command registration
- Serial queue scheduler
- Bash, WSL, PowerShell, and CMD runners

## Install On Windows

Most users should install PipeDL from GitHub Releases:

1. Open the project's GitHub page.
2. Go to `Releases`.
3. Download `PipeDL-Setup-<version>.exe`.
4. Run the installer.
5. Launch `PipeDL` from the Start Menu.

The installer includes:

- `PipeDL.exe`: the desktop GUI app
- `pipedl.exe`: the CLI used by agents or scripts to register commands with the running app

Runtime data is stored in the user's application data directory by default:

```text
%LOCALAPPDATA%\PipeDL\.pipedl\pipedl.db
%LOCALAPPDATA%\PipeDL\runs\<experiment_id>\
```

Advanced users can override this with `PIPEDL_ROOT`, `PIPEDL_STATE_DIR`, or `PIPEDL_RUNS_DIR`.

## Run From Source

```bash
python -m pipedl app
```

On Linux/WSL, the Python environment must include Tkinter. On Windows Python installs, Tkinter is usually included by default.

The main window shows experiments as queue cards. Each card contains the status, command metadata, and action buttons:

- Running cards: `Pause`, `Stop`
- Paused cards: `Continue`, `Stop`
- Queued cards: `Pause Queue` / `Continue Queue`, `Up`, `Down`, `Cancel`, `Delete`, `Top`
- Finished cards, including succeeded, failed, stopped, or cancelled experiments: `Retry`, `Select`, `Delete`

Selecting a card opens its command details and live stdout/stderr log panes on the right.

Use `Demo x5` to add five simulated training commands. Each demo command runs 50 epochs and sleeps 60 seconds per epoch, so the queue remains active long enough to observe pause, stop, delete, retry, and automatic next-task startup behavior. The fourth demo intentionally fails at the final export step so the retry flow is visible.

Or, after installing the package in editable mode:

```bash
pip install -e .
pipedl app
```

## Add An Experiment From CLI

Start the desktop app first, then submit experiments:

```bash
python -m pipedl run --name test --shell bash --cwd . -- python -c "print('hello from PipeDL')"
```

`--name` is recommended but optional. If omitted or empty, PipeDL assigns `Exp.01`, `Exp.02`, and so on.

WSL example:

```bash
python -m pipedl run --name train-wsl --shell wsl --cwd /mnt/d/project -- python train.py --config config.yaml
```

PowerShell example:

```bash
python -m pipedl run --name train-ps --shell powershell --cwd D:\project -- python train.py
```

## CLI Commands

```bash
PipeDL.exe
pipedl.exe run --name exp001 --shell powershell --cwd D:\project -- python train.py
pipedl.exe list
pipedl.exe status
pipedl.exe demo
pipedl.exe stop <experiment_id>
pipedl.exe cancel <experiment_id>
pipedl.exe delete <experiment_id>
pipedl.exe retry <experiment_id>
pipedl.exe move <experiment_id> <position>
pipedl.exe pause
pipedl.exe resume
```

When running from source, use:

```bash
python -m pipedl app
python -m pipedl run --name exp001 --shell bash --cwd . -- python train.py
python -m pipedl list
python -m pipedl status
python -m pipedl demo
python -m pipedl stop <experiment_id>
python -m pipedl cancel <experiment_id>
python -m pipedl delete <experiment_id>
python -m pipedl retry <experiment_id>
python -m pipedl move <experiment_id> <position>
python -m pipedl pause
python -m pipedl resume
```

## Agent Integration

Other agents should register long-running experiments with PipeDL instead of launching them directly. The easiest path is the CLI:

```bash
python -m pipedl run \
  --name agent-exp-001 \
  --shell bash \
  --cwd /mnt/d/project \
  --created-by agent:codex \
  -- python train.py --config a.yaml --gpu 0
```

Names are recommended for readability. If an agent omits the name, PipeDL will display the experiment as `Exp.01`, `Exp.02`, and so on.

Agents can also submit experiments to the local API:

```http
POST http://127.0.0.1:48127/experiments
```

Body:

```json
{
  "name": "agent-exp-001",
  "command": "python train.py --config a.yaml",
  "shell": "bash",
  "cwd": "/mnt/d/project",
  "created_by": "agent:codex"
}
```

The desktop app must be running because it owns the scheduler and local API.

For agent-facing rules and copyable prompts, see `AGENTS.md` and `docs/agent-integration.md`.

## Project Layout

```text
pipedl/
  app.py              Desktop GUI
  api.py              Localhost HTTP API
  cli.py              CLI entry point
  config.py           Paths and app config
  models.py           Shared constants and helpers
  process_manager.py  Shell runners and process control
  scheduler.py        Queue loop
  storage.py          SQLite persistence
```

Runtime files are created under:

```text
%LOCALAPPDATA%\PipeDL\.pipedl\pipedl.db
%LOCALAPPDATA%\PipeDL\runs\<experiment_id>\stdout.log
%LOCALAPPDATA%\PipeDL\runs\<experiment_id>\stderr.log
```

## Build A Release

Windows release builds are produced by GitHub Actions when a tag is pushed:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The release workflow builds:

- `PipeDL-Setup-<version>.exe`
- `PipeDL-portable-<version>.zip`

To build locally on Windows:

```powershell
.\scripts\build_windows.ps1 -Version 0.1.0
```

Install Inno Setup first if you want the `.exe` installer. Use `-SkipInstaller` to build only `PipeDL.exe` and `pipedl.exe`.
