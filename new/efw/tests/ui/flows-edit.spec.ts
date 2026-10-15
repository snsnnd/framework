import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-flow-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

const model = async (path: string) => JSON.parse(await readFile(join(path, 'efw.json'), 'utf8'));
const step = async (path: string, flowId: string, stepId: string) =>
  (await model(path)).flows.find((f: { id: string }) => f.id === flowId).steps.find((s: { id: string }) => s.id === stepId);

test('数据流页：改周期、编辑步骤字段、排序与增删步骤', async ({ page, request }, testInfo) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '数据流', exact: true }).click();

  // 改周期：必须是节拍 1ms 的整数倍（模板都是 1ms，所以任意正整数都合法）
  const period = page.getByLabel('control 周期');
  await period.fill('20');
  await period.press('Enter');
  await expect.poll(async () => (await model(path)).flows[0].period_ms).toBe(20);
  await expect(period).toHaveValue('20');

  // 展开低通滤波步骤，改 alpha
  await page.locator('.step-row[data-id="filter"]').click();
  const alpha = page.getByLabel('filter alpha');
  await expect(alpha).toHaveValue('0.2');
  await alpha.fill('0.4');
  await alpha.press('Enter');
  await expect.poll(async () => (await step(path, 'control', 'filter')).alpha).toBe(0.4);

  // 改 PID 的目标信号与参数
  await page.locator('.step-row[data-id="pid"]').click();
  await page.getByLabel('pid kp').fill('0.12');
  await page.getByLabel('pid kp').press('Enter');
  await expect.poll(async () => (await step(path, 'control', 'pid')).kp).toBe(0.12);
  await page.getByLabel('pid 写入信号').selectOption('duty');
  await page.getByLabel('pid 读取信号').first().selectOption('temp');
  await expect.poll(async () => (await step(path, 'control', 'pid')).setpoint).toBe('temp');

  // 上移 / 下移：把最后一个步骤往前挪一位
  const orderBefore = (await model(path)).flows[0].steps.map((s: { id: string }) => s.id);
  await page.locator('.step-row[data-id="drive"] [aria-label="control drive 上移"]').click();
  await expect.poll(async () => (await model(path)).flows[0].steps.map((s: { id: string }) => s.id))
    .toEqual([...orderBefore.slice(0, 3), 'drive', orderBefore[3]]);
  await page.locator('.step-row[data-id="drive"] [aria-label="control drive 下移"]').click();
  await expect.poll(async () => (await model(path)).flows[0].steps.map((s: { id: string }) => s.id)).toEqual(orderBefore);

  // 添加限幅步骤（引用字段已预填为第一个信号），再改成 duty 并配置范围
  await page.locator('section[aria-label="数据流 control"] > header').getByRole('button', { name: '添加步骤' }).click();
  await page.getByLabel('新步骤类型').selectOption('clamp');
  await page.getByRole('button', { name: '添加', exact: true }).click();
  await expect.poll(async () => (await model(path)).flows[0].steps.length).toBe(6);
  const clamp = (await model(path)).flows[0].steps.at(-1);
  expect(clamp.kind).toBe('clamp');
  await page.locator(`.step-row[data-id="${clamp.id}"]`).click();
  await page.getByLabel(`${clamp.id} 读取信号`).selectOption('duty');
  await expect.poll(async () => (await step(path, 'control', clamp.id)).from).toBe('duty');
  await page.getByLabel(`${clamp.id} 写入信号`).selectOption('duty');
  await expect.poll(async () => (await step(path, 'control', clamp.id)).to).toBe('duty');
  await page.getByLabel(`${clamp.id} max`).fill('1');
  await page.getByLabel(`${clamp.id} max`).press('Enter');
  await expect.poll(async () => (await step(path, 'control', clamp.id)).max).toBe(1);

  // 删除该步骤
  await page.locator(`.step-row[data-id="${clamp.id}"] [aria-label="control ${clamp.id} 删除"]`).click();
  await expect.poll(async () => (await model(path)).flows[0].steps.length).toBe(5);

  await page.screenshot({ path: testInfo.outputPath('flows-edit-dark.png') });
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('flows-edit-light.png') });
});

test('数据流页：新增与删除数据流，受状态机控制的不给删', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '数据流', exact: true }).click();

  await page.getByRole('button', { name: '新增数据流' }).click();
  await page.getByLabel('新数据流名称').fill('记录');
  await page.getByLabel('新数据流标识符').fill('log');
  await page.getByRole('button', { name: '添加', exact: true }).click();
  await expect.poll(async () => (await model(path)).flows.length).toBe(3);
  await expect(page.locator('section[aria-label="数据流 log"]')).toBeVisible();

  // 总览时间线立刻多出一条泳道
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await expect(page.locator('.timeline-lane:not(.is-system)')).toHaveCount(3);
  await expect(page.locator('.timeline-lane:not(.is-system)').last()).toContainText('记录');
  await page.getByRole('button', { name: '数据流', exact: true }).click();

  // 被状态机 mode 控制的 control 不能删除
  await page.locator('section[aria-label="数据流 control"] > header').getByRole('button', { name: '删除', exact: true }).click();
  await expect(page.locator('.diag.error')).toContainText('由状态机 mode 控制');
  expect((await model(path)).flows.some((f: { id: string }) => f.id === 'control')).toBe(true);

  // 未被控制的新数据流可以删除
  await page.locator('section[aria-label="数据流 log"] > header').getByRole('button', { name: '删除', exact: true }).click();
  await expect.poll(async () => (await model(path)).flows.some((f: { id: string }) => f.id === 'log')).toBe(false);

  // 总览的整机时间线随之更新
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await expect(page.locator('.timeline-lane:not(.is-system)')).toHaveCount(2);   // 只剩 control 与 cooldown
  await expect(page.locator('.timeline-lane:not(.is-system)').first()).toContainText('温度控制');
});