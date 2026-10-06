import { test, expect } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-ide-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

async function open(page: import('@playwright/test').Page, request: import('@playwright/test').APIRequestContext, template = 'thermostat') {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  await expect(page.locator('.side.is-open')).toBeVisible({ timeout: 60000 });
  return path;
}

test('资源树：文件、模型对象与诊断都能跳到能编辑它的地方', async ({ page, request }) => {
  await open(page, request);

  // 视图区切换页面
  await page.getByRole('button', { name: '数据流', exact: true }).first().click();
  await expect(page.locator('.blueprint').first()).toBeVisible();

  // 项目文件 → 代码页并打开该文件
  await page.getByRole('button', { name: 'src/logic.c' }).click();
  await expect(page.locator('.monaco-editor')).toBeVisible({ timeout: 120000 });

  // 模型对象 → 对应页面并选中
  await page.getByRole('button', { name: /^温度控制/ }).click();
  await expect(page.locator('[data-flow="control"]')).toBeVisible();
  await page.getByRole('button', { name: '通信', exact: true }).first().click();
  await page.locator('.tree-head', { hasText: '信号（5）' }).click();   // 展开信号分组
  await page.locator('.tree-item[data-tree-id="target"]').click();
  // 名称列是输入框，文字在 value 里，所以断言 data-id 与输入框的值
  await expect(page.locator('tr.is-selected')).toHaveAttribute('data-id', 'target');
  await expect(page.locator('tr.is-selected input').first()).toHaveValue('目标温度');

  // 诊断条目可点
  await page.getByRole('button', { name: '总览', exact: true }).first().click();
  const diag = page.locator('.tree-item.is-diag').first();
  await expect(diag).toBeVisible();
  await diag.click();
  await expect(diag).toBeVisible();   // 跳转后仍在树上可见

  // Ctrl+B 收起成图标条，再展开
  await page.keyboard.press('Control+b');
  await expect(page.locator('.side.is-collapsed')).toBeVisible();
  await page.keyboard.press('Control+b');
  await expect(page.locator('.side.is-open')).toBeVisible();
});

test('命令面板：搜对象并跳转，用键盘选择与执行', async ({ page, request }) => {
  const path = await open(page, request);
  await page.keyboard.press('Control+k');
  const input = page.getByRole('textbox', { name: '命令' });
  await expect(input).toBeFocused();

  await input.fill('温度控制');
  await expect(page.locator('.palette-item')).toHaveCount(1);
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-flow="control"]')).toBeVisible();

  // 源文件命令 → 代码页
  await page.keyboard.press('Control+p');
  await page.getByRole('textbox', { name: '命令' }).fill('board/io.c');
  await page.keyboard.press('Enter');
  await expect(page.locator('.monaco-editor')).toBeVisible({ timeout: 120000 });

  // 无匹配时给出提示，Esc 关闭
  await page.keyboard.press('Control+k');
  await page.getByRole('textbox', { name: '命令' }).fill('zzz-not-a-command');
  await expect(page.locator('.palette-empty')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.palette')).toHaveCount(0);
  void path;
});