import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-console-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

test('遥控台：打字控制目标，有回显、历史和补全', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  const run = page.getByRole('button', { name: '运行', exact: true });
  await run.click();
  await expect(page.getByText('运行中')).toBeVisible({ timeout: 40000 });
  await page.waitForTimeout(1200);

  const input = page.getByLabel('遥控台命令');
  // 打字 → 发送 → 回显里有命令本身和目标回执
  await input.fill('set target 70');
  await input.press('Enter');
  await expect(page.locator('.console-line.is-sent')).toContainText('> set target 70');
  await expect(page.locator('.console-line.is-ack').first()).toContainText('set 已生效', { timeout: 20000 });
  await expect.poll(async () => JSON.parse(await readFile(join(path, 'efw.json'), 'utf8'))).toBeTruthy();

  // 触发事件：回显里能看到状态切换
  await input.fill('fire overheat');
  await input.press('Enter');
  await expect(page.locator('.console-line.is-event').first()).toContainText('状态切换', { timeout: 20000 });

  // 上限保护：乱敲一条非法命令，被后端拒绝并显示原因
  await input.fill('rm -rf /');
  await input.press('Enter');
  await expect(page.locator('.console-line.is-err').first()).toContainText('不允许的调试命令', { timeout: 20000 });

  // Tab 补全：dump ← du
  await input.fill('du');
  await input.press('Tab');
  await expect(input).toHaveValue('dump ');

  // ↑ 翻出上一条命令
  await input.fill('');
  await input.press('ArrowUp');
  await expect(input).toHaveValue('rm -rf /');

  // 快捷命令按当前项目的真实 key / 事件生成，点了直接填进输入框
  await expect(page.locator('.console-help')).toContainText('dump');
  await expect(page.locator('.console-help')).toContainText('set target ');
  await expect(page.locator('.console-help')).toContainText('fire overheat');
  await expect(page.locator('.console-help')).toContainText('force sensor ');
  await page.locator('.console-chip', { hasText: 'fire overheat' }).click();
  await expect(input).toHaveValue('fire overheat');
});
