import { useEffect, useMemo, useRef, useState } from 'react';
import { call } from '../rpc';
import { useStore } from '../store';
import { CurveChart, type Channel } from '../components/CurveChart';
import type { Run, Tunable } from '../types';

const SPEEDS = [[0.5, '0.5×'], [1, '1×'], [2, '2×'], [4, '4×'], [0, '最快']] as const;
const STATE_LABEL: Record<string, string> = { idle: '未启动', starting: '启动中', running: '运行中', paused: '已暂停', stopped: '已停止', error: '启动失败', ended: '回放结束' };
const CHANNELS = ['--s1', '--s2', '--s3', '--s4', '--s5'];
const fmt = (v: number | undefined, digits = 3) => (v === undefined || !Number.isFinite(v) ? '—' : String(Number(v.toFixed(digits))));
const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

export function Debug({ onOpenCode }: { onOpenCode: () => void }) {
  const { project, analysis, sourcesDirty, debug, startDebug, stopDebug, controlDebug, sendDebug } = useStore();
  const [runs, setRuns] = useState<Run[]>([]);
  const [runName, setRunName] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [forceValues, setForceValues] = useState<Record<string, string>>({});
  const timers = useRef<Record<string, number>>({});
  const manifest = debug.manifest;

  useEffect(() => {
    if (!project) return;
    void call<Run[]>('debug.runs', { path: project.path }).then((list) => {
      setRuns(list);
      setRunName((current) => current || list[0]?.name || '');
    }).catch(() => undefined);
  }, [project, debug.session, debug.state]);

  useEffect(() => {
    if (!manifest) return;
    const ids = manifest.signals.map((s) => s.id);
    setPicked(ids.length ? ids.slice(0, 2) : manifest.outputs.slice(0, 1).map((o) => o.id));
  }, [manifest]);

  useEffect(() => () => { for (const id of Object.values(timers.current)) clearTimeout(id); }, []);

  const catalog = useMemo(() => {
    if (!manifest) return [] as { id: string; label: string; unit: string }[];
    return [
      ...manifest.signals.map((s) => ({ id: s.id, label: s.label, unit: s.unit })),
      ...manifest.outputs.map((o) => ({ id: o.id, label: o.label, unit: o.unit })),
    ];
  }, [manifest]);
  const channels: Channel[] = useMemo(() => picked.map((id, i) => {
    const item = catalog.find((x) => x.id === id);
    return { id, label: item?.label ?? id, unit: item?.unit ?? '', color: CHANNELS[i % CHANNELS.length] };
  }), [picked, catalog]);

  if (!project) return null;
  const finished = ['stopped', 'error', 'ended'].includes(debug.state);
  const active = debug.session !== null && !finished;
  const blocked = sourcesDirty || !analysis || !analysis.ok;
  const blockReason = sourcesDirty ? '有未保存的源码草稿' : !analysis ? '正在分析模型' : '模型有错误，请先修复诊断';
  const latest = debug.latest;

  function toggleChannel(id: string) {
    setPicked((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  }
  function tune(item: Tunable, value: number) {
    setDraft((d) => ({ ...d, [item.key]: value }));
    clearTimeout(timers.current[item.key]);
    timers.current[item.key] = window.setTimeout(() => {
      void sendDebug(`set ${item.key} ${value}`);
      setDraft((d) => { const next = { ...d }; delete next[item.key]; return next; });
    }, 150);
  }
  const tunableValue = (item: Tunable) => draft[item.key] ?? debug.params?.[item.key] ?? item.value;

  return <>
    <div><h1>调试</h1><p className="sub">虚拟目标在电脑上运行，用同一套界面观察曲线、任务和状态；也可以回放已保存的记录。</p></div>

    {(!debug.session || debug.state === 'stopped' || debug.state === 'ended') && <section className="card" aria-label="启动调试">
      <header><h2>启动调试</h2><span className="sub">虚拟目标模拟硬件输入，不依赖开发板</span></header>
      {sourcesDirty && <div className="diag warn"><div>有未保存的源码草稿。调试运行磁盘上的代码，请先在代码页保存。<button className="btn" onClick={onOpenCode}>去代码页</button></div></div>}
      {analysis && !analysis.ok && <div className="diag error"><div>模型有错误，无法启动调试：{analysis.diagnostics.find((d) => d.level === 'error')?.message}</div></div>}
      <div className="body debug-start">
        <div className="debug-start-item">
          <p><strong>虚拟目标</strong></p>
          <p className="sub">按模型里的仿真输入运行当前项目，可播放、暂停、单步和整定。</p>
          <button className="btn primary" disabled={blocked} title={blocked ? blockReason : '编译并启动虚拟目标'} onClick={() => void startDebug({ kind: 'virtual' })}>启动虚拟目标</button>
        </div>
        <div className="debug-start-item">
          <p><strong>记录回放</strong></p>
          {runs.length ? <>
            <p className="sub">回放 {runs.length} 份记录，不连接目标。</p>
            <div className="row">
              <select className="input id" value={runName} onChange={(e) => setRunName(e.target.value)} aria-label="选择记录">
                {runs.map((run) => <option key={run.name} value={run.name}>{run.started || run.name} · {run.kind}</option>)}
              </select>
              <button className="btn" disabled={!runName} onClick={() => void startDebug({ kind: 'replay', run: runName })}>启动回放</button>
            </div>
          </> : <p className="sub">还没有记录。启动一次调试后会自动录制到 .efw/runs/。</p>}
        </div>
      </div>
    </section>}

    {debug.state === 'starting' && <section className="card"><p className="empty">正在编译并启动虚拟目标…</p></section>}

    {debug.session && <section className="card" aria-label="调试控制">
      <header>
        <span><strong>{debug.kind === 'replay' ? '记录回放' : '虚拟目标'}</strong> <span className="id sub">{debug.session}</span></span>
        <span className={`dot ${debug.state === 'error' ? 'err' : debug.state === 'running' ? 'ok' : 'warn'}`}>{STATE_LABEL[debug.state] ?? debug.state}</span>
      </header>
      <div className="body debug-bar">
        <span className="debug-t">仿真时间 <span className="id">{debug.t}</span> ms</span>
        {debug.state === 'running' && debug.kind !== 'replay' && <span className="sub">录制中</span>}
        {debug.kind === 'replay' && debug.end !== null && <span className="sub">时长 {secs(debug.end)}</span>}
        <span className="spacer" />
        <button className="btn" disabled={!active || finished} onClick={() => void controlDebug(debug.state === 'running' ? 'pause' : 'play')}>{debug.state === 'running' ? '暂停' : '播放'}</button>
        <button className="btn" disabled={debug.kind !== 'virtual' || debug.state !== 'paused' || !active} title={debug.state === 'running' ? '先暂停再单步' : '前进 500 ms'} onClick={() => void controlDebug('step', 500)}>单步</button>
        <select className="input" value={debug.speed} disabled={!active} aria-label="仿真速度" onChange={(e) => void controlDebug('speed', Number(e.target.value))}>
          {SPEEDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <button className="btn" disabled={debug.kind !== 'virtual' || !active} onClick={() => void startDebug({ kind: 'virtual' })}>重新开始</button>
        <button className="btn" disabled={debug.state === 'stopped'} onClick={() => void stopDebug()}>停止</button>
      </div>
      {debug.message && <p className={`debug-message ${debug.state === 'error' || debug.warning ? 'err-text' : 'sub'}`} role="status">{debug.message}</p>}
      {debug.ack && <p className="debug-ack sub" role="status">{debug.ack.ok ? '目标已确认' : '目标拒绝'} <span className="id">{debug.ack.command}</span>{debug.ack.message ? ` · ${debug.ack.message}` : ''}</p>}
    </section>}

    {debug.session && <div className="debug-grid">
      <div className="debug-col">
        <section className="card" aria-label="信号曲线">
          <header><h2>信号曲线</h2><span className="sub">纵轴自动量程 · 横轴为仿真时间</span></header>
          <div className="body">
            <CurveChart series={debug.series} channels={channels} />
            <div className="chart-legend">
              {catalog.map((item) => {
                const channel = channels.find((c) => c.id === item.id);
                const value = latest ? latest.s?.[item.id] ?? latest.o?.[item.id] : undefined;
                return <button key={item.id} className="channel" data-id={item.id} aria-pressed={picked.includes(item.id)} onClick={() => toggleChannel(item.id)}>
                  {channel && <i style={{ background: `var(${channel.color})` }} />}
                  {item.label}
                  <span className="id">{fmt(value)}{item.unit ? ` ${item.unit}` : ''}</span>
                </button>;
              })}
              {!catalog.length && <span className="sub">当前项目没有信号或输出。</span>}
            </div>
          </div>
        </section>

        <section className="card" aria-label="任务统计">
          <header><h2>任务统计</h2><span className="sub">来自目标快照，运行时刷新</span></header>
          {manifest?.flows.length ? <div className="comm-table-scroll"><table className="tasks">
            <thead><tr><th>任务</th><th className="num">周期</th><th>状态</th><th className="num">执行</th><th className="num">丢拍</th><th className="num">超限</th><th className="num">错误</th><th className="num">迟到</th><th className="num">耗时</th></tr></thead>
            <tbody>{manifest.flows.map((flow) => {
              const stat = latest?.f?.[flow.id];
              const problem = stat && (stat.miss || stat.over || stat.err);
              return <tr key={flow.id} data-id={flow.id}>
                <td>{flow.label} <span className="id sub">{flow.id}</span></td>
                <td className="num">{flow.period_ms} ms</td>
                <td>{stat ? stat.on ? <span className="dot ok">运行</span> : <span className="dot">暂停</span> : '—'}</td>
                <td className="num">{stat?.run ?? '—'}</td>
                <td className={`num ${stat?.miss ? 'err-text' : ''}`}>{stat?.miss ?? '—'}</td>
                <td className={`num ${stat?.over ? 'err-text' : ''}`}>{stat?.over ?? '—'}</td>
                <td className={`num ${stat?.err ? 'err-text' : ''}`}>{stat?.err ?? '—'}</td>
                <td className="num">{stat ? `${stat.late}/${stat.max_late} ms` : '—'}</td>
                <td className="num">{stat ? `${stat.us}/${stat.max_us} µs` : '—'}</td>
              </tr>;
            })}</tbody>
          </table></div> : <p className="empty">当前项目没有数据流。</p>}
        </section>
      </div>

      <div className="debug-col">
        <section className="card debug-machines" aria-label="状态机">
          <header><h2>状态机</h2></header>
          {manifest?.machines.length ? manifest.machines.map((machine) => {
            const current = latest?.m?.[machine.id];
            const label = current ? machine.states.find((s) => s.id === current.s)?.label ?? current.s : machine.initial;
            return <div key={machine.id} className="machine-row" data-id={machine.id}>
              <div><span className="sub">{machine.label}</span> <span className="chip acc">{label}</span></div>
              {current && <div className="id sub">已保持 {secs(debug.t - current.since)}</div>}
            </div>;
          }) : <p className="empty">当前项目没有状态机。</p>}
          {debug.transitions.length > 0 && <div className="debug-transitions">
            {[...debug.transitions].slice(-6).reverse().map((trans, i) => {
              const machine = manifest?.machines.find((m) => m.id === trans.m);
              const name = (id: string) => machine?.states.find((s) => s.id === id)?.label ?? id;
              return <div key={`${trans.t}-${i}`} className="id sub">{secs(trans.t)} {machine?.label ?? trans.m}：{name(trans.from)} → {name(trans.to)}（{trans.by}）</div>;
            })}
          </div>}
        </section>

        <section className="card" aria-label="参数整定">
          <header><h2>参数整定</h2><span className="sub">发送 set 命令，目标立即生效</span></header>
          {manifest?.params.length ? manifest.params.map((item) => {
            const value = tunableValue(item);
            const step = Math.max((item.max - item.min) / 100, 1e-6);
            return <div key={item.key} className="tuner" data-key={item.key}>
              <label htmlFor={`tune-${item.key}`} title={item.label}>{item.label}<span className="id sub">{item.key}</span></label>
              <input id={`tune-${item.key}`} type="range" min={item.min} max={item.max} step={step} value={value} disabled={!active} onChange={(e) => tune(item, Number(e.target.value))} />
              <input className="input" type="number" step={step} value={value} disabled={!active} aria-label={`${item.label} 数值`} onChange={(e) => tune(item, Number(e.target.value))} />
            </div>;
          }) : <p className="empty">当前项目没有可整定量。</p>}
        </section>

        <section className="card" aria-label="事件与输入">
          <header><h2>事件与输入</h2><span className="sub">{debug.kind === 'replay' ? '回放中不能发送命令' : '直接发给目标'}</span></header>
          {manifest?.events.map((event) => <div key={event.id} className="debug-event" data-id={event.id}>
            <span>{event.label} <span className="id sub">{event.id}</span></span>
            <button className="btn" disabled={!active || debug.kind === 'replay'} onClick={() => void sendDebug(`fire ${event.id}`)}>触发</button>
          </div>)}
          {manifest?.inputs.map((input) => {
            const forced = latest?.forced?.includes(input.id);
            return <div key={input.id} className="debug-event" data-id={input.id}>
              <span>{input.label} <span className="id sub">{input.id}</span>{forced && <span className="chip acc">已强制</span>}</span>
              <div className="row">
                <input className="input" type="number" style={{ width: 88 }} value={forceValues[input.id] ?? '0'} disabled={!active || debug.kind === 'replay'} aria-label={`${input.label} 强制值`} onChange={(e) => setForceValues((v) => ({ ...v, [input.id]: e.target.value }))} />
                <button className="btn" disabled={!active || debug.kind === 'replay'} onClick={() => void sendDebug(`force ${input.id} ${forceValues[input.id] ?? '0'}`)}>强制</button>
                <button className="btn" disabled={!active || debug.kind === 'replay' || !forced} onClick={() => void sendDebug(`release ${input.id}`)}>释放</button>
              </div>
            </div>;
          })}
          {!manifest?.events.length && !manifest?.inputs.length && <p className="empty">当前项目没有事件或输入。</p>}
        </section>

        <section className="card" aria-label="队列">
          <header><h2>队列</h2></header>
          <table>
            <thead><tr><th>队列</th><th className="num">深度</th><th className="num">push</th><th className="num">drop</th><th className="num">峰值</th></tr></thead>
            <tbody>
              {[{ id: 'events', label: '事件队列', item: '', capacity: 0 }, ...(manifest?.queues ?? [])].map((queue) => {
                const stat = latest?.q?.[queue.id];
                return <tr key={queue.id}>
                  <td>{queue.label} <span className="id sub">{queue.id}</span></td>
                  <td className="num">{stat ? `${stat.n}/${stat.cap}` : '—'}</td>
                  <td className="num">{stat?.push ?? '—'}</td>
                  <td className={`num ${stat?.drop ? 'err-text' : ''}`}>{stat?.drop ?? '—'}</td>
                  <td className="num">{stat?.hw ?? '—'}</td>
                </tr>;
              })}
            </tbody>
          </table>
        </section>
      </div>
    </div>}
  </>;
}
