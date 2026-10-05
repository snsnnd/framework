import { PAGE_LABEL, repairFor, repairForFunction, repairHint, type RepairTarget } from '../focus';
import { useStore } from '../store';
import type { FnInfo } from '../types';

const COLORS = ['var(--accent)', 'var(--ok)', 'var(--warn)', '#a78bfa', '#38bdf8', 'var(--fg-faint)'];

/** 一条可跳转的修复入口：点它到能修掉这个问题的页面。 */
function RepairRow({ level, at, text, hint, onRepair, target }: {
  level: string; at: string; text: string; hint?: string;
  onRepair: (target: RepairTarget) => void;
  target: RepairTarget | null;
}) {
  const body = <>
    <div className="at">{at}</div>
    <div>{text}</div>
    {hint && <div className="hint">{hint}</div>}
  </>;
  if (!target) return <div className={`diag ${level}`}><div>{body}</div></div>;
  return <button className={`diag repair ${level}`} onClick={() => onRepair(target)}>
    <div>{body}<span className="go">去{PAGE_LABEL[target.page]}页 · {repairHint(target)}</span></div>
    <span className="chev" aria-hidden="true">›</span>
  </button>;
}

export function Overview({ onRepair }: { onRepair: (target: RepairTarget) => void }) {
  const { project, analysis } = useStore();
  if (!project || !analysis) return <p className="sub">分析中…</p>;
  const m = project.model;
  const missing = analysis.functions.filter((f) => !f.defined || f.mismatch);

  const cards = [
    { label: '输入 / 输出', n: m.inputs.length + m.outputs.length, items: [...m.inputs, ...m.outputs].map((x) => x.id) },
    { label: '信号', n: m.signals.length, items: m.signals.map((x) => x.id) },
    { label: '数据流', n: m.flows.length, items: m.flows.map((x) => x.id) },
    { label: '状态机', n: m.machines.length, items: m.machines.map((x) => x.id) },
    { label: '事件 / 队列', n: m.events.length + m.queues.length, items: [...m.events, ...m.queues].map((x) => x.id) },
  ];

  return (
    <>
      <div>
        <h1>{m.name}</h1>
        <p className="sub">节拍 {m.tick_ms} ms · {m.flows.length} 条数据流 · {m.machines.length} 个状态机</p>
      </div>

      <div className="grid five">
        {cards.map((c) => (
          <div className="stat" key={c.label}>
            <div className="n">{c.n}</div>
            <div className="l">{c.label}</div>
            <ul>{c.items.slice(0, 6).map((id) => <li key={id} className="chip">{id}</li>)}</ul>
          </div>
        ))}
      </div>

      <div className="grid two">
        <section className="card">
          <header><h2>执行计划</h2></header>
          <table>
            <thead><tr><th>任务</th><th className="num">周期</th><th className="num">步骤</th><th>由谁控制</th></tr></thead>
            <tbody>
              {analysis.plan.map((p) => (
                <tr key={p.id}>
                  <td>{p.label} <span className="id sub">{p.id}</span></td>
                  <td className="num">{p.period_ms} ms</td>
                  <td className="num">{p.steps}</td>
                  <td>{p.controlled_by ? <span className="chip acc">{p.controlled_by}</span> : <span className="sub">始终运行</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <header><h2>内存估算</h2><span className="id">{analysis.memory.total} B</span></header>
          <div className="body">
            <div className="bar">
              {analysis.memory.parts.filter((p) => p.bytes > 0).map((p, i) => <i key={p.name} title={p.name} style={{ width: `${(p.bytes / analysis.memory.total) * 100}%`, background: COLORS[i % COLORS.length] }} />)}
            </div>
            <div className="legend">
              {analysis.memory.parts.filter((p) => p.bytes > 0).map((p, i) => (
                <span key={p.name}><span style={{ color: COLORS[i % COLORS.length] }}>●</span> {p.name} <span className="id">{p.bytes}</span></span>
              ))}
            </div>
          </div>
        </section>
      </div>

      <section className="card">
        <header><h2>下一步</h2></header>
        {missing.length === 0 && analysis.diagnostics.length === 0 && <p className="empty">一切就绪，可以生成代码或开始调试。</p>}
        {missing.map((f) => (
          <RepairRow key={f.name} level="error" at={f.file} onRepair={onRepair} target={repairForFunction(f as FnInfo)}
            text={`${f.mismatch ?? `缺少函数 ${f.name}`}：${f.role}`} hint={f.signature} />
        ))}
        {analysis.diagnostics.map((d, i) => (
          <RepairRow key={i} level={d.level} at={d.at} onRepair={onRepair} target={repairFor(d.at)}
            text={d.message} hint={d.hint || undefined} />
        ))}
      </section>
    </>
  );
}
