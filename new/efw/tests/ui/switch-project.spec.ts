import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-switch-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

const exists = async (path: string) => readFile(join(path, 'efw.json'), 'utf8').then(() => true, () => false);
/** 只在首次加载时种 lastProject：addInitScript 每次导航都跑，reload 不能再种一次。 */
const seed = (page: import('@playwright/test').Page, path: string) => page.addInitScript((p) => {
  if (sessionStorage.getItem('efw.testSeeded')) return;
  sessionStorage.setItem('efw.testSeeded', '1');
  localStorage.setItem('efw.lastProject', p);
}, path);

test('打开项目后能切换：顶栏按钮回到欢迎页，最近项目可一键打开', async ({ page, request }) => {
  const first = join(root, 'heater');
  const second = join(root, 'signal');
  await request.post('/rpc', { data: { method: 'project.create', params: { path: first, name: '恒温控制', template: 'thermostat' } } });
  await request.post('/rpc', { data: { method: 'project.create', params: { path: second, name: '信号灯', template: 'traffic' } } });
  await seed(page, first);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '恒温控制' })).toBeVisible({ timeout: 60000 });

  // 切回欢迎页；刚打开过的项目进了"最近打开"
  await page.getByRole('button', { name: '切换项目' }).click();
  await expect(page.getByRole('heading', { name: 'EFW Studio' })).toBeVisible();
  await expect(page.locator('.recent-item')).toHaveCount(1);

  // 用路径打开另一个项目
  await page.getByLabel('项目目录').fill(second);
  await page.getByRole('button', { name: '打开已有' }).click();
  await expect(page.getByRole('heading', { name: '信号灯' })).toBeVisible({ timeout: 60000 });
  expect(await exists(second)).toBe(true);

  // 再切回来，两个项目都在最近列表里，点第一个即可回到它
  await page.getByRole('button', { name: '切换项目' }).click();
  await expect.poll(async () => page.locator('.recent-item').count()).toBe(2);
  await page.locator('.recent-item').filter({ hasText: '恒温控制' }).click();
  await expect(page.getByRole('heading', { name: '恒温控制' })).toBeVisible({ timeout: 60000 });
});

test('切换项目会清掉 lastProject 与撤销历史，也能从命令面板切换', async ({ page, request }) => {
  const first = join(root, 'a');
  const second = join(root, 'b');
  for (const [path, name] of [[first, '甲'], [second, '乙']] as const) {
    await request.post('/rpc', { data: { method: 'project.create', params: { path, name, template: 'blank' } } });
  }
  await seed(page, first);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '甲' })).toBeVisible({ timeout: 60000 });

  // 改一次模型，撤销按钮才可用
  await page.getByRole('button', { name: '通信', exact: true }).first().click();
  await page.locator('.comm-categories').getByRole('button', { name: /^信号 / }).click();
  await page.getByRole('button', { name: '新增信号' }).click();
  await page.getByLabel('新名称').fill('测试信号');
  await page.getByLabel('新标识符').fill('probe_sig');
  await page.getByRole('button', { name: '添加', exact: true }).click();
  await expect(page.getByRole('button', { name: '撤销' })).toBeEnabled();

  // 命令面板里也能切换
  await page.keyboard.press('Control+k');
  await page.getByRole('textbox', { name: '命令' }).fill('切换项目');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'EFW Studio' })).toBeVisible();
  await expect(page.getByRole('button', { name: '撤销' })).toHaveCount(0);

  // 刷新不会又自动打开旧项目
  await page.reload();
  await expect(page.getByRole('heading', { name: 'EFW Studio' })).toBeVisible({ timeout: 30000 });

  // 刷新后从最近列表打开（乙只是建了、没打开过，不该出现在列表里）
  await expect(page.locator('.recent-item')).toHaveCount(1);
  await page.locator('.recent-item').filter({ hasText: '甲' }).click();
  await expect(page.getByRole('heading', { name: '甲' })).toBeVisible({ timeout: 60000 });
  await expect(page.getByRole('button', { name: '撤销' })).toBeDisabled();
});

test('最近项目可以移除', async ({ page, request }) => {
  const path = join(root, 'only');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '独苗', template: 'blank' } } });
  await seed(page, path);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '独苗' })).toBeVisible({ timeout: 60000 });
  await page.getByRole('button', { name: '切换项目' }).click();
  await expect(page.locator('.recent-item')).toHaveCount(1);
  await page.getByRole('button', { name: '忘记 独苗' }).click();
  await expect(page.locator('.recent-item')).toHaveCount(0);
});