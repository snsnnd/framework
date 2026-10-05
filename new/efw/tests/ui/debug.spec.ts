import { test, expect } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-debug-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

test('虚拟目标：草稿门禁、运行暂停单步、整定、事件、停止与回放', async ({ page, request }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.addInitScript((path) => localStorage.setItem('efw.lastProject', path), path);
  await page.goto('/');

  // 未保存草稿时禁止运行，保存后恢复
  await page.getByRole('button', { name: '代码', exact: true }).click();
  await page.getByLabel('新文件路径').fill('src/pending.c');
  await page.getByRole('button', { name: '新建草稿' }).click();
  const run = page.getByRole('button', { name: '运行', exact: true });
  await expect(run).toBeDisabled();
  await expect(page.locator('.monaco-editor textarea')).toBeVisible({ timeout: 120000 });
  await page.getByRole('button', { name: '保存文件', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('已保存', { timeout: 30000 });
  await expect(run).toBeEnabled();

  // 启动虚拟目标
  await run.click();
  await expect(page.getByRole('heading', { name: '调试', exact: true })).toBeVisible();
  await expect(page.getByText('运行中')).toBeVisible({ timeout: 30000 });
  const clock = page.locator('.debug-t .id');
  await expect.poll(async () => Number(await clock.innerText()), { timeout: 30000 }).toBeGreaterThan(150);

  // 暂停后时间不再前进；单步推进
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(page.getByText('已暂停')).toBeVisible();
  await page.waitForTimeout(400);
  const paused = Number(await clock.innerText());
  await page.waitForTimeout(700);
  expect(Number(await clock.innerText())).toBe(paused);
  await page.getByRole('button', { name: '单步', exact: true }).click();
  await expect.poll(async () => Number(await clock.innerText()), { timeout: 10000 }).toBeGreaterThan(paused);
  await page.getByRole('button', { name: '播放', exact: true }).click();
  await expect(page.getByText('运行中')).toBeVisible();

  // 曲线、任务、状态机（按模型 id 定位，不依赖展示文案）
  await expect(page.locator('.chart-legend [data-id="temp_raw"]')).toContainText('原始温度');
  await expect(page.locator('.tasks tr[data-id="control"]')).toContainText('温度控制');
  await expect(page.locator('.debug-machines [data-id="mode"]')).toContainText('正常控制');

  // 整定：按稳定 id 选中 target，确认命令往返（ack）与回显
  const target = page.locator('.tuner[data-key="target"] input[type="number"]');
  await target.fill('45');
  await target.blur();
  await expect(page.locator('.debug-ack')).toContainText('目标已确认', { timeout: 10000 });
  await expect(page.locator('.debug-ack')).toContainText('set');
  await expect(target).toHaveValue('45');

  // 触发事件进入过热保护
  await page.locator('.debug-event[data-id="overheat"]').getByRole('button', { name: '触发' }).click();
  await expect(page.locator('.debug-machines [data-id="mode"]')).toContainText('过热保护', { timeout: 10000 });
  await page.screenshot({ path: testInfo.outputPath('debug-dark.png') });

  // 停止后出现录制列表
  await page.getByRole('region', { name: '调试控制' }).getByRole('button', { name: '停止' }).click();
  await expect(page.getByText('已停止')).toBeVisible();
  await expect(page.locator('.debug-start select option')).not.toHaveCount(0);

  // 最快速度回放
  await page.getByRole('button', { name: '启动回放' }).click();
  await expect(page.getByText(/回放中不能发送命令/)).toBeVisible({ timeout: 20000 });
  await page.getByLabel('仿真速度').selectOption('0');
  await expect(page.locator('.debug-message')).toContainText('回放结束', { timeout: 60000 });

  // 亮色窄窗口
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.locator('.page').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('debug-light-narrow.png') });
});

test('调试页选择真机目标：参数不全时不启动，顶栏运行沿用所选目标', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  await page.getByRole('button', { name: '调试', exact: true }).click();

  // 默认虚拟目标，顶栏“运行”随之启动虚拟目标
  await expect(page.getByRole('button', { name: '虚拟目标', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: '启动虚拟目标' })).toBeEnabled();

  // 切到串口：没填设备就不能启动，并说明原因
  await page.getByRole('button', { name: '串口目标', exact: true }).click();
  const serial = page.getByRole('button', { name: '连接串口' });
  await expect(serial).toBeDisabled();
  await expect(serial).toHaveAttribute('title', '请先填写串口设备，例如 /dev/ttyUSB0 或 COM3');
  await page.getByLabel('波特率').selectOption('9600');

  // 切到 TCP：主机和端口都要填
  await page.getByRole('button', { name: 'TCP 目标', exact: true }).click();
  const tcp = page.getByRole('button', { name: '连接 TCP' });
  await expect(tcp).toBeDisabled();
  await expect(tcp).toHaveAttribute('title', '请先填写目标主机或 IP');
  await page.getByLabel('TCP 主机').fill('192.168.1.20');
  await expect(tcp).toBeDisabled();
  await page.getByLabel('TCP 端口').fill('115200');
  await expect(tcp).toBeEnabled();
  await page.getByLabel('TCP 端口').fill('');
  await expect(tcp).toBeDisabled();

  // 顶栏“运行”用同一个目标，不会偷偷启动虚拟目标
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await page.getByRole('button', { name: '运行', exact: true }).click();
  await page.getByRole('button', { name: '调试', exact: true }).click();
  await expect(page.getByText('请先填写端口号')).toBeVisible();
  await expect(page.getByText('运行中')).toHaveCount(0);

  // 回连串口时故意写错设备名，后端的连接错误必须如实显示（失败的会话没有 session，只能靠启动卡上的告警）
  await page.getByRole('button', { name: '串口目标', exact: true }).click();
  await page.getByLabel('串口设备').fill('/dev/efw-no-such-port');
  await page.getByRole('button', { name: '连接串口' }).click();
  await expect(page.getByRole('alert')).toContainText(/efw-no-such-port|pyserial/, { timeout: 30000 });
});

test('调试运行时状态机页高亮当前状态', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');

  // 没在调试：图上只有“初始”标记，没有运行中高亮
  await page.getByRole('button', { name: '状态机', exact: true }).click();
  await expect(page.locator('.machine-state.is-live')).toHaveCount(0);
  await expect(page.locator('.machine-initial')).toHaveCount(1);

  await page.getByRole('button', { name: '调试', exact: true }).click();
  await page.getByRole('button', { name: '启动虚拟目标' }).click();
  await expect(page.getByText('运行中')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.card[aria-label="状态机"] .chip.acc')).toBeVisible();

  // 运行中：当前状态同时用 aria-current 和“运行中 Ns”标注
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: '状态机', exact: true }).click();
  const live = page.locator('.machine-state.is-live');
  await expect(live).toHaveCount(1);
  await expect(live).toHaveAttribute('aria-current', 'true');
  await expect(page.locator('.machine-live')).toContainText('运行中');

  // 停止后高亮消失
  await page.getByRole('button', { name: '调试', exact: true }).click();
  await page.getByRole('button', { name: '停止', exact: true }).first().click();
  await expect(page.getByText('已停止')).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: '状态机', exact: true }).click();
  await expect(page.locator('.machine-state.is-live')).toHaveCount(0);
});
