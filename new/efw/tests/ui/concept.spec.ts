import { test, expect } from '@playwright/test';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(180000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-concept-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

const model = async (path: string) => JSON.parse(await readFile(join(path, 'efw.json'), 'utf8'));

test('项目结构图按真实关系渲染，并能跳到编辑页', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '恒温控制', template: 'thermostat' } } });
  // 加一条没人用的信号：它不该出现在结构图里
  const file = join(path, 'efw.json');
  const m = JSON.parse(await readFile(file, 'utf8'));
  m.signals.push({ id: 'ghost', label: '没人用', type: 'float', init: 0, unit: '', tune: null });
  await writeFile(file, JSON.stringify(m, null, 2) + '\n');
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');

  const svg = page.locator('.concept-svg');
  await expect(svg).toBeVisible();
  // innerText 对 SVG 不可靠，用 textContent 断言真实内容
  const text = await svg.textContent();
  for (const needle of ['温度控制', 'sensor', 'heater', '正常控制', '过热', 'overheat']) expect(text).toContain(needle);
  expect(text).not.toContain('ghost');            // 没被用到的信号不画
  expect(text).not.toContain('faults');           // 同上：faults 无人读写
  await expect(page.locator('.concept-legend')).toContainText('4/6');

  // 连线来自 usage：读取为青色、状态机启停为虚线
  expect(await svg.locator('.cm-line.is-read').count()).toBeGreaterThan(0);
  expect(await svg.locator('.cm-line.is-run').count()).toBeGreaterThan(0);

  // 点数据流盒子 → 跳到数据流页并定位
  await svg.locator('.cm-node.is-flow').first().click();
  await expect(page.locator('.blueprint').first()).toBeVisible();

  // 点信号盒子 → 通信页并选中
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await page.locator('.concept-svg .cm-node.is-signal').first().click();
  await expect(page.locator('tr.is-selected')).toBeVisible();
});
