import { useStore } from '../store';
import type { Model, Step } from '../types';

const VERB: Record<string, string> = {
  read: '读取', write: '写入', set: '设为常数', lowpass: '低通滤波', avg: '滑动平均',
  scale: '缩放', clamp: '限幅', pid: 'PID', emit: '发出事件', custom: '自定义 C',
};
const REFS = ['from', 'setpoint', 'feedback', 'signal', 'input', 'output', 'to', 'event', 'call'];

function Id({ v }: { v: unknown }) { return <span className="chip">{String(v)}</span>; }

function Sentence({ s, i }: { s: Step; i: number }) {
  const num = (k: string) => (s[k] !== undefined ? `${k} ${s[k]}` : null);
  const params = Object.keys(s)
    .filter((k) => !['id', 'kind', ...REFS].includes(k))
    .map(num)
    .filter(Boolean);
  const dst = s.to ?? s.output;
  const src = s.from ?? s.input;
  return (
    <div className="sentence">
      <span className="no">{i + 1}</span>
      <span className="verb">{VERB[s.kind] ?? s.kind}</span>
      {s.kind === 'pid' && <><Id v={dst} /><span className="arrow">←</span><Id v={s.setpoint} /><span className="sub">对</span><Id v={s.feedback} /></>}
      {s.kind === 'emit' && <><Id v={s.event} /><span className="sub">当</span><Id v={s.signal} /><span>{String(s.op)}</span><span className="id">{String(s.value)}</span></>}
      {s.kind === 'custom' && <Id v={s.call} />}
      {!['pid', 'emit', 'custom'].includes(s.kind) && (
        <>
          {dst !== undefined && <Id v={dst} />}
          {src !== undefined && <><span className="arrow">←</span><Id v={src} /></>}
        </>
      )}
      {s.kind !== 'emit' && params.length > 0 && <span className="param">{params.join('  ')}</span>}
    </div>
  );
}

function controller(m: Model, flowId: string): string | null {
  const st = m.machines.flatMap((mc) => mc.states.filter((s) => s.run.includes(flowId)).map((s) => `${mc.label}·${s.label}`));
  return st.length ? st.join('、') : null;
}

export function Flows() {
  const { project } = useStore();
  if (!project) return null;
  const m = project.model;
  return (
    <>
      <div>
        <h1>数据流</h1>
        <p className="sub">每个数据流按周期，从上到下依次执行这些步骤。</p>
      </div>
      {m.flows.length === 0 && <p className="empty">还没有数据流。</p>}
      {m.flows.map((f) => (
        <section className="card" key={f.id}>
          <header>
            <span><strong>{f.label}</strong> <span className="id sub">{f.id}</span></span>
            <span className="sub">每 <span className="id">{f.period_ms}</span> ms · {controller(m, f.id) ? `在 ${controller(m, f.id)} 运行` : '始终运行'}</span>
          </header>
          {f.steps.map((s, i) => <Sentence key={s.id} s={s} i={i} />)}
        </section>
      ))}
    </>
  );
}
