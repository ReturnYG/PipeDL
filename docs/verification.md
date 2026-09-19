# 本地验证记录

v0.3.1 增加成功/失败的独立图标和高对比状态样式，以及带二次确认的成功记录批量清理。新增检查覆盖：拒绝未确认请求、保留失败/停止/取消/排队记录、跨 205 条记录清理、删除日志、空集合重复调用，以及界面取消/确认流程。

日期：2026-09-19。测试使用独立临时数据目录和端口，没有迁移或修改现有实验数据。

| 检查 | 结果 |
| --- | --- |
| TypeScript 检查、生产 Web UI 构建 | 通过 |
| Rust 格式、Linux/Windows 核心 Clippy、单元/存储测试 | 通过 |
| Linux Rust HTTP 集成检查 | 通过：鉴权、Origin/Host、单实例、串行队列、按 ID 控制、暂停/恢复/停止、日志、失败退出码、重试、取消/删除、分页、SSE |
| 旧库备份与恢复状态 | 通过：206 条记录、超出首屏的重排、历史保留、旧运行记录隔离 |
| 真实 API 的浏览器界面检查 | 通过：创建、输入错误、状态更新、日志、历史、删除确认、窄窗口布局 |
| Windows x64 优化版构建 | 通过，Tauri 2 + Rust，内嵌生产 UI |
| Windows 真实 Tauri/WebView2 窗口 | 通过：自动连接、界面操作、中文日志、带空格路径、暂停后输出停止、恢复后继续输出、关闭隐藏且队列继续运行、退出保护、正常退出 |
| Windows PowerShell / CMD / WSL | 通过；WSL 验证了 Linux 进程组的暂停、恢复与停止 |

对最终 `artifacts/PipeDL.exe` 的完整原生检查中，窗口就绪约 **1.4 秒**，停止实验到状态更新约 **237 ms**。这是本机单次检查数据，并非与旧版的受控性能对比，也不代表所有机器或所有实验的延迟。

运行入口、安装包和校验值在 `artifacts/`；截图在 `test-results/windows-desktop.png` 和 `test-results/workspace-completed.png`。可运行检查为 `scripts/smoke.py`、`scripts/ui_check.py`、`scripts/desktop-check.mjs`、`src-tauri/tests/storage.rs`。

验证边界：Linux 核心和浏览器界面已运行，Linux 原生 GTK/WebKit 桌面窗口尚未验证；Windows 独立 Bash 安装未单独验证，Windows 到 WSL 的 Bash 已验证。NSIS 安装包通过构建，未覆盖安装现有应用。当前产物没有代码签名，自动签名更新渠道未启用。

WebView2 在自动化退出时偶尔输出 `Failed to unregister class Chrome_WidgetWin_0 (1412)`；检查中应用正常返回 0，页面没有 JavaScript 异常。该运行时日志未影响本次功能验证。
