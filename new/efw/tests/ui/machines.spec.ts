import { test, expect } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { Opened } from '../../ui/types';

let root: string;
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-ui-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

for (const colorScheme of ['dark', 'light'] as const) {
  test(`状态详情与转换规则 · ${colorScheme}`, async ({ page, request }, testInfo) => {
    const path = join(root, 'thermostat');
    const response = await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
    expect((await response.json()).error).toBeUndefined();
    await page.emulateMedia({ colorScheme });
    await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
    await page.goto('/');
    await page.getByRole('button', { name: '状态机', exact: true }).click();
    await expect(page.getByRole('heading', { name: '状态机', exact: true })).toBeVisible();
    const details = page.getByRole('region', { name: '状态详情' });
    await expect(details).toContainText('温度控制');
    const fault = page.getByRole('button', { name: '过热保护 fault', exact: true });
    await fault.focus();
    await page.keyboard.press('Enter');
    await expect(fault).toHaveAttribute('aria-pressed', 'true');
    await expect(details).toContainText('强制冷却');
    await expect(details).toContainText('count_fault()');
    const recover = page.getByRole('button', { name: /recover$/ });
    await recover.click();
    await expect(recover).toHaveAttribute('aria-pressed', 'true');
    await expect(details).toContainText('温度控制');
    await expect(page.locator('.machine-edge.is-selected')).toHaveCount(1);
    expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`machines-${colorScheme}.png`), fullPage: true });
    await page.setViewportSize({ width: 768, height: 900 });
    expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`machines-${colorScheme}-narrow.png`), fullPage: true });
  });
}

test('空项目与多状态机，条件、任意来源、自转换和声明顺序', async ({ page, request }) => {
  const path = join(root, 'blank');
  const response = await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '空白项目', template: 'blank' } } });
  const { result: opened } = await response.json() as { result: Opened };
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '状态机', exact: true }).click();
  await expect(page.getByText(/还没有状态机。/)).toBeVisible();
  opened.model.signals = [{ id: 'temp', label: '温度', type: 'float', init: 20, unit: '°C', tune: null }];
  opened.model.machines = [
    { id: 'mode', label: '模式', initial: 'idle', states: [
      { id: 'idle', label: '空闲', run: [], set: { temp: 0 } },
      { id: 'alarm', label: '报警', run: [], set: {} },
    ], transitions: [
      { id: 'hot', from: '*', to: 'alarm', on: { signal: 'temp', op: '>', value: 75 } },
      { id: 'hold', from: 'idle', to: 'idle', on: { call: 'keep_idle' } },
    ] },
    { id: 'other', label: '另一个模式', initial: 'ready', states: [{ id: 'ready', label: '就绪', run: [], set: {} }], transitions: [] },
  ];
  const saved = await request.post('/rpc', { data: { method: 'project.save', params: { path, model: opened.model, layout: opened.layout, rev: opened.revision } } });
  expect((await saved.json()).error).toBeUndefined();
  await page.getByRole('button', { name: '重新载入' }).click();
  await expect(page.locator('.machine-rule')).toHaveCount(2);
  await expect(page.locator('.machine-rule').nth(0)).toContainText('当 温度 > 75 时，从 任意状态 到 报警');
  await expect(page.locator('.machine-rule').nth(1)).toContainText('keep_idle() 返回真');
  await expect(page.locator('.machine-edge')).toHaveCount(2);
  await page.getByLabel('状态机', { exact: true }).selectOption('other');
  await expect(page.getByText('还没有转换规则。应用将保持在初始状态。')).toBeVisible();
  await page.getByLabel('状态机', { exact: true }).selectOption('mode');
  await expect(page.getByRole('region', { name: '状态详情' })).toContainText('temp = 0');
});
