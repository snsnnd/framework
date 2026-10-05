import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-edit-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

const model = async (path: string) => JSON.parse(await readFile(join(path, 'efw.json'), 'utf8'));

test('通信页：新增、编辑、删除信号并同步到磁盘', async ({ page, request }, testInfo) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '通信', exact: true }).click();

  // 编辑名称 → 其他页面同步
  const label = page.getByLabel('原始温度 名称');
  await label.fill('传感器原始值');
  await label.press('Enter');
  await expect.poll(async () => (await model(path)).signals.find((s: { id: string }) => s.id === 'temp_raw').label).toBe('传感器原始值');
  await page.getByRole('button', { name: '数据流', exact: true }).click();
  await expect(page.locator('.step-row[data-id="read"]')).toContainText('temp_raw');
  await page.getByRole('button', { name: '通信', exact: true }).click();
  await expect(page.getByLabel('传感器原始值 名称')).toHaveValue('传感器原始值');

  // 编辑初始值与单位
  const init = page.getByLabel('temp 初始值');
  await init.fill('25.5');
  await init.press('Enter');
  await expect.poll(async () => (await model(path)).signals.find((s: { id: string }) => s.id === 'temp').init).toBe(25.5);
  const unit = page.getByLabel('temp 单位');
  await unit.fill('℃');
  await unit.press('Enter');
  await expect.poll(async () => (await model(path)).signals.find((s: { id: string }) => s.id === 'temp').unit).toBe('℃');

  // 新增信号（默认不可整定），再开启整定并改范围
  await page.getByRole('button', { name: '新增信号' }).click();
  await page.getByLabel('新名称').fill('压力');
  await page.getByLabel('新标识符').fill('pressure');
  await page.getByLabel('新标识符').press('Enter');
  await page.getByRole('button', { name: '添加', exact: true }).click();
  await expect.poll(async () => (await model(path)).signals.some((s: { id: string }) => s.id === 'pressure')).toBe(true);
  await expect(page.getByLabel('压力 名称')).toHaveValue('压力');
  await page.locator('tr[data-id="pressure"] .tune-toggle input').click();
  await expect.poll(async () => (await model(path)).signals.find((s: { id: string }) => s.id === 'pressure').tune).toEqual({ min: 0, max: 100 });
  await page.getByLabel('pressure 整定上限').fill('250');
  await page.getByLabel('pressure 整定上限').press('Enter');
  await expect.poll(async () => (await model(path)).signals.find((s: { id: string }) => s.id === 'pressure').tune.max).toBe(250);

  // 删除未被引用的信号；被引用的信号禁止删除
  await page.locator('tr[data-id="pressure"]').getByRole('button', { name: '删除' }).click();
  await page.locator('tr[data-id="pressure"]').getByRole('button', { name: '确认删除' }).click();
  await expect.poll(async () => (await model(path)).signals.some((s: { id: string }) => s.id === 'pressure')).toBe(false);
  await page.locator('tr[data-id="temp_raw"]').getByRole('button', { name: '删除' }).click();
  await page.locator('tr[data-id="temp_raw"]').getByRole('button', { name: '确认删除' }).click();
  await expect(page.locator('.diag.error')).toContainText('仍被引用');
  expect((await model(path)).signals.some((s: { id: string }) => s.id === 'temp_raw')).toBe(true);

  await page.screenshot({ path: testInfo.outputPath('edit-signals-dark.png') });
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('edit-signals-light.png') });
});

test('通信页：事件与队列的增删改，以及被后端拒绝的编辑', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '采样', template: 'sampler' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '通信', exact: true }).click();

  await page.getByRole('button', { name: '队列 1', exact: true }).click();
  await page.getByLabel('samples 容量').fill('32');
  await page.getByLabel('samples 容量').press('Enter');
  await expect.poll(async () => (await model(path)).queues[0].capacity).toBe(32);
  await page.getByLabel('samples 满队策略').selectOption('drop_newest');
  await expect.poll(async () => (await model(path)).queues[0].policy).toBe('drop_newest');
  await page.getByRole('button', { name: '新增队列' }).click();
  await page.getByLabel('新名称').fill('控制字');
  await page.getByLabel('新标识符').fill('cmds');
  await page.getByRole('button', { name: '添加', exact: true }).click();
  await expect.poll(async () => (await model(path)).queues.length).toBe(2);

  await page.getByRole('button', { name: '事件 2', exact: true }).click();
  const label = page.getByLabel('超阈值 名称');
  await label.fill('超过上限');
  await label.press('Enter');
  await expect.poll(async () => (await model(path)).events[0].label).toBe('超过上限');

  // 后端拒绝的编辑：容量超出 1..1024 → 保留原值并给出诊断
  await page.getByRole('button', { name: '队列 2', exact: true }).click();
  const cap = page.getByLabel('samples 容量');
  await cap.fill('5000');
  await cap.press('Enter');
  await expect(page.locator('.diag.error')).toContainText('容量必须是 1..1024');
  expect((await model(path)).queues[0].capacity).toBe(32);
  await expect(cap).toHaveValue('32');

  // 删除队列允许（无引用检查），删除被状态机消费的事件应被拦截
  await page.getByRole('button', { name: '事件 2', exact: true }).click();
  await page.locator('tr[data-id="high"]').getByRole('button', { name: '删除' }).click();
  await page.locator('tr[data-id="high"]').getByRole('button', { name: '确认删除' }).click();
  await expect(page.locator('.diag.error')).toContainText('仍被引用');
  await page.getByRole('button', { name: '队列 2', exact: true }).click();
  await page.locator('tr[data-id="cmds"]').getByRole('button', { name: '删除' }).click();
  await page.locator('tr[data-id="cmds"]').getByRole('button', { name: '确认删除' }).click();
  await expect.poll(async () => (await model(path)).queues.some((q: { id: string }) => q.id === 'cmds')).toBe(false);
});

test('模型改动后调试页提示目标已过期', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '运行', exact: true }).click();
  await expect(page.getByText('运行中')).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: '通信', exact: true }).click();
  const label = page.getByLabel('原始温度 名称');
  await label.fill('改名了');
  await label.press('Enter');
  await expect.poll(async () => (await model(path)).signals[0].label).toBe('改名了');
  await page.getByRole('button', { name: '调试', exact: true }).click();
  await expect(page.locator('.debug-message')).toContainText('模型已修改');
  await page.getByRole('region', { name: '调试控制' }).getByRole('button', { name: '停止' }).click();
});
test('通信页：编辑输入的仿真，并让数据流的读取步骤选中它', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');
  await page.getByRole('button', { name: '通信', exact: true }).click();

  // 输入分类可切换，详情区给出需要实现的 C 函数
  await page.getByRole('button', { name: /^输入 / }).click();
  const row = page.locator('tr[data-id="sensor"]');
  await row.click();
  await expect(page.locator('.comm-io-fns')).toContainText('sensor_read');

  // 仿真类型与字段由后端 sim_specs 驱动
  await page.getByLabel('sensor 仿真类型').selectOption('sine');
  await expect.poll(async () => (await model(path)).inputs.find((i: { id: string }) => i.id === 'sensor').sim.kind).toBe('sine');
  const amp = page.getByLabel('sensor 幅值');
  await amp.fill('12.5');
  await amp.press('Enter');
  await expect.poll(async () => (await model(path)).inputs.find((i: { id: string }) => i.id === 'sensor').sim.amp).toBe(12.5);

  // 切到 follow 必须一次就保存成功（预填第一个输出），否则用户没法再选输出
  await page.getByLabel('sensor 仿真类型').selectOption('follow');
  await expect.poll(async () => (await model(path)).inputs.find((i: { id: string }) => i.id === 'sensor').sim.output).toBe('heater');
  await expect(page.getByLabel('sensor 跟随的输出')).toHaveValue('heater');
  await expect(page.locator('.diag')).toHaveCount(0);

  // 新增输入后，读取步骤能选到它（step_specs 的 input 字段）
  await page.getByRole('button', { name: '新增输入' }).click();
  await page.getByLabel('新名称').fill('压力');
  await page.getByLabel('新标识符').fill('pressure');
  await page.getByRole('button', { name: '添加' }).click();
  await expect.poll(async () => (await model(path)).inputs.map((i: { id: string }) => i.id)).toContain('pressure');
  await expect(page.locator('.comm-io-fns')).toContainText('pressure_read');

  await page.getByRole('button', { name: '数据流', exact: true }).click();
  const readRow = page.locator('.step-row[data-id="read"]');
  await readRow.click();
  const pick = readRow.getByLabel('read 输入');
  await pick.selectOption('pressure');
  await expect.poll(async () => (await model(path)).flows[0].steps.find((s: { id: string }) => s.id === 'read').input).toBe('pressure');

  // 仍被读取步骤引用的输入不给删
  await page.getByRole('button', { name: '通信', exact: true }).click();
  await page.getByRole('button', { name: /^输入 / }).click();
  await page.locator('tr[data-id="pressure"]').click();
  await page.locator('tr[data-id="pressure"]').getByRole('button', { name: '删除' }).click();
  await page.locator('tr[data-id="pressure"]').getByRole('button', { name: '确认删除' }).click();
  await expect(page.getByRole('alert')).toContainText('仍被引用');
  await expect.poll(async () => (await model(path)).inputs.map((i: { id: string }) => i.id)).toContain('pressure');
});
