import { useState } from 'react';
import { CellInput } from '../components/CellInput';
import {
  appendItem, diagPrefix, fail, idProblem, ITEMS, newItem, patchItem, POLICY_LABEL, POLICIES, refGroups,
  removeItem, suggestId, TYPES, type Category,
} from '../model-edit';
import { useStore } from '../store';
import type { Diagnostic, IoPoint, Model, Queue, Signal, Sim, SimSpec, UsageRef } from '../types';

const CATEGORIES = [
  { id: 'signals', label: '信号', memory: '信号', prefix: 'signal' },
  { id: 'inputs', label: '输入', memory: '输出缓存与强制值', prefix: 'input' },
  { id: 'outputs', label: '输出', memory: '输出缓存与强制值', prefix: 'output' },
  { id: 'events', label: '事件', memory: '事件队列', prefix: 'event' },
  { id: 'queues', label: '队列', memory: '用户队列', prefix: 'queue' },
] as const;
function isIoCategory(c: Category): c is 'inputs' | 'outputs' { return c === 'inputs' || c === 'outputs'; }
const TYPE_OPTIONS = TYPES.map((t) => ({ value: t, label: t }));
const ITEM_OPTIONS = ITEMS.map((t) => ({ value: t, label: t }));
const POLICY_OPTIONS = POLICIES.map((p) => ({ value: p, label: POLICY_LABEL[p] }));

/** 输入的虚拟仿真：类型与字段表全部来自后端 sim_specs，界面不自行推导。 */
function SimEditor({ point, specs, model, resetKey, onCommit }: {
  point: IoPoint; specs: SimSpec[]; model: Model; resetKey: number; onCommit: (sim: Sim | undefined) => void;
}) {
  const enabled = !!point.sim;
  const spec = specs.find((s) => s.kind === point.sim?.kind);
  return <div className="sim-editor">
    <label className="tune-toggle">
      <input type="checkbox" checked={enabled} onChange={(e) => onCommit(e.target.checked ? { kind: 'const', value: 0 } : undefined)} />
      虚拟目标里自动产生这个输入
    </label>
    {!enabled && <p className="sub">关闭时虚拟目标读到 0；真机目标由 <span className="id">board/io.c</span> 里的 <span className="id">{point.id}_read()</span> 提供。</p>}
    {enabled && spec && <ul className="sim-fields">
      <li><CellInput resetKey={resetKey} label={`${point.id} 仿真类型`} kind="select"
        options={specs.map((s) => ({ value: s.kind, label: s.label }))} value={spec.kind}
        onCommit={(raw) => onCommit({ kind: raw, ...defaults(specs.find((s) => s.kind === raw), model.outputs) })} /></li>
      {spec.fields.map((f) => <li key={f.name}>
        <span className="sub">{f.label}</span>
        {f.role === 'output'
          ? <CellInput resetKey={resetKey} label={`${point.id} ${f.label}`} kind="select"
              options={model.outputs.map((o) => ({ value: o.id, label: o.label || o.id }))}
              value={String(point.sim?.[f.name] ?? '')}
              onCommit={(raw) => onCommit({ ...(point.sim as Sim), [f.name]: raw })} />
          : <CellInput resetKey={resetKey} label={`${point.id} ${f.label}`} kind="number" step="any"
              min={f.min ?? undefined} value={Number(point.sim?.[f.name] ?? f.default ?? 0)}
              onCommit={(raw) => onCommit({ ...(point.sim as Sim), [f.name]: Number(raw) })} />}
      </li>)}
    </ul>}
    {enabled && !spec && <p className="sub">这个输入的仿真类型不在后端可用列表里，请重新选择。</p>}
  </div>;
}

/** 切换仿真类型时预填默认值（含跟随的输出），否则会被后端拒绝而无法完成配置。 */
function defaults(spec: SimSpec | undefined, outputs: IoPoint[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of spec?.fields ?? []) {
    if (f.role === 'output') out[f.name] = outputs[0]?.id ?? '';
    else out[f.name] = f.default ?? 0;
  }
  return out;
}

function References({ refs, model }: { refs: UsageRef[]; model: Model }) {
  if (!refs.length) return <p className="sub">未发现模型内引用</p>;
  return <ul className="comm-refs">{refs.map((ref, i) => {
    if ('flow' in ref) {
      const flow = model.flows.find((f) => f.id === ref.flow);
      return <li key={i}><span>数据流 · {flow?.label || ref.flow}</span><code>{ref.flow} / {ref.step}</code></li>;
    }
    const machine = model.machines.find((m) => m.id === ref.machine);
    const child = 'state' in ref ? ref.state : ref.transition;
    const name = 'state' in ref ? machine?.states.find((s) => s.id === child)?.label || child : child;
    return <li key={i}><span>状态机 · {machine?.label || ref.machine} · {'state' in ref ? '状态' : '转换'} {name}</span><code>{ref.machine} / {child}</code></li>;
  })}</ul>;
}

export function Communication() {
  const { project, analysis, updateModel } = useStore();
  const [category, setCategory] = useState<Category>('signals');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<Diagnostic[]>([]);
  const [adding, setAdding] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const [newId, setNewId] = useState('');
  const [confirmId, setConfirmId] = useState('');
  const [resetToken, setResetToken] = useState(0);
  if (!project) return null;
  const model = project.model;
  const meta = CATEGORIES.find((c) => c.id === category)!;
  const all = model[category];
  const taken = all.map((item) => item.id);
  const search = query.trim().toLocaleLowerCase();
  const visible = all.filter((item) => `${item.label} ${item.id}`.toLocaleLowerCase().includes(search));
  const selected = visible.find((item) => item.id === selectedId) ?? visible[0];
  const signal = category === 'signals' ? model.signals.find((s) => s.id === selected?.id) : undefined;
  const queue = category === 'queues' ? model.queues.find((q) => q.id === selected?.id) : undefined;
  const isIo = isIoCategory(category);
  const io = isIo ? model[category].find((x) => x.id === selected?.id) : undefined;
  const ioFns = io ? analysis?.functions.filter((f) => f.owner === `${category}/${io.id}`) ?? [] : [];
  const memory = analysis?.memory.parts.find((p) => p.name === meta.memory);
  const groups = selected ? refGroups(analysis, category, selected.id) : [];
  const diagnostics = selected
    ? analysis?.diagnostics.filter((d) => d.at.startsWith(diagPrefix(category, selected.id))) ?? []
    : [];

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

  function editSignal(id: string, patch: Partial<Signal>) {
    return apply((m) => patchItem(m, 'signals', id, patch as Record<string, unknown>));
  }
  function editTune(id: string, field: 'min' | 'max', value: number) {
    return apply((m) => {
      const signal = m.signals.find((s) => s.id === id);
      if (!signal?.tune) return m;
      return patchItem(m, 'signals', id, { tune: { ...signal.tune, [field]: value } });
    });
  }
  function editQueue(id: string, patch: Partial<Queue>) {
    return apply((m) => patchItem(m, 'queues', id, patch as Record<string, unknown>));
  }
  function editEvent(id: string, label: string) {
    return apply((m) => patchItem(m, 'events', id, { label }));
  }
  function editIo(id: string, patch: Partial<IoPoint>) {
    return apply((m) => patchItem(m, category as 'inputs' | 'outputs', id, patch as Record<string, unknown>));
  }
  function remove(id: string) {
    const refs = refGroups(analysis, category, id).flatMap((g) => g.refs);
    if (refs.length) {
      setErrors(fail(`${meta.label}“${id}”仍被引用，不能删除`, `先改这些位置：${refs.slice(0, 3).map((r) => ('flow' in r ? `数据流 ${r.flow}/${r.step}` : `状态机 ${r.machine}`)).join('、')}`));
      setConfirmId('');
      return;
    }
    void apply((m) => removeItem(m, category, id)).then((ok) => { if (ok) { setSelectedId(''); setConfirmId(''); } });
  }
  function add() {
    const problem = idProblem(newId, taken);
    if (problem) { setErrors(fail(problem)); return; }
    void apply((m) => appendItem(m, category, newItem(category, newId, newLabel))).then((ok) => {
      if (!ok) return;
      setAdding(false); setNewLabel(''); setNewId(''); setSelectedId(newId);
    });
  }
  function startAdd() {
    setAdding(true);
    setErrors([]);
    setNewLabel('');
    setNewId(suggestId(meta.prefix, taken));
  }
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

  return <>
    <div><h1>通信</h1><p className="sub">共享信号、事件和队列。直接在这里编辑，保存后所有页面按新模型刷新。</p></div>
    {errors.map((d, i) => <div key={i} className="diag error" role="alert"><div>{d.message}{d.hint && <p className="hint">{d.hint}</p>}</div></div>)}
    <div className="comm-toolbar">
      <div className="comm-categories" role="group" aria-label="通信分类">
        {CATEGORIES.map((c) => <button key={c.id} className="btn" aria-pressed={category === c.id} onClick={() => { setCategory(c.id); setQuery(''); setSelectedId(''); setErrors([]); setAdding(false); }}>{c.label} <span className="id">{model[c.id].length}</span></button>)}
      </div>
      <label className="comm-search">查找<input className="input" type="search" placeholder="名称或标识符" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
    </div>
    <section className="card" aria-label={`${meta.label}列表`}>
      <header>
        <span className="sub">{memory ? `${meta.memory}内存估算 ${memory.bytes} B` : '内存估算暂不可用'} · 全部{meta.label}</span>
        <button className="btn" onClick={startAdd} disabled={pending}>新增{meta.label}</button>
      </header>
      {category === 'events' && <p className="comm-note sub">事件不携带数据，共用事件队列。{model.limits?.event_queue !== undefined ? `配置容量 ${model.limits.event_queue} 条；` : '容量使用后端默认值；'}队列满时丢弃最新事件。</p>}
      {isIo && <p className="comm-note sub">{category === 'inputs' ? '输入是硬件读到的量，虚拟目标下可用下方的仿真设置代替硬件。' : '输出是写到硬件的值，调试页可以强制它。'}删除前要先改掉引用它的步骤；后端会拒绝仍被引用的删除。</p>}
      {!all.length && !adding ? <p className="empty">还没有{meta.label}。点“新增{meta.label}”创建，或在 efw.json 里配置后重新载入。</p>
        : !visible.length && !adding ? <div className="empty"><p>没有匹配的{meta.label}。</p><button className="btn" onClick={() => setQuery('')}>清除搜索</button></div>
          : <div className="comm-table-scroll" role="region" aria-label={`${meta.label}表格，可横向滚动`} tabIndex={0}>
            <table className="comm-table">
              <thead><tr><th scope="col">名称</th><th scope="col">标识符</th>
                {category === 'signals' ? <><th scope="col">类型</th><th scope="col">初始值</th><th scope="col">单位</th><th scope="col">可整定范围</th></>
                  : category === 'queues' ? <><th scope="col">元素类型</th><th scope="col">容量（条）</th><th scope="col">队列满时</th></>
                    : isIo ? <><th scope="col">类型</th><th scope="col">单位</th><th scope="col">虚拟仿真</th></>
                      : <th scope="col">用途</th>}
                <th scope="col">操作</th></tr></thead>
              <tbody>
                {visible.map((item) => {
                  const s = category === 'signals' ? model.signals.find((x) => x.id === item.id) : undefined;
                  const q = category === 'queues' ? model.queues.find((x) => x.id === item.id) : undefined;
                  const p = isIo ? model[category].find((x) => x.id === item.id) : undefined;
                  return <tr key={item.id} data-id={item.id} className={selected?.id === item.id ? 'is-selected' : undefined} onClick={() => setSelectedId(item.id)}>
                    <td><CellInput resetKey={resetToken} label={`${item.label || item.id} 名称`} value={item.label || item.id}
                      onCommit={(raw) => (s ? editSignal(item.id, { label: raw }) : q ? editQueue(item.id, { label: raw }) : io ? editIo(item.id, { label: raw }) : editEvent(item.id, raw))} /></td>
                    <td><span className="id sub" title="标识符决定生成的 C 名字，创建后不可修改">{item.id}</span></td>
                    {s ? <>
                      <td><CellInput resetKey={resetToken} label={`${s.id} 类型`} kind="select" options={TYPE_OPTIONS} value={s.type} onCommit={(raw) => editSignal(item.id, { type: raw as Signal['type'] })} /></td>
                      <td><CellInput resetKey={resetToken} label={`${s.id} 初始值`} kind="number" step="any" value={s.init} onCommit={(raw) => editSignal(item.id, { init: Number(raw) })} /></td>
                      <td><CellInput resetKey={resetToken} label={`${s.id} 单位`} value={s.unit} onCommit={(raw) => editSignal(item.id, { unit: raw })} /></td>
                      <td className="tune-cell">
                        <span className="tune-toggle">
                          <input id={`tune-${item.id}`} type="checkbox" checked={!!s.tune}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => editSignal(item.id, { tune: e.target.checked ? { min: 0, max: 100 } : null })} />
                          <label htmlFor={`tune-${item.id}`}>可整定</label>
                        </span>
                        {s.tune && <span className="tune-range">
                          <CellInput resetKey={resetToken} label={`${s.id} 整定下限`} kind="number" step="any" value={s.tune.min} onCommit={(raw) => editTune(item.id, 'min', Number(raw))} />
                          <span className="sub">～</span>
                          <CellInput resetKey={resetToken} label={`${s.id} 整定上限`} kind="number" step="any" value={s.tune.max} onCommit={(raw) => editTune(item.id, 'max', Number(raw))} />
                        </span>}
                      </td>
                    </> : p ? <>
                      <td><CellInput resetKey={resetToken} label={`${p.id} 类型`} kind="select" options={TYPE_OPTIONS} value={p.type} onCommit={(raw) => editIo(item.id, { type: raw as IoPoint['type'] })} /></td>
                      <td><CellInput resetKey={resetToken} label={`${p.id} 单位`} value={p.unit} onCommit={(raw) => editIo(item.id, { unit: raw })} /></td>
                      <td className="sub">{p.sim ? (analysis?.sim_specs ?? []).find((x) => x.kind === p.sim?.kind)?.label ?? p.sim.kind : '由 C 提供'}</td>
                    </> : q ? <>
                      <td><CellInput resetKey={resetToken} label={`${q.id} 元素类型`} kind="select" options={ITEM_OPTIONS} value={q.item} onCommit={(raw) => editQueue(item.id, { item: raw as Queue['item'] })} /></td>
                      <td><CellInput resetKey={resetToken} label={`${q.id} 容量`} kind="number" value={q.capacity} min={1} max={1024} onCommit={(raw) => editQueue(item.id, { capacity: Number(raw) })} /></td>
                      <td><CellInput resetKey={resetToken} label={`${q.id} 满队策略`} kind="select" options={POLICY_OPTIONS} value={q.policy} onCommit={(raw) => editQueue(item.id, { policy: raw as Queue['policy'] })} /></td>
                    </> : <td className="sub">通知状态机，无数据载荷</td>}
                    <td>{confirmId === item.id
                      ? <span className="row"><button className="btn danger" onClick={(e) => { stop(e); remove(item.id); }}>确认删除</button><button className="btn" onClick={(e) => { stop(e); setConfirmId(''); }}>取消</button></span>
                      : <button className="btn" disabled={pending} onClick={(e) => { stop(e); setConfirmId(item.id); setErrors([]); }}>删除</button>}</td>
                  </tr>;
                })}
                {adding && <tr className="adding-row" data-id="new">
                  <td><CellInput resetKey={resetToken} liveCommit label="新名称" value={newLabel} onCommit={setNewLabel} placeholder="名称" /></td>
                  <td><CellInput resetKey={resetToken} liveCommit label="新标识符" value={newId} onCommit={setNewId} className="mono" /></td>
                  {category === 'signals' ? <><td className="sub">float</td><td>0</td><td>—</td><td className="sub">默认不可整定</td></>
                    : category === 'queues' ? <><td className="sub">uint16_t</td><td>8</td><td className="sub">{POLICY_LABEL.drop_oldest}</td></>
                      : isIo ? <><td className="sub">float</td><td>—</td><td className="sub">{category === 'inputs' ? '恒定值 0' : '—'}</td></>
                        : <td className="sub">通知状态机</td>}
                  <td><span className="row"><button className="btn primary" onClick={add} disabled={pending}>添加</button><button className="btn" onClick={() => setAdding(false)}>取消</button></span></td>
                </tr>}
              </tbody>
            </table>
          </div>}
    </section>
    {selected && <section className="card comm-details" aria-label="通信详情">
      <header><h2>{selected.label || selected.id}</h2><span className="id sub">{selected.id}</span></header>
      {io ? <div className="body comm-io">
        <p>{category === 'inputs' ? '硬件或仿真产生的值，用“读取”步骤取进数据流。' : '数据流用“写入”步骤驱动这里，真机上对应 board/io.c 的输出函数。'}</p>
        {category === 'inputs' ? <SimEditor point={io} specs={analysis?.sim_specs ?? []} model={model} resetKey={resetToken}
          onCommit={(sim) => editIo(io.id, { sim })} /> : <p className="sub">输出的取值来自数据流的“写入”步骤，没有仿真设置。</p>}
        <div className="comm-io-fns">
          <h3>需要你实现的 C 函数</h3>
          <ul>{ioFns.map((f) => <li key={f.name}><code>{f.signature}</code> <span className="sub">在 {f.file}</span>{' '}
            <span className={`chip ${f.defined ? 'ok' : 'warn'}`}>{f.defined ? '已实现' : '未实现'}</span></li>)}</ul>
        </div>
      </div> : queue ? <div className="body">
        <p>最多保存 <span className="id">{queue.capacity}</span> 条 <span className="id">{queue.item}</span> 数据，队列满时{POLICY_LABEL[queue.policy] ?? queue.policy}。</p>
        <p className="sub">队列通过用户 C 函数收发，当前分析接口未提供队列的生产者、消费者与逐队列内存。上方显示全部用户队列的内存估算；运行时深度与丢包数将在调试页查看。删除队列不会检查用户 C 代码是否还在调用它。</p>
      </div> : groups.length === 0 ? <p className="empty">模型内没有引用这个{meta.label}。用户 C 代码里的访问不在此列。</p> : <>
        <div className="comm-relations">
          {groups.map((group) => <div key={group.role}><h3>{group.role}</h3><References refs={group.refs} model={model} /></div>)}
        </div>
        <p className="comm-note sub">引用来自后端模型分析；用户 C 代码中未声明的访问不在此列。{signal ? '表格里的初始值不是运行时采样值。' : '调试页也可以直接发出事件。'}</p>
      </>}
      {diagnostics.map((d, i) => <div key={i} className={`diag ${d.level}`}><div><div>{d.message}</div>{d.hint && <div className="hint">{d.hint}</div>}</div></div>)}
    </section>}
  </>;
}