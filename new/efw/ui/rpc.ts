// 与服务通信的唯一入口：浏览器开发时走开发桥的 HTTP/SSE，Electron 里走 preload 的 IPC。
// 页面只调 call() 与 onEvent()，不感知当前是哪一种传输。

/** preload 注入的最小桥（desktop/preload.cjs）。 */
interface ElectronBridge {
  call: (method: string, params: Record<string, unknown>) => Promise<unknown>;
  onEvent: (fn: (msg: { event: string; [k: string]: unknown }) => void) => () => void;
}

const bridge = (): ElectronBridge | null =>
  typeof window !== 'undefined' && 'efw' in window ? (window as unknown as { efw: ElectronBridge }).efw : null;

export const isDesktop = () => bridge() !== null;
export class RpcError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

/** 响应丢失（后端卡死或退出）时必须报错，否则界面会一直停在“保存中”。虚拟构建较慢，默认 120 秒。 */
const TIMEOUT_MS = 120000;

export async function call<T>(method: string, params: Record<string, unknown> = {}, timeoutMs = TIMEOUT_MS): Promise<T> {
  const ipc = bridge();
  if (ipc) {
    try {
      return await ipc.call(method, params) as T;
    } catch (e) {
      throw new RpcError('BACKEND', (e as Error).message);
    }
  }
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch('/rpc', { method: 'POST', body: JSON.stringify({ method, params }), signal: ac.signal });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw new RpcError('TIMEOUT', `${method} 超时 ${Math.round(timeoutMs / 1000)} 秒没有响应`);
    throw new RpcError('NETWORK', `无法连接后端服务：${(e as Error).message}`);
  } finally {
    clearTimeout(timer);
  }
  const msg = await res.json();
  if (msg.error) throw new RpcError(msg.error.code, msg.error.message);
  return msg.result as T;
}

export function onEvent(fn: (event: { event: string; [k: string]: unknown }) => void): () => void {
  const ipc = bridge();
  if (ipc) return ipc.onEvent(fn);
  const es = new EventSource('/events');
  es.onmessage = (e) => fn(JSON.parse(e.data));
  return () => es.close();
}

/** 选目录：Electron 走系统对话框，浏览器里没有这个能力（返回 null）。 */
export async function pickDirectory(): Promise<string | null> {
  const ipc = bridge();
  if (!ipc) return null;
  return (ipc as ElectronBridge & { pickDirectory: () => Promise<string | null> }).pickDirectory();
}
