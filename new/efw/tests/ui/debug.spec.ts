import { test, expect } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-debug-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

test('虚拟目标：草稿门禁、运行暂停单步、整定、事件、停止与回放', async ({ page, request }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');

  // 未保存草稿时禁止运行，保存后恢复
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await page.getByLabel('新文件路径').fill('src/pending.c');
  await page.getByRole('button', { name: '新建草稿' }).click();
  const run = page.getByRole('button', { name: '运行', exact: true });
  await expect(run).toBeDisabled();
  await expect(page.locator('.monaco-editor textarea')).toBeVisible({ timeout: 120000 });
  await page.getByRole('button', { name: '保存文件', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('已保存', { timeout: 30000 });
  await expect(run).toBeEnabled();

  // 启动虚拟目标
  await run.click();
  await expect(page.getByRole('heading', { name: '调试', exact: true })).toBeVisible();
  await expect(page.getByText('运行中')).toBeVisible({ timeout: 30000 });
  const clock = page.locator('.debug-t .id');
  await expect.poll(async () => Number(await clock.innerText()), { timeout: 30000 }).toBeGreaterThan(150);

  // 暂停后时间不再前进；单步推进
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(page.getByText('已暂停')).toBeVisible();
  await page.waitForTimeout(400);
  const paused = Number(await clock.innerText());
  await page.waitForTimeout(700);
  expect(Number(await clock.innerText())).toBe(paused);
  await page.getByRole('button', { name: '单步', exact: true }).click();
  await expect.poll(async () => Number(await clock.innerText()), { timeout: 10000 }).toBeGreaterThan(paused);
  await page.getByRole('button', { name: '播放', exact: true }).click();
  await expect(page.getByText('运行中')).toBeVisible();

  // 曲线、任务、状态机（按模型 id 定位，不依赖展示文案）
  await expect(page.locator('.chart-legend [data-id="temp_raw"]')).toContainText('原始温度');
  await expect(page.locator('.tasks tr[data-id="control"]')).toContainText('温度控制');
  await expect(page.locator('.debug-machines [data-id="mode"]')).toContainText('正常控制');

  // 整定：按稳定 id 选中 target，确认命令往返（ack）与回显
  const target = page.locator('.tuner[data-key="target"] input[type="number"]');
  await target.fill('45');
  await target.blur();
  await expect(page.locator('.debug-ack')).toContainText('目标已确认', { timeout: 10000 });
  await expect(page.locator('.debug-ack')).toContainText('set');
  await expect(target).toHaveValue('45');

  // 触发事件进入过热保护
  await page.locator('.debug-event[data-id="overheat"]').getByRole('button', { name: '触发' }).click();
  await expect(page.locator('.debug-machines [data-id="mode"]')).toContainText('过热保护', { timeout: 10000 });
  await page.screenshot({ path: testInfo.outputPath('debug-dark.png') });

  // 停止后出现录制列表
  await page.getByRole('region', { name: '调试控制' }).getByRole('button', { name: '停止' }).click();
  await expect(page.getByText('已停止')).toBeVisible();
  await expect(page.locator('.debug-start select option')).not.toHaveCount(0);

  // 最快速度回放
  await page.getByRole('button', { name: '启动回放' }).click();
  await expect(page.getByText(/回放中不能发送命令/)).toBeVisible({ timeout: 20000 });
  await page.getByLabel('仿真速度').selectOption('0');
  await expect(page.locator('.debug-message')).toContainText('回放结束', { timeout: 60000 });

  // 亮色窄窗口
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('debug-light-narrow.png') });
});
