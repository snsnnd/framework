// 与服务通信的唯一入口。Electron 阶段只需替换这里的传输。
export class RpcError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

/** 响应丢失（后端卡死或退出）时必须报错，否则界面会一直停在“保存中”。虚拟构建较慢，默认 120 秒。 */
const TIMEOUT_MS = 120000;

export async function call<T>(method: string, params: Record<string, unknown> = {}, timeoutMs = TIMEOUT_MS): Promise<T> {
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
  const es = new EventSource('/events');
  es.onmessage = (e) => fn(JSON.parse(e.data));
  return () => es.close();
}
