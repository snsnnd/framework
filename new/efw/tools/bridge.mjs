// 开发桥：把浏览器的 POST /rpc 转给 python 服务（stdio JSON Lines），并用 SSE /events 推送通知。
// Electron 阶段由主进程接管同样的职责，界面代码不变。
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

export function efwBridge() {
  return {
    name: 'efw-bridge',
    configureServer(server) {
      const py = spawn('uv', ['run', 'python', '-m', 'studio_core.server'], { stdio: ['pipe', 'pipe', 'inherit'] });
      const pending = new Map();
      const clients = new Set();
      let seq = 0;

      createInterface({ input: py.stdout }).on('line', (line) => {
        let msg;
        try { msg = JSON.parse(line); } catch { return; }
        if (msg.id != null && pending.has(msg.id)) {
          pending.get(msg.id)(msg);
          pending.delete(msg.id);
        } else if (msg.event) {
          for (const res of clients) res.write(`data: ${line}\n\n`);
        }
      });
      py.on('exit', () => {
        for (const done of pending.values()) done({ error: { code: 'INTERNAL', message: '后端服务已退出' } });
        pending.clear();
      });
      server.httpServer?.on('close', () => py.kill());

      server.middlewares.use('/events', (_req, res) => {
        res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
        res.write(': ok\n\n');
        clients.add(res);
        res.on('close', () => clients.delete(res));
      });

      server.middlewares.use('/rpc', (req, res) => {
        if (req.method !== 'POST') { res.statusCode = 405; res.end(); return; }
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          let request;
          try { request = JSON.parse(body); } catch { res.statusCode = 400; res.end('bad json'); return; }
          const id = ++seq;
          pending.set(id, (msg) => {
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify(msg));
          });
          py.stdin.write(JSON.stringify({ id, method: request.method, params: request.params ?? {} }) + '\n');
        });
      });
    },
  };
}
