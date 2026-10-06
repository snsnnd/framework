import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-repair-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

/** 在磁盘上改模型；模拟用户手改文件后重新载入。 */
async function patch(path: string, patch: (m: Record<string, any>) => void) {
  const file = join(path, 'efw.json');
  const m = JSON.parse(await readFile(file, 'utf8'));
  patch(m);
  await writeFile(file, JSON.stringify(m, null, 2) + '\n');
}

async function create(path: string, request: { post: (url: string, opts: unknown) => Promise<unknown> }) {
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
}

test('总览页“下一步”跳到通信页并选中出问题的信号', async ({ page, request }) => {
  const path = join(root, 'app');
  await create(path, request);
  await patch(path, (m) => { m.signals.push({ id: 'orphan', label: '没人用', type: 'float', init: 0, unit: '', tune: null }); });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  const entry = page.getByRole('button', { name: /信号“orphan”还没有被使用/ });
  await expect(entry).toContainText('去通信页 · 信号 orphan');
  await entry.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.comm-toolbar')).toBeVisible();
  await expect(page.locator('.comm-categories').getByRole('button', { name: /^信号 / })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('tr[data-id="orphan"]')).toHaveClass(/is-selected/);
});

test('总览页“下一步”跳到数据流、状态机与代码页', async ({ page, request }) => {
  const path = join(root, 'app');
  await create(path, request);
  await patch(path, (m) => {
    m.tick_ms = 2;
    m.flows[0].period_ms = 3;
    m.flows[0].steps.push({ id: 'work', kind: 'custom', call: 'do_work', reads: [], writes: [] });
    m.machines[0].states[0].run = ['ghost'];
  });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  const overview = () => page.getByRole('button', { name: '总览', exact: true });
  // 模型有错时，两条错误诊断 + 一条缺失函数，各自都能跳
  await expect(page.locator('.diag.repair')).toHaveCount(3);

  await page.getByRole('button', { name: /周期 3ms 不是节拍/ }).click();
  const card = page.locator('[data-flow="control"]');
  await expect(card).toBeVisible();
  await expect(card).toBeInViewport();

  await overview().click();
  await page.getByRole('button', { name: /run 必须是已有数据流/ }).click();
  const state = page.locator('.machine-state', { hasText: 'running' });
  await expect(state).toHaveAttribute('aria-pressed', 'true');

  await overview().click();
  await page.getByRole('button', { name: /缺少函数 do_work/ }).click();
  await expect(page.locator('.monaco-editor')).toBeVisible();
  await expect(page.locator('.code-page header .id')).toHaveText('src/logic.c');
  await expect(page.getByText('do_work')).toBeVisible();
});

