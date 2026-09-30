import { useId, useState } from 'react';
import { useStore } from '../store';
import type { Machine, Model, Transition } from '../types';

function label(items: { id: string; label: string }[], id: string): string {
  return items.find((item) => item.id === id)?.label || id;
}

function condition(t: Transition, model: Model): string {
  const on = t.on;
  if (typeof on.event === 'string') return `收到“${label(model.events, on.event)}”事件`;
  if (typeof on.after_ms === 'number') return `在当前状态停留 ${on.after_ms} ms`;
  if (typeof on.signal === 'string') return `${label(model.signals, on.signal)} ${on.op} ${on.value}`;
  if (typeof on.call === 'string') return `${on.call}() 返回真`;
  return '条件无效（请查看模型诊断）';
}

// 坐标只决定显示位置；不对转换排序，也不计算执行计划。
function StateGraph({ machine, selected, transition, select }: {
  machine: Machine; selected: string; transition: string | null; select: (id: string) => void;
}) {
  const marker = useId().replace(/:/g, '');
  const states = machine.states;
  const wildcard = machine.transitions.some((t) => t.from === '*');
  const entries = wildcard ? [...states, { id: '*', label: '任意状态' }] : states;
  const height = Math.max(180, entries.length * 104 + 32);
  const width = Math.max(360, 260 + machine.transitions.length * 28);
  const center = (id: string) => entries.findIndex((s) => s.id === id) * 104 + 64;
  return (
    <div className="machine-graph-scroll" role="region" aria-label="状态关系图，可横向滚动" tabIndex={0}>
      <div className="machine-graph" style={{ width, height }}>
        <svg width={width} height={height} aria-hidden="true">
          <defs>
            <marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" /></marker>
          </defs>
          {machine.transitions.map((t, i) => {
            if (!entries.some((s) => s.id === t.from) || !states.some((s) => s.id === t.to)) return null;
            const y1 = center(t.from) - 12;
            const y2 = center(t.to) + 12;
            const x = 240 + i * 28;
            const middle = (y1 + y2) / 2;
            const active = transition ? transition === t.id : t.from === selected || t.to === selected || t.from === '*';
            return <g key={t.id} className={`machine-edge${active ? ' is-selected' : ''}`}>
              <path d={`M 208 ${y1} H ${x - 12} Q ${x} ${y1} ${x} ${y1 + (y2 > y1 ? 12 : -12)} V ${y2 + (y2 > y1 ? -12 : 12)} Q ${x} ${y2} ${x - 12} ${y2} H 210`} markerEnd={`url(#${marker})`} />
              <circle cx={x} cy={middle} r="11" />
              <text x={x} y={middle} dominantBaseline="central" textAnchor="middle">{i + 1}</text>
            </g>;
          })}
        </svg>
        {entries.map((s, i) => s.id === '*' ? (
          <div key={s.id} className="machine-state machine-any" style={{ top: i * 104 + 32 }}>{s.label}<span className="sub">匹配所有来源</span></div>
        ) : (
          <button key={s.id} type="button" className="machine-state" style={{ top: i * 104 + 32 }} aria-pressed={selected === s.id} onClick={() => select(s.id)}>
            <span className="machine-state-title">{s.label || s.id}{s.id === machine.initial && <span className="machine-initial">初始</span>}</span>
            <span className="id sub">{s.id}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function MachineView({ machine, model }: { machine: Machine; model: Model }) {
  const [stateId, setStateId] = useState(machine.initial);
  const [transitionId, setTransitionId] = useState<string | null>(null);
  const state = machine.states.find((s) => s.id === stateId) ?? machine.states[0];
  const select = (id: string) => { setStateId(id); setTransitionId(null); };
  return <>
    <div className="machine-workspace card">
      <section className="machine-map" aria-label="状态关系">
        <header><h2>状态关系</h2><span className="sub">选择状态查看详情 · 数字对应转换顺序</span></header>
        {machine.states.length ? <StateGraph machine={machine} selected={state?.id ?? ''} transition={transitionId} select={select} /> : <p className="empty">此状态机还没有状态。</p>}
      </section>
      <section className="machine-detail" aria-label="状态详情">
        {state ? <>
          <header><h2>{state.label || state.id}</h2><span className="id sub">{state.id}</span></header>
          <dl>
            <dt>运行的数据流</dt>
            <dd>{state.run?.length ? <ul>{state.run.map((id) => <li key={id}>{label(model.flows, id)} <span className="id sub">{id}</span></li>)}</ul> : '未指定数据流'}</dd>
            <dt>进入时设置信号</dt>
            <dd>{Object.keys(state.set ?? {}).length ? <ul>{Object.entries(state.set).map(([id, value]) => <li key={id}>{label(model.signals, id)} <span className="id">{id} = {String(value)}</span></li>)}</ul> : '无'}</dd>
            <dt>进入后调用</dt><dd className={state.on_enter ? 'id' : undefined}>{state.on_enter ? `${state.on_enter}()` : '无'}</dd>
            <dt>离开前调用</dt><dd className={state.on_exit ? 'id' : undefined}>{state.on_exit ? `${state.on_exit}()` : '无'}</dd>
          </dl>
          <p className="sub machine-note">这里展示模型配置，选中状态不会改变目标运行状态。未受状态机控制的数据流仍按执行计划运行。</p>
        </> : <p className="empty">添加状态后可在这里查看详情。</p>}
      </section>
    </div>
    <section className="card machine-rules" aria-label="转换规则">
      <header><h2>转换规则</h2><span className="sub">按声明顺序评估，第一个匹配生效</span></header>
      {machine.transitions.length === 0 ? <p className="empty">还没有转换规则。应用将保持在初始状态。</p> : (
        <ol>{machine.transitions.map((t, i) => <li key={t.id}>
          <button className="machine-rule" aria-pressed={transitionId === t.id} onClick={() => { setTransitionId(transitionId === t.id ? null : t.id); setStateId(t.to); }}>
            <span className="id sub">{i + 1}</span>
            <span>当 <strong>{condition(t, model)}</strong> 时，从 <strong>{t.from === '*' ? '任意状态' : label(machine.states, t.from)}</strong> 到 <strong>{label(machine.states, t.to)}</strong></span>
            <span className="id sub">{t.id}</span>
          </button>
        </li>)}</ol>
      )}
    </section>
  </>;
}

export function Machines() {
  const { project, analysis } = useStore();
  const [machineId, setMachineId] = useState('');
  if (!project) return null;
  const model = project.model;
  const machine = model.machines.find((m) => m.id === machineId) ?? model.machines[0];
  const diagnostics = analysis?.diagnostics.filter((d) => machine && (d.at === `machines/${machine.id}` || d.at.startsWith(`machines/${machine.id}/`))) ?? [];
  return <>
    <div><h1>状态机</h1><p className="sub">用状态决定哪些数据流运行，用条件决定何时切换。</p></div>
    {!machine ? <section className="card"><p className="empty">还没有状态机。数据流会按执行计划运行；需要工作模式切换时，可在 efw.json 的 machines 中配置后重新载入。</p></section> : <>
      <div className="machine-toolbar">
        <label htmlFor="machine-select">状态机</label>
        <select id="machine-select" className="input" value={machine.id} onChange={(e) => setMachineId(e.target.value)}>
          {model.machines.map((m) => <option key={m.id} value={m.id}>{m.label || m.id} · {m.id}</option>)}
        </select>
        <span className="sub">{machine.states.length} 个状态 · {machine.transitions.length} 条转换</span>
        <span className="sub">模型预览 · 只读</span>
      </div>
      {diagnostics.length > 0 && <section className="card" aria-label="状态机诊断">{diagnostics.map((d, i) => <div key={i} className={`diag ${d.level}`}><div><div>{d.message}</div>{d.hint && <div className="hint">{d.hint}</div>}</div></div>)}</section>}
      <MachineView key={machine.id} machine={machine} model={model} />
    </>}
  </>;
}
