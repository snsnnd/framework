import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { waitEditorReady } from './helpers';

let root: string;
/** 资源树与代码页都列文件，测试要指明是哪一个。 */
const files = (page: import('@playwright/test').Page) => page.getByRole('complementary', { name: '源码文件' });
test.setTimeout(240000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-code-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

test('模板只读、编辑保存、跨页草稿保留及外部写入冲突保护', async ({ page, request }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  const disk = () => readFile(join(path, 'src/logic.c'), 'utf8');
  const original = await disk();
  const remoteRequests: string[] = [];
  page.on('request', (r) => {
    const url = new URL(r.url());
    if (url.protocol !== 'data:' && url.hostname !== '127.0.0.1') remoteRequests.push(r.url());
  });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await files(page).getByRole('button', { name: 'src/logic.c', exact: true }).click();
  const input = page.locator('.monaco-editor textarea');
  const save = page.getByRole('button', { name: '保存文件', exact: true });
  await waitEditorReady(page, input);

  // 固定结构不可改：文件末尾输入被拦截，不产生草稿
  await page.keyboard.press('Control+End');
  await page.keyboard.press('a');
  await expect(page.getByRole('status')).toContainText('模板结构由工具维护');
  await expect(save).toBeDisabled();

  // 用户逻辑区内可编辑，跨页面保留草稿
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('End');
  await page.keyboard.insertText('  // browser edit');
  await expect(save).toBeEnabled();
  await page.getByRole('button', { name: '通信', exact: true }).click();
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await save.click();
  await expect(page.getByRole('status')).toContainText('已保存');
  const saved = await disk();
  expect(saved).toBe(original.replace('    return EFW_OK;', '    return EFW_OK;  // browser edit'));

  // 外部改写磁盘后再保存：给出冲突，草稿不落盘
  await input.focus();
  await page.keyboard.press('Control+End');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('End');
  await page.keyboard.insertText('  // local draft');
  await writeFile(join(path, 'src/logic.c'), saved + '// external edit\n');
  await save.click();
  await expect(page.locator('.code-page').getByRole('alert')).toContainText('已在外部修改');
  expect(await disk()).not.toContain('// local draft');
  expect(await disk()).toContain('// external edit');
  expect(remoteRequests).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('code-dark.png') });
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '载入磁盘版本', exact: true }).click();
  await expect(save).toBeDisabled();
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('code-light-narrow.png') });
});

test('函数模板进入草稿，保存后替换实现并保持模板保护', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  const read = async (name: string) => (await (await request.post('/rpc', { data: { method: 'file.read', params: { path, name } } })).json());
  await writeFile(join(path, 'src/logic.c'), '#include "app.h"\n');
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await page.getByRole('button', { name: '创建函数模板', exact: true }).click();
  await expect(page.locator('.monaco-editor textarea')).toBeVisible({ timeout: 150000 });
  expect((await read('src/logic.c')).result.content).not.toContain('count_fault');
  await page.getByRole('button', { name: '保存文件', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('补充了函数模板');
  await expect(page.getByText('没有待补充的函数。')).toBeVisible();
  const content = (await read('src/logic.c')).result.content;
  expect(content).toContain('/* EFW USER BEGIN count_fault */');
  expect(content).toContain('/* EFW USER END count_fault */');
  const revision = (await read('src/logic.c')).result.revision;
  const rejected = await request.post('/rpc', { data: { method: 'file.write', params: { path, name: 'src/logic.c', content: content + '// tail\n', rev: revision } } });
  expect((await rejected.json()).error.code).toBe('TEMPLATE');
  await page.getByLabel('新文件路径').fill('src/helper.c');
  await page.getByRole('button', { name: '新建草稿' }).click();
  expect((await read('src/helper.c')).error.code).toBe('NOT_FOUND');
  await page.getByRole('button', { name: '保存文件', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('已保存 src/helper.c');
  expect((await read('src/helper.c')).result.content).toContain('#include "app.h"');
});

test('efw.json 可编辑，保存后其他页面按新模型刷新', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await files(page).getByRole('button', { name: /efw\.json/ }).click();
  const input = page.locator('.monaco-editor textarea');
  const save = page.getByRole('button', { name: '保存文件', exact: true });
  await waitEditorReady(page, input);
  // 整段重写，所以重试是幂等的
  const replace = async (text: string) => {
    for (let i = 0; i < 8; i++) {
      await input.focus();
      await page.keyboard.press('Control+A');
      await page.keyboard.insertText(text);
      if (await save.isEnabled()) return;
      await page.waitForTimeout(400);
    }
    throw new Error('编辑器没有接受输入，草稿始终不是“未保存”');
  };

  await replace('{ bad json');
  await save.click();
  await expect(page.locator('.code-page').getByRole('alert')).toContainText('efw.json 格式错误');
  expect(JSON.parse(await readFile(join(path, 'efw.json'), 'utf8')).flows[0].period_ms).toBe(10);

  const model = JSON.parse(await readFile(join(path, 'efw.json'), 'utf8'));
  model.flows[0].period_ms = 20;
  await replace(JSON.stringify(model, null, 2) + '\n');
  await save.click();
  await expect(page.getByRole('status')).toContainText('已保存 efw.json');
  await page.getByRole('button', { name: '数据流', exact: true }).click();
  await expect(page.getByLabel('control 周期')).toHaveValue('20');
});

test('源码草稿在刷新后仍然存在', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await files(page).getByRole('button', { name: 'src/logic.c', exact: true }).click();
  const input = page.locator('.monaco-editor textarea');
  await waitEditorReady(page, input);
  const before = await readFile(join(path, 'src/logic.c'), 'utf8');

  await input.focus();
  await page.keyboard.press('Control+End');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('End');
  await page.keyboard.insertText('  // 刷新前写的');
  await expect(page.getByRole('button', { name: '保存文件', exact: true })).toBeEnabled();
  // 等防抖的草稿写入
  await expect.poll(async () => page.evaluate((p) => Boolean(localStorage.getItem(`efw.drafts:${p}`)), path)).toBe(true);

  // 刷新：磁盘没变，但草稿回来了
  await page.reload();
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('恢复了未保存草稿', { timeout: 30000 });
  // 文件列表直接标出未保存
  await expect(files(page).getByRole('button', { name: /src\/logic\.c 未保存/ })).toBeVisible();
  await files(page).getByRole('button', { name: /src\/logic\.c/ }).click();
  await expect(page.locator('.monaco-editor .view-lines')).toContainText('刷新前写的', { timeout: 30000 });
  await expect(page.getByRole('button', { name: '保存文件', exact: true })).toBeEnabled();
  expect(await readFile(join(path, 'src/logic.c'), 'utf8')).toBe(before);

  // 保存后草稿从本地存储里消失
  await page.getByRole('button', { name: '保存文件', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('已保存', { timeout: 30000 });
  await expect.poll(async () => page.evaluate((p) => localStorage.getItem(`efw.drafts:${p}`), path)).toBe(null);
  expect(await readFile(join(path, 'src/logic.c'), 'utf8')).toContain('刷新前写的');
});
