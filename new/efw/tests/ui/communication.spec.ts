import { test, expect } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-comm-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

for (const colorScheme of ['dark', 'light'] as const) {
  test(`信号关系、搜索与事件队列 · ${colorScheme}`, async ({ page, request }, testInfo) => {
    const path = join(root, 'app');
    const res = await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
    expect((await res.json()).error).toBeUndefined();
    await page.emulateMedia({ colorScheme });
    await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
    await page.goto('/');
    await page.getByRole('button', { name: '通信', exact: true }).click();
    await expect(page.getByRole('heading', { name: '通信', exact: true })).toBeVisible();
    await page.getByRole('button', { name: '加热占空比 duty' }).click();
    const details = page.getByRole('region', { name: '通信详情' });
    await expect(details).toContainText('control / pid');
    await expect(details).toContainText('cooldown / off');
    await expect(details).toContainText('被多个地方写入');
    await page.getByLabel('查找').fill('target');
    await expect(page.locator('.comm-table tbody tr')).toHaveCount(1);
    await expect(page.locator('.comm-table')).toContainText('20 ～ 90');
    await page.getByLabel('查找').fill('不存在');
    await expect(page.getByText('没有匹配的信号。')).toBeVisible();
    await page.getByRole('button', { name: '清除搜索' }).click();
    await page.getByRole('button', { name: '温度 temp', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(details).toContainText('control / filter');
    await page.screenshot({ path: testInfo.outputPath(`communication-${colorScheme}.png`) });
    await page.getByRole('button', { name: '事件 1', exact: true }).click();
    await expect(page.getByText(/配置容量 8 条/)).toBeVisible();
    await expect(details).toContainText('control / guard');
    await expect(details).toContainText('mode / trip');
    await page.setViewportSize({ width: 768, height: 900 });
    expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`communication-${colorScheme}-narrow.png`) });
    await page.getByRole('button', { name: '队列 0', exact: true }).click();
    await expect(page.getByText(/还没有队列。/)).toBeVisible();
  });
}

test('采样队列显示容量、溢出策略与后端内存合计', async ({ page, request }) => {
  const path = join(root, 'sampler');
  const res = await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '采样', template: 'sampler' } } });
  const { result } = await res.json();
  const analysis = await request.post('/rpc', { data: { method: 'project.analyze', params: { path, model: result.model } } });
  const bytes = (await analysis.json()).result.memory.parts.find((p: { name: string }) => p.name === '用户队列').bytes;
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '通信', exact: true }).click();
  await page.getByRole('button', { name: '队列 1', exact: true }).click();
  await expect(page.locator('.comm-table')).toContainText('uint16_t');
  await expect(page.locator('.comm-table')).toContainText('16');
  await expect(page.locator('.comm-table')).toContainText('丢弃最旧');
  await expect(page.getByText(`用户队列内存估算 ${bytes} B · 全部队列`)).toBeVisible();
  await expect(page.getByRole('region', { name: '通信详情' })).toContainText('未提供队列的生产者');
});
