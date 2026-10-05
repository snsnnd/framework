import { useId, useState } from 'react';
import { CellInput } from '../components/CellInput';
import { fail, idProblem, patchItem, removeItem, suggestId } from '../model-edit';
import { useStore } from '../store';
import type { Diagnostic, Machine, Model, State, Transition } from '../types';

const OPS = ['>', '<', '>=', '<=', '==', '!='] as const;
const TRIGGERS = [
  { id: 'event', label: '收到事件' },
  { id: 'after_ms', label: '停留一段时间' },
  { id: 'signal', label: '信号比较' },
  { id: 'call', label: 'C 函数返回真' },
] as const;

function label(items: { id: string; label: string }[], id: string): string {
  return items.find((item) => item.id === id)?.label || id;
}

function triggerOf(on: Record<string, unknown>): string {
  for (const kind of ['event', 'after_ms', 'signal', 'call']) if (kind in on) return kind;
  return 'event';
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

function MachineView({ machine, model, apply, pending, resetToken, errors, setErrors }: {
  machine: Machine; model: Model;
  apply: (mutate: (m: Model) => Model) => Promise<boolean>;
  pending: boolean; resetToken: number; errors: Diagnostic[]; setErrors: (d: Diagnostic[]) => void;
}) {
  const [stateId, setStateId] = useState(machine.initial);
  const [transitionId, setTransitionId] = useState<string | null>(null);
  const [addingState, setAddingState] = useState(false);
  const [stateLabel, setStateLabel] = useState('');
  const [stateNewId, setStateNewId] = useState('');
  const [addingTr, setAddingTr] = useState(false);
  const [trNewId, setTrNewId] = useState('');
  const state = machine.states.find((s) => s.id === stateId) ?? machine.states[0];
  const select = (id: string) => { setStateId(id); setTransitionId(null); };

  const patchMachine = (patch: Record<string, unknown>) => apply((m) => patchItem(m, 'machines', machine.id, patch));
  const patchState = (id: string, patch: Record<string, unknown>) =>
    apply((m) => {
      const target = m.machines.find((x) => x.id === machine.id);
      if (!target) return m;
      return patchItem(m, 'machines', machine.id, {
        states: target.states.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      });
    });
  const patchTransition = (id: string, patch: Record<string, unknown>) =>
    apply((m) => {
      const target = m.machines.find((x) => x.id === machine.id);
      if (!target) return m;
      return patchItem(m, 'machines', machine.id, {
        transitions: target.transitions.map((t) => (t.id === id ? { ...t, ...patch } : t)),
      });
    });
  function moveTransition(id: string, delta: number) {
    return apply((m) => {
      const target = m.machines.find((x) => x.id === machine.id);
      if (!target) return m;
      const list = [...target.transitions];
      const index = list.findIndex((t) => t.id === id);
      const to = index + delta;
      if (index < 0 || to < 0 || to >= list.length) return m;
      [list[index], list[to]] = [list[to], list[index]];
      return patchItem(m, 'machines', machine.id, { transitions: list });
    });
  }
  function removeState(id: string) {
    const usedBy = machine.transitions.filter((t) => t.from === id || t.to === id);
    if (usedBy.length) {
      setErrors(fail(`状态“${id}”仍在转换规则里`, `涉及的规则：${usedBy.map((t) => t.id).join('、')}；先改或删除它们`));
      return;
    }
    void apply((m) => {
      const target = m.machines.find((x) => x.id === machine.id);
      if (!target) return m;
      const next = patchItem(m, 'machines', machine.id, { states: target.states.filter((s) => s.id !== id) });
      const updated = next.machines.find((x) => x.id === machine.id);
      return updated && updated.initial === id
        ? patchItem(next, 'machines', machine.id, { initial: updated.states[0]?.id ?? '' })
        : next;
    }).then((ok) => { if (ok) { setStateId(''); setAddingState(false); } });
  }
  function removeTransition(id: string) {
    void apply((m) => {
      const target = m.machines.find((x) => x.id === machine.id);
      if (!target) return m;
      return patchItem(m, 'machines', machine.id, { transitions: target.transitions.filter((t) => t.id !== id) });
    }).then((ok) => { if (ok) setTransitionId(null); });
  }
  function addState() {
    const problem = idProblem(stateNewId, machine.states.map((s) => s.id));
    if (problem) { setErrors(fail(problem)); return; }
    void apply((m) => {
      const target = m.machines.find((x) => x.id === machine.id);
      if (!target) return m;
      const fresh: State = { id: stateNewId, label: stateLabel || stateNewId, run: [], set: {} };
      const withState = patchItem(m, 'machines', machine.id, { states: [...target.states, fresh] });
      return target.states.length ? withState : patchItem(withState, 'machines', machine.id, { initial: stateNewId });
    }).then((ok) => {
      if (!ok) return;
      setAddingState(false); setStateLabel(''); setStateNewId(''); setStateId(stateNewId);
    });
  }
  function addTransition() {
    const problem = idProblem(trNewId, machine.transitions.map((t) => t.id));
    if (problem) { setErrors(fail(problem)); return; }
    if (!machine.states.length) { setErrors(fail('先添加状态，再添加转换')); return; }
    void apply((m) => {
      const target = m.machines.find((x) => x.id === machine.id);
      if (!target) return m;
      const from = machine.initial || machine.states[0].id;
      const to = machine.states.find((s) => s.id !== from)?.id ?? from;
      const on = model.events.length ? { event: model.events[0].id } : { after_ms: 1000 };
      return patchItem(m, 'machines', machine.id, {
        transitions: [...target.transitions, { id: trNewId, from, to, on }],
      });
    }).then((ok) => { if (ok) { setAddingTr(false); setTrNewId(''); setTransitionId(trNewId); } });
  }
  function setTrigger(id: string, kind: string) {
    const on = kind === 'event' ? { event: model.events[0]?.id ?? '' }
      : kind === 'after_ms' ? { after_ms: 1000 }
        : kind === 'signal' ? { signal: model.signals[0]?.id ?? '', op: '>', value: 0 }
          : { call: `${machine.id}_cond` };
    patchTransition(id, { on });
  }

  return <>
    <div className="machine-workspace card">
      <section className="machine-map" aria-label="状态关系">
        <header><h2>状态关系</h2><span className="sub">点击状态查看详情 · 数字对应转换顺序</span></header>
        {machine.states.length ? <StateGraph machine={machine} selected={state?.id ?? ''} transition={transitionId} select={select} />
          : <p className="empty">此状态机还没有状态。</p>}
        <div className="step-add">
          {addingState ? <>
            <CellInput liveCommit label="新状态名称" value={stateLabel} onCommit={setStateLabel} placeholder="名称" />
            <CellInput liveCommit label="新状态标识符" value={stateNewId} onCommit={setStateNewId} className="mono" />
            <button className="btn primary" disabled={pending} onClick={addState}>添加</button>
            <button className="btn" onClick={() => setAddingState(false)}>取消</button>
          </> : <button className="btn" disabled={pending} onClick={() => { setAddingState(true); setStateNewId(suggestId('state', machine.states.map((s) => s.id))); }}>新增状态</button>}
        </div>
      </section>
      <section className="machine-detail" aria-label="状态详情">
        {state ? <>
          <header>
            <h2>{state.label || state.id}</h2><span className="id sub">{state.id}</span>
            <span className="spacer" />
            <button className="btn" disabled={pending || machine.initial === state.id} title={machine.initial === state.id ? '当前已是初始状态' : '设为初始状态'}
              onClick={() => void patchMachine({ initial: state.id })}>设为初始</button>
            <button className="btn danger" disabled={pending} onClick={() => removeState(state.id)}>删除</button>
          </header>
          <div className="body">
            <label className="step-field"><span className="sub">名称</span>
              <CellInput resetKey={resetToken} label={`${state.id} 名称`} value={state.label || state.id} onCommit={(raw) => patchState(state.id, { label: raw })} />
            </label>
            <h3 className="detail-h">运行的数据流</h3>
            {model.flows.length ? <ul className="check-list">{model.flows.map((flow) => {
              const controlled = model.machines.find((mc) => mc.id !== machine.id && mc.states.some((s) => s.run.includes(flow.id)));
              const on = state.run?.includes(flow.id) ?? false;
              return <li key={flow.id}>
                <label>
                  <input type="checkbox" checked={on} disabled={pending || !!controlled}
                    aria-label={`${machine.id} ${state.id} 运行 ${flow.id}`}
                    onChange={(e) => patchState(state.id, {
                      run: e.target.checked ? [...(state.run ?? []), flow.id] : (state.run ?? []).filter((id) => id !== flow.id),
                    })} />
                  {flow.label || flow.id} <span className="id sub">{flow.id}</span>
                  {controlled && <span className="sub">（已由 {controlled.label || controlled.id} 控制）</span>}
                </label>
              </li>;
            })}</ul> : <p className="sub">还没有数据流。</p>}
            <h3 className="detail-h">进入时设置信号</h3>
            {model.signals.length ? <div className="set-editor">
              {model.signals.map((signal) => {
                const current = state.set?.[signal.id];
                return <div key={signal.id} className="set-row">
                  <span className="sub">{signal.label || signal.id}</span>
                  <CellInput resetKey={resetToken} label={`${state.id} 设置 ${signal.id}`} kind="number" step="any"
                    value={current ?? signal.init} disabled={pending || current === undefined}
                    onCommit={(raw) => patchState(state.id, { set: { ...(state.set ?? {}), [signal.id]: Number(raw) } })} />
                  <button className="btn ghost" disabled={pending || current === undefined} aria-label={`${state.id} 取消设置 ${signal.id}`}
                    onClick={() => { const next = { ...(state.set ?? {}) }; delete next[signal.id]; void patchState(state.id, { set: next }); }}>×</button>
                </div>;
              })}
              <button className="btn" disabled={pending || Object.keys(state.set ?? {}).length >= model.signals.length}
                onClick={() => patchState(state.id, { set: { ...(state.set ?? {}), [model.signals[0].id]: model.signals[0].init } })}>添加设置</button>
            </div> : <p className="sub">还没有信号。</p>}
            <h3 className="detail-h">钩子函数</h3>
            <div className="row">
              <CellInput resetKey={resetToken} label={`${state.id} on_enter`} value={state.on_enter ?? ''} placeholder="进入时调用"
                onCommit={(raw) => patchState(state.id, { on_enter: raw })} />
              <CellInput resetKey={resetToken} label={`${state.id} on_exit`} value={state.on_exit ?? ''} placeholder="离开时调用"
                onCommit={(raw) => patchState(state.id, { on_exit: raw })} />
            </div>
            <p className="sub machine-note">这里配置的是模型；选中状态不会改变目标的运行状态。未被任何状态机控制的数据流按执行计划一直运行。</p>
          </div>
        </> : <p className="empty">添加状态后可在这里查看详情。</p>}
      </section>
    </div>

    <section className="card machine-rules" aria-label="转换规则">
      <header>
        <span className="sub">按声明顺序评估，第一个匹配生效</span>
        <div className="step-add" style={{ padding: 0, borderTop: 0 }}>
          {addingTr ? <>
            <CellInput liveCommit label="新转换标识符" value={trNewId} onCommit={setTrNewId} className="mono" />
            <button className="btn primary" disabled={pending} onClick={addTransition}>添加</button>
            <button className="btn" onClick={() => setAddingTr(false)}>取消</button>
          </> : <button className="btn" disabled={pending || !machine.states.length} onClick={() => { setAddingTr(true); setTrNewId(suggestId('tr', machine.transitions.map((t) => t.id))); }}>新增转换</button>}
        </div>
      </header>
      {machine.transitions.length === 0 && !addingTr ? <p className="empty">还没有转换规则。应用将保持在初始状态。</p> : (
        <ol>{machine.transitions.map((t, i) => {
          const open = transitionId === t.id;
          const kind = triggerOf(t.on);
          return <li key={t.id} data-id={t.id} className={open ? 'is-open' : undefined}>
            <button className="machine-rule" aria-pressed={open} onClick={() => { setTransitionId(open ? null : t.id); setStateId(t.to); }}>
              <span className="id sub">{i + 1}</span>
              <span>当 <strong>{condition(t, model)}</strong> 时，从 <strong>{t.from === '*' ? '任意状态' : label(machine.states, t.from)}</strong> 到 <strong>{label(machine.states, t.to)}</strong></span>
              <span className="id sub">{t.id}</span>
            </button>
            {open && <div className="tr-editor">
              <label className="step-field"><span className="sub">起点</span>
                <CellInput resetKey={resetToken} label={`${t.id} 起点`} kind="select" value={t.from}
                  options={[{ value: '*', label: '任意状态' }, ...machine.states.map((s) => ({ value: s.id, label: `${s.label || s.id} · ${s.id}` }))]}
                  onCommit={(raw) => patchTransition(t.id, { from: raw })} />
              </label>
              <label className="step-field"><span className="sub">终点</span>
                <CellInput resetKey={resetToken} label={`${t.id} 终点`} kind="select" value={t.to}
                  options={machine.states.map((s) => ({ value: s.id, label: `${s.label || s.id} · ${s.id}` }))}
                  onCommit={(raw) => patchTransition(t.id, { to: raw })} />
              </label>
              <label className="step-field"><span className="sub">触发方式</span>
                <CellInput resetKey={resetToken} label={`${t.id} 触发方式`} kind="select" value={kind}
                  options={TRIGGERS.map((x) => ({ value: x.id, label: x.label }))}
                  onCommit={(raw) => setTrigger(t.id, raw)} />
              </label>
              {kind === 'event' && <label className="step-field"><span className="sub">事件</span>
                <CellInput resetKey={resetToken} label={`${t.id} 事件`} kind="select" value={String(t.on.event ?? '')}
                  options={model.events.map((e) => ({ value: e.id, label: `${e.label || e.id} · ${e.id}` }))}
                  onCommit={(raw) => patchTransition(t.id, { on: { event: raw } })} />
              </label>}
              {kind === 'after_ms' && <label className="step-field"><span className="sub">毫秒</span>
                <CellInput resetKey={resetToken} label={`${t.id} 停留毫秒`} kind="number" min={1} value={Number(t.on.after_ms ?? 1000)}
                  onCommit={(raw) => patchTransition(t.id, { on: { after_ms: Math.max(1, Number(raw)) } })} />
              </label>}
              {kind === 'signal' && <>
                <label className="step-field"><span className="sub">信号</span>
                  <CellInput resetKey={resetToken} label={`${t.id} 信号`} kind="select" value={String(t.on.signal ?? '')}
                    options={model.signals.map((s) => ({ value: s.id, label: `${s.label || s.id} · ${s.id}` }))}
                    onCommit={(raw) => patchTransition(t.id, { on: { ...t.on, signal: raw } })} />
                </label>
                <label className="step-field"><span className="sub">比较</span>
                  <CellInput resetKey={resetToken} label={`${t.id} 比较符`} kind="select" value={String(t.on.op ?? '>')}
                    options={OPS.map((op) => ({ value: op, label: op }))}
                    onCommit={(raw) => patchTransition(t.id, { on: { ...t.on, op: raw } })} />
                </label>
                <label className="step-field"><span className="sub">数值</span>
                  <CellInput resetKey={resetToken} label={`${t.id} 数值`} kind="number" step="any" value={Number(t.on.value ?? 0)}
                    onCommit={(raw) => patchTransition(t.id, { on: { ...t.on, value: Number(raw) } })} />
                </label>
              </>}
              {kind === 'call' && <label className="step-field"><span className="sub">条件函数</span>
                <CellInput resetKey={resetToken} label={`${t.id} 条件函数`} value={String(t.on.call ?? '')} placeholder="返回非 0 触发"
                  onCommit={(raw) => patchTransition(t.id, { on: { call: raw } })} />
              </label>}
              <div className="row">
                <button className="btn" disabled={pending || i === 0} aria-label={`${t.id} 上移`} onClick={() => moveTransition(t.id, -1)}>上移</button>
                <button className="btn" disabled={pending || i === machine.transitions.length - 1} aria-label={`${t.id} 下移`} onClick={() => moveTransition(t.id, 1)}>下移</button>
                <button className="btn danger" aria-label={`${t.id} 删除`} disabled={pending} onClick={() => removeTransition(t.id)}>删除</button>
              </div>
            </div>}
          </li>;
        })}</ol>
      )}
      {errors.length > 0 && <div className="body">{errors.map((d, i) => <p key={i} className="err-text">{d.message}{d.hint ? ` — ${d.hint}` : ''}</p>)}</div>}
    </section>
  </>;
}

export function Machines() {
  const { project, analysis, updateModel } = useStore();
  const [machineId, setMachineId] = useState('');
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<Diagnostic[]>([]);
  const [resetToken, setResetToken] = useState(0);
  if (!project) return null;
  const model = project.model;
  const machine = model.machines.find((m) => m.id === machineId) ?? model.machines[0];
  const diagnostics = analysis?.diagnostics.filter((d) => machine && (d.at === `machines/${machine.id}` || d.at.startsWith(`machines/${machine.id}/`))) ?? [];

  async function apply(mutate: (m: Model) => Model) {
    setPending(true);
    try {
      const result = await updateModel(mutate);
      setErrors(result.diagnostics);
      if (!result.ok) setResetToken((token) => token + 1);
      return result.ok;
    } catch (e) {
      setErrors(fail((e as Error).message));
      setResetToken((token) => token + 1);
      return false;
    } finally {
      setPending(false);
    }
  }

  return <>
    <div><h1>状态机</h1><p className="sub">用状态决定哪些数据流运行，用条件决定何时切换。</p></div>
    {!machine ? <section className="card"><p className="empty">还没有状态机。数据流会按执行计划运行；需要工作模式切换时，可在 efw.json 的 machines 中配置后重新载入。</p></section> : <>
      <div className="machine-toolbar">
        <label htmlFor="machine-select">状态机</label>
        <select id="machine-select" className="input" value={machine.id} onChange={(e) => { setMachineId(e.target.value); setErrors([]); }}>
          {model.machines.map((m) => <option key={m.id} value={m.id}>{m.label || m.id} · {m.id}</option>)}
        </select>
        <span className="sub">{machine.states.length} 个状态 · {machine.transitions.length} 条转换</span>
        <span className="sub">直接编辑，保存后其他页面按新模型刷新</span>
      </div>
      {diagnostics.length > 0 && <section className="card" aria-label="状态机诊断">{diagnostics.map((d, i) => <div key={i} className={`diag ${d.level}`}><div><div>{d.message}</div>{d.hint && <div className="hint">{d.hint}</div>}</div></div>)}</section>}
      <MachineView key={machine.id} machine={machine} model={model} apply={apply} pending={pending} resetToken={resetToken} errors={errors} setErrors={setErrors} />
    </>}
  </>;
}