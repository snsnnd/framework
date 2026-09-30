// 与服务通信的唯一入口。Electron 阶段只需替换这里的传输。
export class RpcError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

export async function call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch('/rpc', { method: 'POST', body: JSON.stringify({ method, params }) });
  const msg = await res.json();
  if (msg.error) throw new RpcError(msg.error.code, msg.error.message);
  return msg.result as T;
}

export function onEvent(fn: (event: { event: string; [k: string]: unknown }) => void): () => void {
  const es = new EventSource('/events');
  es.onmessage = (e) => fn(JSON.parse(e.data));
  return () => es.close();
}
