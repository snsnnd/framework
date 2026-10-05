import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-mach-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

const model = async (path: string) => JSON.parse(await readFile(join(path, 'efw.json'), 'utf8'));
const machine = async (path: string, id = 'mode') => (await model(path)).machines.find((m: { id: string }) => m.id === id);

test('状态机页：编辑状态、run、set、钩子与初始状态', async ({ page, request }, testInfo) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '状态机', exact: true }).click();

  // 改状态名称
  const label = page.getByLabel('running 名称');
  await label.fill('正常控温');
  await label.press('Enter');
  await expect.poll(async () => (await machine(path)).states.find((s: { id: string }) => s.id === 'running').label).toBe('正常控温');

  // run：勾选数据流
  await page.getByLabel('mode running 运行 cooldown').click();
  await expect.poll(async () => (await machine(path)).states.find((s: { id: string }) => s.id === 'running').run).toEqual(['control', 'cooldown']);
  await page.getByLabel('mode running 运行 control').click();
  await expect.poll(async () => (await machine(path)).states.find((s: { id: string }) => s.id === 'running').run).toEqual(['cooldown']);

  // set：新增一条信号设置并修改
  await page.getByRole('button', { name: '添加设置' }).click();
  await expect.poll(async () => Object.keys((await machine(path)).states.find((s: { id: string }) => s.id === 'running').set)).toContain('temp_raw');
  await expect(page.getByLabel('running 设置 temp_raw')).toHaveValue('20');   // 等新增落盘、输入框可编辑
  await page.getByLabel('running 设置 temp_raw').fill('5');
  await page.getByLabel('running 设置 temp_raw').press('Enter');
  await expect.poll(async () => (await machine(path)).states.find((s: { id: string }) => s.id === 'running').set.temp_raw).toBe(5);
  await page.getByLabel('running 取消设置 temp_raw').click();
  await expect.poll(async () => Object.keys((await machine(path)).states.find((s: { id: string }) => s.id === 'running').set)).not.toContain('temp_raw');

  // 钩子
  await page.getByLabel('running on_exit').fill('log_exit');
  await page.getByLabel('running on_exit').press('Enter');
  await expect.poll(async () => (await machine(path)).states.find((s: { id: string }) => s.id === 'running').on_exit).toBe('log_exit');
  // 非法函数名会被拒绝并回滚
  await page.getByLabel('running on_exit').fill('9bad');
  await page.getByLabel('running on_exit').press('Enter');
  await expect(page.getByLabel('running on_exit')).toHaveValue('log_exit');   // 被拒绝后回滚
  expect((await machine(path)).states.find((s: { id: string }) => s.id === 'running').on_exit).toBe('log_exit');

  // 新增状态并设为初始
  await page.getByRole('button', { name: '新增状态' }).click();
  await page.getByLabel('新状态名称').fill('待机');
  await expect(page.getByLabel('新状态名称')).toHaveValue('待机');
  await page.getByLabel('新状态标识符').fill('standby');
  await expect(page.getByLabel('新状态标识符')).toHaveValue('standby');
  await page.getByRole('button', { name: '添加', exact: true }).click();
  await expect.poll(async () => (await machine(path)).states.length).toBe(3);
  await expect(page.locator('.machine-state', { hasText: '待机' })).toBeVisible();
  await page.getByRole('button', { name: '设为初始' }).click();
  await expect.poll(async () => (await machine(path)).initial).toBe('standby');

  // 被转换引用的状态不能删；没有转换的状态可以删
  await page.locator('.machine-state', { hasText: '正常控温' }).click();
  await page.getByRole('button', { name: '删除', exact: true }).click();
  await expect(page.locator('.machine-rules .err-text').first()).toContainText('仍在转换规则里');
  expect((await machine(path)).states.some((s: { id: string }) => s.id === 'running')).toBe(true);
  await page.locator('.machine-state', { hasText: '待机' }).click();
  await page.getByRole('button', { name: '删除', exact: true }).click();
  await expect.poll(async () => (await machine(path)).states.length).toBe(2);
  await expect(page.locator('.machine-rules .err-text')).toHaveCount(0);

  await page.screenshot({ path: testInfo.outputPath('machines-edit-dark.png') });
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('machines-edit-light.png') });
});

test('状态机页：新增与编辑转换规则（事件 / 超时 / 信号 / 函数）', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '信号灯', template: 'traffic' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '状态机', exact: true }).click();

  await page.getByRole('button', { name: '新增转换' }).click();
  await page.getByLabel('新转换标识符').fill('to_off');
  await page.getByRole('button', { name: '添加', exact: true }).click();
  await expect.poll(async () => (await machine(path, 'light')).transitions.length).toBe(5);

  // 改成超时条件并修改时长与端点
  await page.getByLabel('to_off 触发方式').selectOption('after_ms');
  await expect.poll(async () => (await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').on).toEqual({ after_ms: 1000 });
  await expect(page.getByLabel('to_off 停留毫秒')).toHaveValue('1000');   // 等 select 落盘、输入框重建
  await page.getByLabel('to_off 停留毫秒').fill('2500');
  await page.getByLabel('to_off 停留毫秒').press('Enter');
  await expect.poll(async () => (await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').on.after_ms).toBe(2500);
  await expect(page.getByLabel('to_off 停留毫秒')).toHaveValue('2500');
  await page.getByLabel('to_off 终点').selectOption('red');
  await expect.poll(async () => (await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').to).toBe('red');
  await page.getByLabel('to_off 起点').selectOption('*');
  await expect.poll(async () => (await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').from).toBe('*');
  await expect(page.locator('.machine-any')).toBeVisible();

  // 切换成信号条件
  await page.getByLabel('to_off 触发方式').selectOption('signal');
  await expect.poll(async () => Object.keys((await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').on)).toEqual(['signal', 'op', 'value']);
  await page.getByLabel('to_off 比较符').selectOption('>=');
  await expect.poll(async () => (await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').on.op).toBe('>=');
  await page.getByLabel('to_off 数值').fill('2');
  await page.getByLabel('to_off 数值').press('Enter');
  await expect.poll(async () => (await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').on.value).toBe(2);

  // 切换成函数条件
  await page.getByLabel('to_off 触发方式').selectOption('call');
  await expect.poll(async () => (await machine(path, 'light')).transitions.find((t: { id: string }) => t.id === 'to_off').on.call).toBe('light_cond');

  // 排序与删除（新增后该规则仍是展开的）
  await page.getByLabel('to_off 上移').click();
  await expect.poll(async () => (await machine(path, 'light')).transitions[3].id).toBe('to_off');
  await page.getByLabel('to_off 删除').click();
  await expect.poll(async () => (await machine(path, 'light')).transitions.length).toBe(4);

  // 状态机页的改动同步到通信页的事件引用
  await page.getByRole('button', { name: '通信', exact: true }).click();
  await page.getByRole('button', { name: '事件 1', exact: true }).click();
  await expect(page.getByRole('region', { name: '通信详情' })).toContainText('被消费');
});