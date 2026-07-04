# PipeDL Agent Instructions

PipeDL is the experiment queue owner for this workspace. If you are an AI agent asked to launch a long-running training, evaluation, benchmark, or deep learning experiment, register it with PipeDL instead of starting it directly.

## Required Behavior

1. Check that the PipeDL desktop app is running:

   ```bash
   pipedl status
   ```

2. If the app is not running, tell the user to start it:

   ```bash
   PipeDL
   ```

3. Register the experiment through the CLI:

   ```bash
   pipedl run \
     --name <short-experiment-name> \
     --shell <bash|wsl|powershell|cmd> \
     --cwd <working-directory> \
     --created-by agent:<agent-name> \
     -- <original command and args>
   ```

   `--name` is recommended for readability. If omitted or empty, PipeDL assigns `Exp.01`, `Exp.02`, and so on.

4. Do not use `nohup`, background `&`, `setsid`, detached terminals, or direct long-running training commands unless the user explicitly asks to bypass PipeDL.

5. After registration, report the returned experiment `id` to the user.

## Examples

Bash or WSL-side Python:

```bash
pipedl run \
  --name train-baseline \
  --shell bash \
  --cwd /mnt/d/project \
  --created-by agent:codex \
  -- python train.py --config configs/baseline.yaml --gpu 0
```

Windows PowerShell:

```bash
pipedl run \
  --name train-windows \
  --shell powershell \
  --cwd D:\project \
  --created-by agent:codex \
  -- python train.py --config configs\baseline.yaml
```

Explicit WSL runner from Windows:

```bash
pipedl run \
  --name train-wsl \
  --shell wsl \
  --cwd /mnt/d/project \
  --created-by agent:codex \
  -- python train.py --config configs/baseline.yaml
```

## Local HTTP API

Agents may use the localhost API when direct HTTP calls are easier than shelling out:

```http
POST http://127.0.0.1:48127/experiments
Content-Type: application/json
```

```json
{
  "name": "train-baseline",
  "command": "python train.py --config configs/baseline.yaml --gpu 0",
  "shell": "bash",
  "cwd": "/mnt/d/project",
  "created_by": "agent:codex",
  "tags": "baseline,gpu0",
  "notes": "queued by an AI agent"
}
```

Useful endpoints:

```text
GET  /health
GET  /summary
GET  /experiments
GET  /experiments/<id>
GET  /experiments/<id>/logs?stream=stdout
GET  /experiments/<id>/logs?stream=stderr
POST /experiments/<id>/stop
POST /experiments/<id>/pause
POST /experiments/<id>/resume
POST /experiments/<id>/cancel
POST /experiments/<id>/delete
POST /experiments/<id>/retry
POST /experiments/<id>/move   {"position": 1}
POST /queue/pause
POST /queue/resume
```

## Shell Selection

- Use `bash` for commands that should run in the current Linux/WSL environment.
- Use `wsl` for Windows-side agents that need PipeDL to run the command through `wsl.exe`.
- Use `powershell` for Windows PowerShell commands.
- Use `cmd` for Windows `cmd.exe /C` commands.

## Naming

Prefer names that are short but informative:

```text
dataset_model_variant_lr_gpu
```

Examples:

```text
shhb_moe_hard_lr1e4_gpu0
imagenet_resnet50_amp_gpu1
```
