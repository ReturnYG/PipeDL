// Run with Windows Node.js. Exercises the real Tauri/WebView2 executable, not a browser mock.
import { chromium } from "playwright";
import { spawn, execFileSync } from "node:child_process";
import { mkdir, readFile, mkdtemp, writeFile } from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const root = await mkdtemp(path.join(process.cwd(), ".test-data", "desktop-"));
const port = 48131,
  debugPort = 9228;
const launchedAt = Date.now();
const app = spawn(path.resolve(process.argv[2]), [], {
  env: {
    ...process.env,
    PIPEDL_ROOT: root,
    PIPEDL_PORT: String(port),
    WEBVIEW2_USER_DATA_FOLDER: path.join(root, "webview"),
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${debugPort}`,
  },
  stdio: ["ignore", "pipe", "pipe"],
});
let output = "";
app.stdout.on("data", (b) => (output += b));
app.stderr.on("data", (b) => (output += b));
let browser, token;
async function api(route, body) {
  const r = await fetch(`http://127.0.0.1:${port}${route}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`${r.status}: ${JSON.stringify(data)}`);
  return data;
}
async function until(fn, timeout = 20000) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    try {
      const result = await fn();
      if (result) return result;
    } catch (e) {
      last = e;
    }
    await pause(100);
  }
  throw last || new Error("Timed out");
}
try {
  await until(async () => {
    if (app.exitCode !== null)
      throw new Error(`App exited ${app.exitCode}: ${output}`);
    token = (
      await readFile(path.join(root, ".pipedl/api-token"), "utf8")
    ).trim();
    return await api("/health");
  });
  browser = await until(() =>
    chromium.connectOverCDP(`http://127.0.0.1:${debugPort}`),
  );
  const page = await until(() =>
    browser
      .contexts()[0]
      ?.pages()
      .find((p) => p.url().includes("tauri.localhost")),
  );
  await page.waitForSelector(".app-shell");
  console.log(`Native window ready: ${Date.now() - launchedAt} ms`);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await api("/queue/pause", {});
  await page.getByRole("button", { name: "新建实验" }).click();
  await page.getByLabel("实验名称").fill("Windows native verification");
  await page.getByLabel("工作目录").fill(process.cwd());
  await page
    .getByLabel("运行命令")
    .fill(
      "Write-Output 'native-webview-ok 中文日志'; 1..300 | ForEach-Object { Write-Output $_; Start-Sleep -Milliseconds 100 }",
    );
  await page.getByRole("button", { name: "加入队列" }).click();
  await page
    .getByRole("button", { name: "查看 Windows native verification" })
    .waitFor();
  await page
    .getByRole("button", { name: "查看 Windows native verification" })
    .click();
  const exp = (await api("/experiments")).experiments[0];
  await page.getByRole("button", { name: "恢复队列", exact: true }).click();
  await until(
    async () => (await api(`/experiments/${exp.id}`)).status === "running",
  );
  await until(async () =>
    (await api(`/experiments/${exp.id}/logs?offset=0`)).text.includes(
      "native-webview-ok",
    ),
  );
  assert(
    (await api(`/experiments/${exp.id}/logs?offset=0`)).text.includes(
      "中文日志",
    ),
    "PowerShell logs must preserve UTF-8",
  );
  await page
    .getByRole("button", { name: "暂停 Windows native verification" })
    .click();
  await until(
    async () => (await api(`/experiments/${exp.id}`)).status === "paused",
  );
  await pause(200);
  const pausedLog = (await api(`/experiments/${exp.id}/logs?offset=0`)).text;
  await pause(350);
  assert.equal(
    (await api(`/experiments/${exp.id}/logs?offset=0`)).text,
    pausedLog,
  );
  // Explicit quit must refuse while an owned task exists.
  await page.getByRole("button", { name: "工作台设置" }).click();
  await page.getByRole("button", { name: "退出应用" }).click();
  await page
    .getByRole("alert")
    .filter({ hasText: "stop it before quitting" })
    .waitFor();
  await page.getByRole("button", { name: "关闭错误" }).click();
  await page
    .getByRole("button", { name: "继续 Windows native verification" })
    .click();
  await until(
    async () => (await api(`/experiments/${exp.id}`)).status === "running",
  );
  await until(
    async () =>
      (await api(`/experiments/${exp.id}/logs?offset=0`)).text.length >
      pausedLog.length,
  );
  await mkdir("test-results", { recursive: true });
  await page.screenshot({
    path: "test-results/windows-desktop.png",
    fullPage: true,
  });
  // Closing the native window must hide it while preserving the queue owner.
  execFileSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      `
        $ErrorActionPreference = 'Stop';
        Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class PipeDLWindowCheck {
      [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
      [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int mode);
    }';
    $p = Get-Process -Id ${app.pid}; $w = $p.MainWindowHandle;
    if ($w -eq 0) { throw 'No native window' };
    if (-not $p.CloseMainWindow()) { throw 'Close request failed' };
    Start-Sleep -Milliseconds 500;
    if ([PipeDLWindowCheck]::IsWindowVisible($w)) { throw 'Window did not hide' };
    [void][PipeDLWindowCheck]::ShowWindow($w, 5);
  `,
    ],
    { timeout: 10000, stdio: "pipe" },
  );
  assert.equal((await api(`/experiments/${exp.id}`)).status, "running");
  const start = Date.now();
  await page
    .getByRole("button", { name: "停止 Windows native verification" })
    .click();
  await until(
    async () => (await api(`/experiments/${exp.id}`)).status === "stopped",
  );
  assert(Date.now() - start < 5000, "native stop took too long");
  console.log(`Native stop and state update: ${Date.now() - start} ms`);
  await api("/queue/pause", {});
  // CMD quoting and filesystem path are checked via the same API.
  const batch = path.join(root, "runner with spaces.cmd");
  await writeFile(batch, "@echo off\r\necho cmd-ok 中文日志\r\n", "utf8");
  const cmd = await api("/experiments", {
    name: "CMD runner",
    command: `call "${batch}"`,
    shell: "cmd",
    cwd: process.cwd(),
  });
  await api("/queue/resume", {});
  await until(
    async () => (await api(`/experiments/${cmd.id}`)).status === "succeeded",
  );
  assert(
    (await api(`/experiments/${cmd.id}/logs?offset=0`)).text.includes(
      "cmd-ok 中文日志",
    ),
  );
  const wslCwd = process.argv[3] || process.env.PIPEDL_TEST_WSL_CWD;
  if (wslCwd) {
    const wsl = await api("/experiments", {
      name: "WSL runner",
      command: "printf 'wsl-ok\\n'; sleep 30",
      shell: "wsl",
      cwd: wslCwd,
    });
    await until(async () =>
      (await api(`/experiments/${wsl.id}/logs?offset=0`)).text.includes(
        "wsl-ok",
      ),
    );
    for (const [action, status] of [
      ["pause", "paused"],
      ["resume", "running"],
      ["stop", "stopped"],
    ]) {
      await api(`/experiments/${wsl.id}/${action}`, {});
      await until(
        async () => (await api(`/experiments/${wsl.id}`)).status === status,
      );
    }
    console.log(
      "PASS: Windows-to-WSL launch, logs, pause/resume and group stop",
    );
  }
  const failure = await api("/experiments", {
    name: "Preserved failure",
    command: "exit 9",
    shell: "powershell",
    cwd: process.cwd(),
  });
  await until(
    async () => (await api(`/experiments/${failure.id}`)).status === "failed",
  );
  await page.getByRole("button", { name: "运行历史", exact: true }).click();
  await page.locator(".state-succeeded").waitFor();
  await page.locator(".state-failed").waitFor();
  await page.screenshot({
    path: "test-results/windows-history.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "删除所有已完成", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "保留实验" })
    .click();
  assert.equal((await api(`/experiments/${cmd.id}`)).status, "succeeded");
  await page
    .getByRole("button", { name: "删除所有已完成", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认删除所有已完成" })
    .click();
  await until(
    async () =>
      !(await api("/experiments")).experiments.some((e) => e.id === cmd.id),
  );
  assert.equal((await api(`/experiments/${failure.id}`)).status, "failed");
  assert.equal((await api(`/experiments/${exp.id}`)).status, "stopped");
  console.log(
    "PASS: distinct success/failure history, cancel and confirm bulk cleanup, failures and stopped records retained",
  );
  assert.deepEqual(errors, []);
  await page.getByRole("button", { name: "工作台设置" }).click();
  await page.getByRole("button", { name: "退出应用" }).click();
  await until(() => app.exitCode !== null);
  assert.equal(app.exitCode, 0);
  console.log(
    "PASS: real Windows Tauri window, bootstrap, WebView2 UI, PowerShell/CMD, UTF-8 logs, quoted paths, pause/resume, close-to-tray, stop, quit protection and clean exit",
  );
} finally {
  if (token && app.exitCode === null) {
    try {
      await api("/queue/pause", {});
      for (const e of (await api("/experiments")).experiments) {
        if (["running", "paused"].includes(e.status))
          await api(`/experiments/${e.id}/stop`, {});
      }
      await pause(1000);
    } catch {}
  }
  if (browser) await browser.close().catch(() => {});
  if (app.exitCode === null) app.kill();
  if (output.trim()) console.log(output.slice(-3000));
}
