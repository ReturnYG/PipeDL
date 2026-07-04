# Agent Integration

PipeDL accepts experiment registrations from other agents through two stable entry points:

1. CLI registration with `pipedl run`
2. Localhost-only HTTP registration on `127.0.0.1:48127`

The desktop app must be running because it owns the queue scheduler and process manager.

## Recommended Agent Workflow

Use this flow whenever an agent wants to launch a deep learning experiment:

```text
check PipeDL status
  -> if unavailable, ask the user to start PipeDL
  -> submit command to PipeDL
  -> record returned experiment id
  -> optionally poll status/logs
```

## CLI Registration

```bash
pipedl run \
  --name <name> \
  --shell <bash|wsl|powershell|cmd> \
  --cwd <working-directory> \
  --created-by agent:<agent-name> \
  -- <command> <args>
```

`--name` is recommended but optional. Empty names are automatically displayed as `Exp.01`, `Exp.02`, and so on.

Example:

```bash
pipedl run \
  --name shhb_moe_lr1e4_gpu0 \
  --shell bash \
  --cwd /mnt/d/Dev/project/crowdcounting_moe \
  --created-by agent:codex \
  -- python train.py --config workspace/configs/shhb.yaml --gpu 0
```

The CLI prints JSON containing the experiment `id`, status, command, and log paths.

## HTTP Registration

```bash
curl -s http://127.0.0.1:48127/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "shhb_moe_lr1e4_gpu0",
    "command": "python train.py --config workspace/configs/shhb.yaml --gpu 0",
    "shell": "bash",
    "cwd": "/mnt/d/Dev/project/crowdcounting_moe",
    "created_by": "agent:codex",
    "tags": "shhb,moe,gpu0"
  }'
```

## Polling

```bash
pipedl status
pipedl list
```

HTTP:

```text
GET http://127.0.0.1:48127/summary
GET http://127.0.0.1:48127/experiments
GET http://127.0.0.1:48127/experiments/<id>
GET http://127.0.0.1:48127/experiments/<id>/logs?stream=stdout
GET http://127.0.0.1:48127/experiments/<id>/logs?stream=stderr
```

## Control

```text
POST /experiments/<id>/stop
POST /experiments/<id>/pause
POST /experiments/<id>/resume
POST /experiments/<id>/cancel
POST /experiments/<id>/delete
POST /experiments/<id>/retry
POST /experiments/<id>/move
POST /queue/pause
POST /queue/resume
```

For `/experiments/<id>/move`, send:

```json
{"position": 1}
```

## Important Rule

Agents should not detach the process themselves. Avoid `nohup`, `setsid`, background `&`, new terminals, or raw long-running training commands. PipeDL must be the parent process so it can capture logs, detect completion, and start the next queued experiment.
