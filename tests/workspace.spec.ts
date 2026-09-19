import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("real API: create, event refresh, details, logs, history and validation", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByLabel("API 地址")
    .fill(process.env.PIPEDL_TEST_URL || "http://127.0.0.1:48129");
  await page
    .getByLabel("API Token")
    .fill(
      readFileSync(
        process.env.PIPEDL_TEST_TOKEN || ".test-data/ui/.pipedl/api-token",
        "utf8",
      ).trim(),
    );
  await page.getByRole("button", { name: "连接工作台" }).click();
  await expect(page.getByText("API 已连接")).toBeVisible();
  await expect(page.getByRole("heading", { name: "实验队列." })).toBeVisible();
  const pause = page.getByRole("button", { name: "暂停队列", exact: true });
  if (await pause.isVisible()) await pause.click();
  await expect(
    page.getByRole("button", { name: "恢复队列", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新建实验" }).click();
  await page.getByLabel("实验名称").fill("UI smoke");
  await page.getByLabel("工作目录").fill("relative-invalid");
  await page
    .getByLabel("运行命令")
    .fill(
      process.platform === "win32"
        ? "Write-Output 'ui-log-ok'"
        : "printf 'ui-log-ok\\n'",
    );
  await page.getByRole("button", { name: "加入队列" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "absolute directory",
  );
  await page.getByLabel("工作目录").fill(process.cwd());
  await page.getByRole("button", { name: "加入队列" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "查看 UI smoke" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看 UI smoke" }).click();
  await expect(page.locator(".detail-heading h2")).toHaveText("UI smoke");
  await page.screenshot({
    path: "test-results/workspace-queued.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "恢复队列", exact: true }).click();
  await expect(page.getByLabel("stdout 日志")).toContainText("ui-log-ok", {
    timeout: 15000,
  });
  await page.getByRole("button", { name: "运行历史", exact: true }).click();
  const base = process.env.PIPEDL_TEST_URL || "http://127.0.0.1:48129";
  const headers = {
    Authorization: `Bearer ${readFileSync(process.env.PIPEDL_TEST_TOKEN || ".test-data/ui/.pipedl/api-token", "utf8").trim()}`,
  };
  const failedResponse = await request.post(`${base}/experiments`, {
    headers,
    data: {
      name: "UI failure",
      command: "exit 7",
      cwd: process.cwd(),
      shell: process.platform === "win32" ? "powershell" : "bash",
    },
  });
  const failed = await failedResponse.json();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${base}/experiments/${failed.id}`, { headers })
          ).json()
        ).status,
    )
    .toBe("failed");
  await expect(
    page.locator(".state-succeeded .task-icon .lucide-circle-check"),
  ).toBeVisible();
  await expect(
    page.locator(".state-failed .task-icon .lucide-circle-x"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "查看 UI smoke" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-completed.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "删除所有已完成", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("失败、已停止、已取消");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "保留实验" })
    .click();
  await expect(
    page.getByRole("button", { name: "查看 UI smoke" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "删除所有已完成", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认删除所有已完成" })
    .click();
  await expect(
    page.getByRole("button", { name: "查看 UI smoke" }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "查看 UI failure" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "删除所有已完成", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "删除 UI failure" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "删除实验", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "查看 UI failure" }),
  ).not.toBeVisible();
  await page.setViewportSize({ width: 760, height: 900 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
