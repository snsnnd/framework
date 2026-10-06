import { test, expect } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-note-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

test('通信页解释信号与事件、常量的区别；步骤字段说明常量与信号', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  await page.getByRole('button', { name: '通信', exact: true }).click();

  const note = page.locator('.comm-note').first();
  await expect(note).toContainText('它不是常量');
  await expect(note).toContainText('运行期的值');

  await page.getByRole('button', { name: /^事件 / }).click();
  await expect(note).toContainText('不带数值');
  await expect(note).toContainText('触发状态机切换');

  await page.getByRole('button', { name: /^输入 / }).click();
  await expect(note).toContainText('board/io.c');
  await expect(page.locator('.comm-note code').first()).toHaveText('board/io.c');
  await expect(page.locator('.comm-note code').filter({ hasText: '_read()' })).toBeVisible();

  // 步骤字段：信号字段与常量字段的提示来自后端 step_specs
  await page.getByRole('button', { name: '数据流', exact: true }).click();
  await page.locator('.step-row[data-id="pid"]').click();
  await expect(page.locator('.field-hint').first()).toContainText('信号是运行期的共享值');
  await expect(page.locator('.field-hint').filter({ hasText: '常量' }).first()).toBeVisible();

  await page.locator('.step-row[data-id="guard"]').click();
  await expect(page.locator('.field-hint').first()).toContainText('事件不带数值');
});
