# PipeDL

**让实验有序运行。** PipeDL 是用于管理本机实验队列的桌面软件，适合训练、评估和基准测试任务。

新版采用 **Tauri 2 + Rust + React/TypeScript + HTTP API**。软件本身无需 Python 环境；实验命令仍可使用你自己的 Python 或其他运行环境。

## 下载与安装

从 [GitHub Releases](https://github.com/ReturnYG/PipeDL/releases/latest) 下载 Windows x64 版本：

- `PipeDL_0.3.2_x64-setup.exe`：安装程序，缺少 WebView2 时会引导安装。
- `PipeDL.exe`：可直接运行的程序，同样需要 WebView2。
- `SHA256SUMS`：下载文件的 SHA-256 校验值。

升级前请完成或停止实验，并从托盘完全退出旧版。关闭窗口只会隐藏到托盘。旧 Python 版用户请先阅读下方的升级说明。

## 主要功能

- 串行实验队列，支持创建、暂停、恢复、停止、取消、删除、重试和调整顺序。
- 成功与失败使用不同颜色和图标；历史页可在二次确认后删除所有分页中的成功实验及日志，保留失败和其他状态的记录。
- 队列与历史分页、当前页搜索、实验详情，以及增量读取的标准输出和错误日志。
- 通过 SSE 推送状态变化，进程控制与数据库操作在界面线程之外执行。
- 桌面界面与外部脚本统一通过带鉴权的 HTTP API 操作，不再提供独立控制 CLI。
- 使用 SQLite 保存历史，按实验保存日志，迁移旧数据库前自动备份。
- 支持系统托盘；存在由本应用管理的活动任务时拒绝退出，避免意外中断。
- Windows 支持 PowerShell、CMD、Bash、WSL；Linux 支持 Bash。通过 Windows Job Objects 或 POSIX 进程组管理子进程。
- 重启后隔离异常中断的任务，不会直接向旧记录中的 PID 发送终止信号。

## 数据目录与 API 鉴权

| 平台 | 默认数据目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\PipeDL` |
| Linux | `$XDG_DATA_HOME/pipedl`，未设置时为 `~/.local/share/pipedl` |

API 默认仅监听 **`127.0.0.1:48127`**。`GET /health` 无需鉴权，其他接口需要 `Authorization: Bearer <token>`。令牌保存在 `<数据目录>/.pipedl/api-token`，也可以在设置中复制。不要将令牌写入仓库或公开日志。

可通过环境变量调整运行配置：

| 变量 | 用途 |
|---|---|
| `PIPEDL_ROOT` | 指定完整数据根目录 |
| `PIPEDL_PROFILE=dev` | 使用独立的开发数据目录 |
| `PIPEDL_PORT` | 修改 API 端口 |

旧版的 `PIPEDL_HOST`、`PIPEDL_STATE_DIR` 和 `PIPEDL_RUNS_DIR` 已不再支持。

## 通过 HTTP API 提交实验

先启动 PipeDL，再提交任务。以下示例用于 PipeDL 运行在 Linux、使用默认数据目录和端口的情况；请替换实际工作目录和实验命令：

```bash
TOKEN=$(cat "${XDG_DATA_HOME:-$HOME/.local/share}/pipedl/.pipedl/api-token")
curl --fail http://127.0.0.1:48127/experiments \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"baseline","command":"python -u train.py","shell":"bash","cwd":"/absolute/project/path","created_by":"agent:codex"}'
```

成功注册返回 HTTP 201 和实验记录，请保存其中的 `id`。注册成功表示任务已进入队列，不一定已经开始运行。请求超时时，先查询队列再决定是否重新提交，避免重复创建。

当 PipeDL 运行在 Windows 上时，使用 `powershell` 或 `cmd` 配合 Windows 绝对目录；使用 `wsl` 时传入 Linux 绝对目录。`bash` 指应用所在主机上的 Bash。可通过 `GET /info` 查询主机平台和支持的 Shell。

完整接口见 [HTTP API 文档](docs/agent-integration.md)。让 AI 代理提交实验时，可参考 [AGENTS.md](AGENTS.md)；其他项目中的旧版 CLI 指令也需要同步更新。

## 开发与构建

需要 Node.js 22+ 和稳定版 Rust。Windows 还需要 MSVC C++ 构建工具、Windows SDK 和 WebView2；Linux 桌面构建需要 GTK3、WebKitGTK 4.1、Ayatana AppIndicator、librsvg 和 C 编译器，推荐 Ubuntu 24.04。

```bash
npm ci
npm run desktop
```

按当前构建平台选择打包命令：

```bash
npm run package -- --bundles nsis   # Windows 安装包
npm run package -- --bundles deb    # Linux 软件包
```

开发时请同时使用独立数据目录和端口，避免影响正式队列：

```bash
export PIPEDL_ROOT="$PWD/.test-data/dev"
export PIPEDL_PORT=48128
npm run desktop
```

本工作区额外下载的工具链位于 `.tools/`，不随仓库分发。已配置本地 Rust 工具链时，可执行 `source scripts/env.sh`。旧版 WSL 主机可通过 `scripts/in-ubuntu.sh` 使用预先准备的本地 Ubuntu 环境；新机器请先安装上述构建依赖。详见 [开发说明](docs/development.md)和[架构与性能设计](docs/architecture.md)。

同一个程序也支持 `--headless`，供集成测试或明确需要的纯 API 部署使用。该模式运行队列服务，不是提交命令的 CLI：

```bash
cargo run --manifest-path src-tauri/Cargo.toml --no-default-features -- --headless
```

## 验证

```bash
npm run build
cargo test --manifest-path src-tauri/Cargo.toml --no-default-features
cargo build --manifest-path src-tauri/Cargo.toml --no-default-features
python3 scripts/smoke.py src-tauri/target/debug/pipedl
# 先启动隔离的测试 API，具体配置见开发说明。
npm run test:ui
```

CI 覆盖核心逻辑、实际 HTTP 操作流程、前端检查和 Windows 桌面构建。Python 仅用于集成测试，不是应用运行依赖。Windows 原生桌面已完成实际运行验证；Linux 核心与浏览器界面已有测试，Linux 原生桌面窗口尚未完成本地运行验证。

## 升级与回退

从旧 Python 版升级前，先停止实验并完全退出，再备份整个数据目录。**旧 Inno Setup 卸载程序会删除运行数据，必须先备份再卸载。** 新版使用相同的默认数据目录，并在迁移旧数据库前自动创建备份；自定义路径和回退步骤见 [迁移说明](docs/migration.md)。

旧 Python 源码已从当前目录移除，仍可在 Git 标签 [`v0.3.2` 的 `legacy/python/`](https://github.com/ReturnYG/PipeDL/tree/v0.3.2/legacy/python) 中获取。

设置中的更新入口会打开官方发布页面。当前安装包未进行代码签名，尚未启用签名自动更新。
