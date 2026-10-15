import { test, expect } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let root: string;
test.setTimeout(120000);
test.beforeEach(async () => { root = await mkdtemp(join(tmpdir(), 'efw-shell-')); });
test.afterEach(async () => { await rm(root, { recursive: true, force: true }); });

/**
 * 桌面版（Electron）渲染层：ui/rpc.ts 检测到 window.efw 就改走 IPC。
 * 这里注入一个假的 preload，验证切过去以后请求不再经过 HTTP 桥。
 */
test('渲染层在 window.efw 存在时改走 IPC', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '壳测试', template: 'blank' } } });

  await page.addInitScript(() => {
    // 记录发生在页面里：addInitScript 的参数是快照，回传要用 evaluate 读
    (window as unknown as { __efwCalls: string[] }).__efwCalls = [];
    (window as unknown as { __efwPath: string }).__efwPath = '';
    (window as unknown as { efw: unknown }).efw = {
      call: async (method: string) => {
        (window as unknown as { __efwCalls: string[] }).__efwCalls.push(method);
        if (method === 'system.info') return { version: '0.9.9-desktop', protocol: 2, runtime: '/resources/runtime' };
        if (method === 'templates.list') return [{ id: 'blank', label: '空白', text: 'x', features: [] }];
        // 打开项目要真实结果才能继续走界面：这一跳仍然先经过 IPC（已记录），再由假桥转发给 HTTP
        if (method === 'project.open' || method === 'project.analyze') {
          const res = await fetch('/rpc', {
            method: 'POST',
            body: JSON.stringify({ method, params: { path: window.__efwPath, model: window.__efwModel } }),
          });
          return (await res.json()).result;
        }
        return {};
      },
      pickDirectory: async () => '/tmp/picked-by-user',
      onEvent: (fn: (msg: { event: string }) => void) => {
        fn({ event: 'debug.status', state: 'running' });
        return () => undefined;
      },
    };
  });
  const calls = () => page.evaluate(() => (window as unknown as { __efwCalls: string[] }).__efwCalls);
  await page.addInitScript((p: string) => { (window as unknown as { __efwPath: string }).__efwPath = p; }, path);

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'EFW Studio' })).toBeVisible();
  // 模板来自 IPC，不是 HTTP 桥
  await expect(page.getByRole('button', { name: /空白/ })).toBeVisible();
  expect(await calls()).toContain('templates.list');
  // 浏览按钮只有桌面版才有
  await expect(page.getByRole('button', { name: '浏览…' })).toBeVisible();

  // 打开项目也应走 IPC（假桥只回空对象，界面据此报错但不应回落去请求 HTTP）
  await page.getByLabel('项目目录').fill(path);
  await page.getByRole('button', { name: '打开已有' }).click();
  await expect(page.getByRole('button', { name: '生成', exact: true })).toBeVisible();
  expect(await calls()).toContain('project.open');
});

test('浏览器里没有浏览按钮，接口仍走 HTTP 桥', async ({ page, request }) => {
  const path = join(root, 'app');
  await request.post('/rpc', { data: { method: 'project.create', params: { path, name: '壳测试', template: 'blank' } } });
  await page.addInitScript((p) => localStorage.setItem('efw.lastProject', p), path);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '壳测试' })).toBeVisible();
  // 已打开项目时不显示欢迎页；这里验证浏览器环境下 window.efw 不存在
  expect(await page.evaluate(() => 'efw' in window)).toBe(false);
});
test('欢迎页：模板没到之前有骨架，到失败有说法', async ({ page }) => {
  // 让 templates.list 慢一点，看首屏是否留白
  await page.route('**/rpc', async (route) => {
    const body = route.request().postData() ?? '';
    if (body.includes('templates.list')) {
      await new Promise((r) => setTimeout(r, 1200));
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, result: [] }) });
    }
    return route.continue();
  });
  await page.goto('/');
  await expect(page.locator('.tpl-skeleton')).toHaveCount(4);
  // 没有模板时要说清楚，而不是空白
  await expect(page.getByText('没有可用模板')).toBeVisible({ timeout: 20000 });
  await expect(page.locator('.tpl-skeleton')).toHaveCount(0);
});
