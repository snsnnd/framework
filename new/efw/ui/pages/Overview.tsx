import { ConceptMap } from '../components/ConceptMap';
import { Timeline } from '../components/Timeline';
import { PAGE_LABEL, repairFor, repairForFunction, repairHint, type RepairTarget } from '../focus';
import { useStore, KIND_LABEL } from '../store';
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
  const { project, analysis, debug } = useStore();
  if (!project || !analysis) return <p className="sub">分析中…</p>;
  const m = project.model;
  const missing = analysis.functions.filter((f) => !f.defined || f.mismatch);
  const live = debug.session !== null && !['stopped', 'error', 'ended'].includes(debug.state);
  const manifest = debug.manifest;
  const snap = live ? debug.latest : null;
  const runningState = snap && manifest
    ? m.machines.map((machine) => {
      const now = snap.m?.[machine.id];
      if (!now) return null;
      return `${machine.label} → ${machine.states.find((s) => s.id === now.s)?.label ?? now.s}`;
    }).filter(Boolean).join('；') || null
    : null;

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
        <p className="sub">
          节拍 {m.tick_ms} ms · {m.flows.length} 条数据流 · {m.machines.length} 个状态机
          {debug.session && ` · 正在${KIND_LABEL[debug.kind] ?? debug.kind}运行 ${(debug.t / 1000).toFixed(1)} s`}
        </p>
      </div>

      <section className="card" aria-label="整机怎么跑">
        <header><h2>整机怎么跑</h2><span className="sub">节拍 {m.tick_ms} ms · {analysis.plan.filter((p) => p.kind === 'flow').length} 个数据流任务按槽位顺序执行</span></header>
        <Timeline plan={analysis.plan} tick_ms={m.tick_ms} now={debug.session && !['stopped', 'error', 'ended'].includes(debug.state) ? debug.t : null} />
      </section>

      <section className="card" aria-label="项目结构">
        <header><h2>项目结构</h2><span className="sub">盒子是模型里的对象，连线是真实读写关系；点盒子跳到能编辑它的页面</span></header>
        <ConceptMap model={m} analysis={analysis} running={runningState}
          onOpen={(page, category, item, machine) => onRepair({ page, category, item, machine })} />
      </section>

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
        <section className="card" aria-label="内存估算">
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
