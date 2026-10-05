import { defineConfig } from '@playwright/test';

// 测试用独立端口（5174），避免与开发者手动启动的 5173 开发服务器冲突。
const port = Number(process.env.EFW_TEST_PORT ?? 5174);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests/ui',
  workers: 1,
  use: { baseURL, viewport: { width: 1366, height: 768 } },
  // 每次保存都要经过 Python 服务（校验 + 写盘），机器负载高时 5 秒不够用。
  // expect.poll 会继承这个超时，所以轮询模型文件的断言也一起放宽。
  expect: { timeout: 20000 },
  webServer: {
    command: `${JSON.stringify(process.execPath)} node_modules/vite/bin/vite.js --port ${port} --strictPort`,
    url: baseURL,
    timeout: 120000,
    reuseExistingServer: false,
  },
});