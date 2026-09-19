# Development

The queue worker thread exclusively owns SQLite and processes. Axum handlers dispatch commands to it off the async/UI threads. Mutations emit SSE invalidations. The frontend refetches only on events/actions; log reads use offsets every 500 ms for the selected active task, with a 200,000-character display cap. Idle/hidden log views do not repeatedly read files. The worker checks owned process completion every 100 ms; idle queues block on commands rather than polling SQLite.

## Workspace-local tools

```bash
source scripts/env.sh
cargo test --manifest-path src-tauri/Cargo.toml --no-default-features
cargo build --manifest-path src-tauri/Cargo.toml --no-default-features
python3 scripts/smoke.py src-tauri/target/debug/pipedl
npm run build
```

On this Ubuntu 20.04 workspace, `.tools/ubuntu` supplies Ubuntu 24.04 GTK/WebKit/LLVM through `.tools/proot` without system installation (the Windows cross-build uses local LLVM wrappers to avoid filesystem translation overhead):

```bash
source scripts/env.sh
bash scripts/in-ubuntu.sh env CARGO_HOME="$CARGO_HOME" RUSTUP_HOME="$RUSTUP_HOME" PATH="$CARGO_HOME/bin:/usr/bin:/bin" cargo build --manifest-path src-tauri/Cargo.toml
```

Tool setup/downloads are local, ignored by git, and disposable. Normal supported Ubuntu/Windows machines can use native build tools instead.

## Browser integration checks

Start the headless binary in a terminal with `PIPEDL_ROOT=$PWD/.test-data/ui PIPEDL_PORT=48129`. Then:

```bash
export PIPEDL_TEST_URL=http://127.0.0.1:48129
export PIPEDL_TEST_TOKEN=.test-data/ui/.pipedl/api-token
# Older workspace only, after local Chromium download:
export PIPEDL_BROWSER=$PWD/scripts/chromium-local.sh
npm run test:ui
```

The UI check uses the actual Rust API; it verifies validation, submission, event refresh, logs, history, deletion and narrow layout. Screenshots go to test-results. Use a disposable queue, never a live profile. The API smoke script independently starts and tears down its own temporary instance.

## Process ownership

Normal Windows descendants belong to a kill-on-close Job Object. POSIX tasks have separate process groups. A workload that deliberately escapes its group/job is outside this queue contract. WSL uses setsid inside the distribution, not a Windows process-tree assumption. Pause/resume failures retain the old database state. Backend crash recovery is conservative: quarantine rather than pretend to reattach.

Keep UI logic out of the worker, and process/DB logic out of Tauri commands. Tauri IPC is limited to bootstrap credentials and desktop lifecycle; all experiment operations use HTTP.

Logs use UTF-8. PowerShell output encoding and CMD's code page are set at launch; Python receives `PYTHONIOENCODING=utf-8` and `PYTHONUNBUFFERED=1` (including WSL). Commands may explicitly override their own environment. Programs that insist on a different binary/text encoding need to convert output before writing to these text logs.

## Windows cross-build in this workspace

The Windows SDK/CRT was downloaded by cargo-xwin to `.tools/xwin`; LLVM is in the local Ubuntu sysroot. The wrappers in `.tools/llvm-bin` invoke those binaries through the local loader without changing host libraries.

```bash
source scripts/env.sh
PATH="$PWD/.tools/llvm-bin:$PATH" XWIN_CACHE_DIR="$PWD/.tools/xwin" CARGO_TARGET_DIR="$PWD/.tools/target-windows" cargo xwin build --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-msvc --features custom-protocol
```

`custom-protocol` embeds the production Web UI instead of depending on the Vite development server. Run `npm run build` first. Native Windows builds via the Tauri CLI enable it automatically.

`desktop-check.mjs` is a Windows-only real-window check using WebView2's temporary debug port and Windows Node.js. It runs in a disposable root and closes the app afterwards. The test does not enable remote debugging in normal application launches.

In this workspace, `bash scripts/build_local_windows.sh` builds and packages with the locally installed toolchain and copies deliverables to `artifacts/`. It expects the downloaded `.tools` contents; a fresh machine should use the native prerequisites and normal Tauri build instead.

```bash
.tools/node-v22.22.0-win-x64/node.exe scripts/desktop-check.mjs 'D:\Develop\PipeDL\artifacts\PipeDL.exe' /mnt/d/Develop/PipeDL
```

The optional final argument enables the Windows-to-WSL runner check using that Linux working directory.
