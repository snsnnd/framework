// 开发桥（tools/bridge.mjs）与 Electron 主进程（desktop/main.mjs）共用的协议约定：
// stdout 只出协议行、响应带 id、通知不带 id。这里校验行解析规则与真实服务的往返。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createInterface } from 'node:readline';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

/** 与两个壳里相同的行解析规则；抽出后可独立测。 */
function dispatch({ onResponse, onEvent, onDropped }) {
  return (line) => {
    let msg;
    try { msg = JSON.parse(line); } catch { onDropped(line); return; }
    if (msg.id != null) onResponse(msg);
    else if (msg.event) onEvent(msg);
  };
}

test('响应按 id 配对，通知不带 id，污染的行被丢弃而不吞掉后续响应', () => {
  const responses = new Map();
  const events = [];
  const dropped = [];
  const line = dispatch({
    onResponse: (msg) => {
      const done = responses.get(msg.id);
      if (done) { responses.delete(msg.id); done(msg); } else dropped.push(`未知 id ${msg.id}`);
    },
    onEvent: (msg) => events.push(msg),
    onDropped: (text) => dropped.push(text),
  });

  const seen = [];
  responses.set(1, (msg) => seen.push(msg.result));
  line('{"id":1,"result":{"protocol":2}}');
  line('这不是 JSON');                                     // 污染
  line('{"event":"debug.frames","frames":[]}');           // 通知
  responses.set(3, (msg) => seen.push(msg.result));
  line('{"id":3,"result":{"version":"0.2.0"}}');           // 污染之后仍然送达

  assert.deepEqual(seen, [{ protocol: 2 }, { version: '0.2.0' }]);
  assert.equal(events.length, 1);
  assert.deepEqual(dropped, ['这不是 JSON']);
});

test('真实服务：并发请求各自拿到自己的结果，非法方法只回错误', async () => {
  const proc = spawn('python3', ['-m', 'studio_core.server'], { cwd: root, stdio: ['pipe', 'pipe', 'pipe'] });
  try {
    const responses = new Map();
    let seq = 0;
    const request = (method, params) => new Promise((resolve, reject) => {
      const id = ++seq;
      responses.set(id, (msg) => (msg.error ? reject(new Error(`${msg.error.code}: ${msg.error.message}`)) : resolve(msg.result)));
      proc.stdin.write(JSON.stringify({ id, method, params: params ?? {} }) + '\n');
    });
    createInterface({ input: proc.stdout }).on('line', dispatch({
      onResponse: (msg) => responses.get(msg.id)?.(msg),
      onEvent: () => undefined,
      onDropped: () => undefined,
    }));

    const [info, templates] = await Promise.all([request('system.info'), request('templates.list')]);
    assert.equal(info.protocol, 2);
    assert.equal(templates.length, 4);
    await assert.rejects(request('shell.exec'), /未知方法/);
    // 出错之后服务仍然可用
    assert.equal((await request('system.info')).protocol, 2);
  } finally {
    proc.kill();
  }
});