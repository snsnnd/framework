import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-gen-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

test('生成页：预览 Diff、提交写入、冲突阻止与恢复', async ({ page, request }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '生成', exact: true }).click();
  await expect(page.getByRole('heading', { name: '生成', exact: true })).toBeVisible();

  const core = page.locator('.generate-files [data-path="app_core.c"]');
  await expect(core).toContainText('新增');
  await core.click();
  await expect(page.locator('.monaco-diff-editor')).toBeVisible({ timeout: 90000 });

  await page.getByRole('button', { name: '提交生成' }).click();
  await expect(page.getByRole('status')).toContainText('已生成');
  expect(await readFile(join(path, 'generated/app_core.c'), 'utf8')).toContain('app_tick');
  expect(JSON.parse(await readFile(join(path, '.efw/generated.json'), 'utf8'))['app_core.c']).toBeTruthy();
  await expect(core).toContainText('未变化');

  await writeFile(join(path, 'generated/app_core.c'), '// hand edit\n');
  await page.getByRole('button', { name: '重新预览' }).click();
  await expect(page.locator('.diag.error')).toContainText('已阻止覆盖');
  await expect(page.getByRole('button', { name: '提交生成' })).toBeDisabled();
  await expect(core).toContainText('冲突');
  await page.screenshot({ path: testInfo.outputPath('generate-dark.png') });

  await rm(join(path, 'generated/app_core.c'));
  await page.getByRole('button', { name: '重新预览' }).click();
  await expect(core).toContainText('新增');
  await expect(page.getByRole('button', { name: '提交生成' })).toBeEnabled();

  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('generate-light-narrow.png') });
});
