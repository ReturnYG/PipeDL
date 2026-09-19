import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests",
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:1420",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    launchOptions: process.env.PIPEDL_BROWSER
      ? { executablePath: process.env.PIPEDL_BROWSER }
      : {},
  },
  webServer: {
    command: "npx vite preview --host 127.0.0.1 --port 1420 --strictPort",
    url: "http://127.0.0.1:1420",
    reuseExistingServer: !process.env.CI,
  },
});
