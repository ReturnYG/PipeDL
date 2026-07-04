# PipeDL

PipeDL is a local desktop application for managing deep learning experiments launched from command-line commands. It provides a visual experiment queue, process controls, live logs, and a local interface for users, scripts, and AI agents to register experiments.

## Features

- Card-style desktop queue for experiments
- Automatic serial scheduling: the next queued experiment starts when the current one finishes
- Live stdout/stderr log viewer
- Pause, continue, stop, delete, retry, and reorder operations
- Retry for finished experiments, including succeeded, failed, stopped, and cancelled runs
- Bash, WSL, PowerShell, and CMD command runners
- Local CLI and localhost API for scripts and AI agents
- SQLite-backed local history and per-experiment log files

## Install

Install PipeDL from GitHub Releases:

1. Open the project's GitHub page.
2. Go to `Releases`.
3. Download `PipeDL-Setup-<version>.exe`.
4. Run the installer.
5. Launch `PipeDL` from the Start Menu.

The installer includes:

- `PipeDL.exe`: the desktop application
- `pipedl.exe`: the CLI used to register and control experiments

On startup, the installed Windows app checks GitHub Releases for a newer stable version. If an update is available, PipeDL asks before downloading `PipeDL-Setup-<version>.exe` and starting the installer automatically.

Runtime data is stored under:

```text
%LOCALAPPDATA%\PipeDL\.pipedl\pipedl.db
%LOCALAPPDATA%\PipeDL\runs\<experiment_id>\
```

## Uninstall

Uninstall PipeDL from Windows Settings or Control Panel.

The uninstaller removes:

- The installed application files
- Start Menu shortcuts
- The `pipedl` PATH entry
- Local database and experiment logs under `%LOCALAPPDATA%\PipeDL`

If PipeDL is still running, the uninstaller attempts to stop `PipeDL.exe` and `pipedl.exe` before removing files.

## Desktop Usage

Start `PipeDL` from the Start Menu. The main window displays experiments as queue cards.

To disable startup update checks, set the environment variable:

```powershell
setx PIPEDL_DISABLE_UPDATE_CHECK 1
```

Card actions depend on experiment status:

- Running: `Pause`, `Stop`, `Delete`
- Paused: `Continue`, `Stop`, `Delete`
- Queued: drag the left `☰` handle to reorder; `Pause Queue` / `Continue Queue`, `Cancel`, `Delete`
- Finished: `Retry`, `Select`, `Delete`

Selecting a card opens its full command details and live stdout/stderr logs on the right.

Use `Demo x5` to add five simulated training experiments. Each demo runs 50 epochs with 60 seconds per epoch; the fourth demo intentionally fails so the retry flow can be tested.

## Add Experiments

Start the PipeDL desktop app first, then register experiments with `pipedl.exe`.

PowerShell example:

```powershell
pipedl run --name train-ps --shell powershell --cwd D:\project -- python train.py
```

WSL example:

```powershell
pipedl run --name train-wsl --shell wsl --cwd /mnt/d/project -- python train.py --config config.yaml
```

Bash example:

```bash
pipedl run --name train-bash --shell bash --cwd /mnt/d/project -- python train.py --config config.yaml
```

`--name` is recommended but optional. If omitted or empty, PipeDL assigns names such as `Exp.01`, `Exp.02`, and so on.

## CLI Commands

```bash
pipedl status
pipedl list
pipedl demo
pipedl stop <experiment_id>
pipedl cancel <experiment_id>
pipedl delete <experiment_id>
pipedl retry <experiment_id>
pipedl move <experiment_id> <position>
pipedl pause
pipedl resume
```

## Agent Integration

AI agents and scripts should register long-running experiments with PipeDL instead of launching them directly.

```bash
pipedl run \
  --name agent-exp-001 \
  --shell bash \
  --cwd /mnt/d/project \
  --created-by agent:codex \
  -- python train.py --config a.yaml --gpu 0
```

Agents can also submit experiments to the local API:

```http
POST http://127.0.0.1:48127/experiments
```

```json
{
  "name": "agent-exp-001",
  "command": "python train.py --config a.yaml",
  "shell": "bash",
  "cwd": "/mnt/d/project",
  "created_by": "agent:codex"
}
```

The desktop app must be running because it owns the queue scheduler and process manager.
