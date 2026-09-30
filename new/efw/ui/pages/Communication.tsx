import { useState } from 'react';
import { useStore } from '../store';
import type { Model, UsageRef } from '../types';

const CATEGORIES = [
  { id: 'signals', label: '信号', memory: '信号' },
  { id: 'events', label: '事件', memory: '事件队列' },
  { id: 'queues', label: '队列', memory: '用户队列' },
] as const;
type Category = typeof CATEGORIES[number]['id'];
const POLICIES: Record<string, string> = { drop_oldest: '丢弃最旧', drop_newest: '丢弃最新' };

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
  const { project, analysis } = useStore();
  const [category, setCategory] = useState<Category>('signals');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState('');
  if (!project) return null;
  const model = project.model;
  const meta = CATEGORIES.find((c) => c.id === category)!;
  const all = model[category];
  const search = query.trim().toLocaleLowerCase();
  const visible = all.filter((item) => `${item.label} ${item.id}`.toLocaleLowerCase().includes(search));
  const selected = visible.find((item) => item.id === selectedId) ?? visible[0];
  const signal = category === 'signals' ? model.signals.find((s) => s.id === selected?.id) : undefined;
  const queue = category === 'queues' ? model.queues.find((q) => q.id === selected?.id) : undefined;
  const memory = analysis?.memory.parts.find((p) => p.name === meta.memory);
  const usage = category === 'signals' ? analysis?.usage.signals : analysis?.usage.events;
  const signalUsage = signal && analysis?.usage.signals?.[signal.id];
  const eventUsage = selected && analysis?.usage.events?.[selected.id];
  const diagnostics = selected ? analysis?.diagnostics.filter((d) => d.at === `${category}/${selected.id}` || d.at.startsWith(`${category}/${selected.id}/`)) ?? [] : [];
  return <>
    <div><h1>通信</h1><p className="sub">查看共享信号、事件和队列，了解数据由谁写入、由谁使用。</p></div>
    <div className="comm-toolbar">
      <div className="comm-categories" role="group" aria-label="通信分类">
        {CATEGORIES.map((c) => <button key={c.id} className="btn" aria-pressed={category === c.id} onClick={() => { setCategory(c.id); setQuery(''); setSelectedId(''); }}>{c.label} <span className="id">{model[c.id].length}</span></button>)}
      </div>
      <label className="comm-search">查找<input className="input" type="search" placeholder="名称或标识符" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
    </div>
    <section className="card" aria-label={`${meta.label}列表`}>
      <header><h2>{meta.label}配置</h2><span className="sub">{memory ? `${meta.memory}内存估算 ${memory.bytes} B` : '内存估算暂不可用'} · 全部{meta.label}</span></header>
      {category === 'events' && <p className="comm-note sub">事件不携带数据，共用事件队列。{model.limits?.event_queue !== undefined ? `配置容量 ${model.limits.event_queue} 条；` : '容量使用后端默认值；'}队列满时丢弃最新事件。</p>}
      {!all.length ? <p className="empty">还没有{meta.label}。在 efw.json 的 {category} 中配置后，点击“重新载入”查看。</p> : !visible.length ? <div className="empty"><p>没有匹配的{meta.label}。</p><button className="btn" onClick={() => setQuery('')}>清除搜索</button></div> : (
        <div className="comm-table-scroll" role="region" aria-label={`${meta.label}表格，可横向滚动`} tabIndex={0}>
          <table className="comm-table">
            <thead><tr><th scope="col">名称 / 标识符</th>{category === 'signals' ? <><th scope="col">类型</th><th scope="col">初始值</th><th scope="col">单位</th><th scope="col">可整定范围</th></> : category === 'queues' ? <><th scope="col">元素类型</th><th scope="col">容量（条）</th><th scope="col">队列满时</th></> : <th scope="col">用途</th>}</tr></thead>
            <tbody>{visible.map((item) => {
              const s = category === 'signals' ? model.signals.find((s) => s.id === item.id) : undefined;
              const q = category === 'queues' ? model.queues.find((q) => q.id === item.id) : undefined;
              return <tr key={item.id} className={selected?.id === item.id ? 'is-selected' : undefined}>
                <td><button className="comm-object" aria-pressed={selected?.id === item.id} onClick={() => setSelectedId(item.id)}><span>{item.label || item.id}</span><span className="id sub">{item.id}</span></button></td>
                {s ? <><td className="id">{s.type}</td><td className="id">{String(s.init)}</td><td>{s.unit || '—'}</td><td>{s.tune ? <span className="id">{s.tune.min} ～ {s.tune.max}</span> : <span className="sub">不可整定</span>}</td></> : q ? <><td className="id">{q.item}</td><td className="id">{q.capacity}</td><td>{POLICIES[q.policy] ?? q.policy}</td></> : <td className="sub">通知状态机，无数据载荷</td>}
              </tr>;
            })}</tbody>
          </table>
        </div>
      )}
    </section>
    {selected && <section className="card comm-details" aria-label="通信详情">
      <header><h2>{selected.label || selected.id}</h2><span className="id sub">{selected.id}</span></header>
      {queue ? <div className="body"><p>最多保存 <span className="id">{queue.capacity}</span> 条 <span className="id">{queue.item}</span> 数据，队列满时{POLICIES[queue.policy] ?? queue.policy}。</p><p className="sub">队列通过用户 C 函数收发，当前分析接口未提供队列的生产者、消费者与逐队列内存。上方显示全部用户队列的内存估算；运行时深度与丢包数将在调试页查看。</p></div> : !usage ? <p className="empty">关系分析暂不可用，请先查看总览中的模型诊断。</p> : <>
        <div className="comm-relations">
          <div><h3>{signal ? '写入来源' : '发出事件'}</h3><References refs={signal ? signalUsage?.writers ?? [] : eventUsage?.emitters ?? []} model={model} /></div>
          <div><h3>{signal ? '读取位置' : '消费事件'}</h3><References refs={signal ? signalUsage?.readers ?? [] : eventUsage?.consumers ?? []} model={model} /></div>
        </div>
        <p className="comm-note sub">引用来自后端模型分析；用户 C 代码中未声明的访问不在此列。{signal ? '表格显示初始值，不是运行时采样值。' : '调试命令也可发出事件。'}</p>
      </>}
      {diagnostics.map((d, i) => <div key={i} className={`diag ${d.level}`}><div><div>{d.message}</div>{d.hint && <div className="hint">{d.hint}</div>}</div></div>)}
    </section>}
  </>;
}
