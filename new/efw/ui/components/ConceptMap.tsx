import type { Analysis, Model } from '../types';

// 概念图必须由项目现状渲染：盒子 = 模型里的真实对象，连线 = 后端分析出的真实读写关系。
// 不画“示意流程”，也不替用户编造关系；没人用的信号不出现。
export interface ConceptMapProps {
  model: Model;
  analysis: Analysis | null;
  /** 点盒子跳到能编辑它的页面（复用总览的修复入口）。 */
  onOpen?: (page: 'flows' | 'machines' | 'comm', category?: 'signals' | 'inputs' | 'outputs' | 'events' | 'queues', item?: string, machine?: string) => void;
  running?: string | null;
}

interface Node { key: string; col: Col; index: number; label: string; sub: string; tone: string }
type Col = 'in' | 'flow' | 'signal' | 'out' | 'mode' | 'event';

const COL = { in: 12, flow: 176, signal: 340, out: 504, mode: 668, event: 852 } as const;
const COL_TITLE: Record<Col, string> = { in: '输入', flow: '数据流', signal: '信号', out: '输出', mode: '状态机', event: '事件' };
const BOX_W = 152;
const BOX_H = 38;
const GAP_Y = 10;
const WIDTH = COL.event + BOX_W + 12;

export function ConceptMap({ model, analysis, onOpen, running = null }: ConceptMapProps) {
  const usage = analysis?.usage;
  const flowIds = new Set(model.flows.map((f) => f.id));
  const signalIds = new Set(model.signals.map((s) => s.id));

  // 被用到的信号：步骤里出现的信号字段 + 状态的 set + 转换的 signal 条件
  const usedSignals = new Set<string>();
  for (const f of model.flows) {
    for (const step of f.steps) {
      for (const value of Object.values(step)) if (typeof value === 'string' && signalIds.has(value)) usedSignals.add(value);
      for (const key of ['reads', 'writes']) {
        const list = step[key];
        if (Array.isArray(list)) for (const v of list) if (typeof v === 'string' && signalIds.has(v)) usedSignals.add(v);
      }
    }
  }
  for (const m of model.machines) {
    for (const st of m.states) for (const k of Object.keys(st.set)) usedSignals.add(k);
    for (const t of m.transitions) if (typeof t.on.signal === 'string') usedSignals.add(t.on.signal);
  }

  const signals = model.signals.filter((s) => usedSignals.has(s.id));
  const emitted = new Set(Object.entries(usage?.events ?? {})
    .filter(([, entry]) => entry.emitters.length > 0).map(([id]) => id));
  const consumed = new Set(model.machines.flatMap((m) => m.transitions
    .filter((t) => typeof t.on.event === 'string').map((t) => t.on.event as string)));
  const events = model.events.filter((e) => emitted.has(e.id) || consumed.has(e.id));

  const groups: Record<Col, Node[]> = { in: [], flow: [], signal: [], out: [], mode: [], event: [] };
  const add = (col: Col, key: string, label: string, sub: string, tone: string) => groups[col].push({ key, col, index: groups[col].length, label, sub, tone });

  for (const i of model.inputs) add('in', `in:${i.id}`, i.label || i.id, i.id, 'in');
  for (const f of model.flows) add('flow', `flow:${f.id}`, f.label || f.id, `${f.period_ms} ms · ${f.steps.length} 步`, 'flow');
  for (const s of signals) add('signal', `sig:${s.id}`, s.label || s.id, s.id, 'signal');
  for (const o of model.outputs) add('out', `out:${o.id}`, o.label || o.id, o.id, 'out');
  for (const m of model.machines) {
    for (const st of m.states) {
      add('mode', `mode:${m.id}:${st.id}`, st.label || st.id, st.run.length ? `${m.id} 跑 ${st.run.join('、')}` : `${m.id} 不控制数据流`, 'mode');
    }
  }
  for (const e of events) add('event', `event:${e.id}`, e.label || e.id, e.id, 'event');

  const nodes = (Object.values(groups).flat());
  const box = (key: string) => {
    const node = nodes.find((n) => n.key === key);
    if (!node) return null;
    return { x: COL[node.col], y: 26 + node.index * (BOX_H + GAP_Y), w: BOX_W, h: BOX_H };
  };

  const edges: { d: string; kind: 'read' | 'write' | 'run' | 'event' }[] = [];
  const link = (from: string, to: string, kind: 'read' | 'write' | 'run' | 'event') => {
    const a = box(from);
    const b = box(to);
    if (!a || !b) return;
    const x1 = a.x + a.w;
    const y1 = a.y + a.h / 2;
    const x2 = b.x;
    const y2 = b.y + b.h / 2;
    const bend = Math.max(24, (x2 - x1) / 2);
    edges.push({ d: `M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}`, kind });
  };
  // 关系一律来自 analyze.usage（输入/输出/信号/事件），状态机的 run 与 set 直接来自模型
  for (const [id, entry] of Object.entries(usage?.inputs ?? {})) {
    for (const r of entry.steps) if ('flow' in r && flowIds.has(r.flow)) link(`in:${id}`, `flow:${r.flow}`, 'read');
  }
  for (const [id, entry] of Object.entries(usage?.outputs ?? {})) {
    for (const r of entry.steps) if ('flow' in r && flowIds.has(r.flow)) link(`flow:${r.flow}`, `out:${id}`, 'write');
  }
  for (const [id, entry] of Object.entries(usage?.signals ?? {})) {
    for (const r of entry.writers) if ('flow' in r && flowIds.has(r.flow)) link(`flow:${r.flow}`, `sig:${id}`, 'write');
    for (const r of entry.readers) if ('flow' in r && flowIds.has(r.flow)) link(`flow:${r.flow}`, `sig:${id}`, 'read');
  }
  for (const m of model.machines) {
    for (const st of m.states) {
      for (const f of st.run) if (flowIds.has(f)) link(`mode:${m.id}:${st.id}`, `flow:${f}`, 'run');
      for (const k of Object.keys(st.set)) if (signalIds.has(k)) link(`mode:${m.id}:${st.id}`, `sig:${k}`, 'write');
    }
    for (const t of m.transitions) if (typeof t.on.event === 'string') link(`mode:${m.id}:${t.from}`, `event:${t.on.event}`, 'event');
  }
  for (const [id, entry] of Object.entries(usage?.events ?? {})) {
    for (const r of entry.emitters) if ('flow' in r && flowIds.has(r.flow)) link(`flow:${r.flow}`, `event:${id}`, 'event');
  }

  const height = Math.max(120, ...nodes.map((n) => 26 + n.index * (BOX_H + GAP_Y) + BOX_H)) + 16;
  const empty = !model.flows.length && !model.machines.length;

  return (
    <div className="concept">
      <div className="concept-scroll">
        <svg viewBox={`0 0 ${WIDTH} ${height}`} className="concept-svg" role="img"
          aria-label={`项目结构：${model.inputs.length} 个输入、${model.flows.length} 条数据流、${signals.length} 个被用到的信号、${model.outputs.length} 个输出、${model.machines.length} 台状态机、${events.length} 个事件`}>
          {(Object.keys(COL) as Col[]).map((col) => <text key={col} x={COL[col]} y={14} className="cm-col">{COL_TITLE[col]}</text>)}
          <g className="cm-edge">
            {edges.map((e, i) => <path key={i} d={e.d} className={`cm-line is-${e.kind}`} />)}
          </g>
          {nodes.map((n) => {
            const b = box(n.key)!;
            const live = n.tone === 'mode' && running !== null && running.includes(`${n.key.slice(5)}`);
            return <g key={n.key} className={`cm-node is-${n.tone}${live ? ' is-live' : ''}`} transform={`translate(${b.x} ${b.y})`}
              {...(onOpen ? { role: 'button', tabIndex: 0, onClick: () => openNode(n.key, onOpen), onKeyDown: (e: React.KeyboardEvent) => { if (e.key === 'Enter') openNode(n.key, onOpen); } } : {})}>
              <rect width={BOX_W} height={BOX_H} rx="5" />
              <text x={9} y={16}>{clip(n.label)}</text>
              <text x={9} y={29} className="cm-sub">{clip(n.sub)}</text>
            </g>;
          })}
        </svg>
      </div>
      {empty && <p className="empty">还没有数据流与状态机；添加对象后这张图会自己长出来。</p>}
      <p className="concept-legend sub">
        连线来自后端模型分析：<i className="cm-line is-read" /> 读取 · <i className="cm-line is-write" /> 写入 ·
        <i className="cm-line is-run" /> 状态机启停 · <i className="cm-line is-event" /> 事件。
        只画真正被用到的 {signals.length}/{model.signals.length} 个信号；{onOpen ? '点盒子可跳到编辑它的页面。' : ''}
        {running && ` 运行时标绿的是当前状态（${running}）。`}
      </p>
    </div>
  );
}

function clip(text: string): string {
  return text.length > 15 ? `${text.slice(0, 14)}…` : text;
}

function openNode(key: string, onOpen: ConceptMapProps['onOpen']) {
  if (!onOpen) return;
  const [kind, a, b] = key.split(':');
  if (kind === 'flow') onOpen('flows', undefined, a);
  else if (kind === 'sig') onOpen('comm', 'signals', a);
  else if (kind === 'mode') onOpen('machines', undefined, b, a);
  else if (kind === 'in') onOpen('comm', 'inputs', a);
  else if (kind === 'out') onOpen('comm', 'outputs', a);
  else if (kind === 'event') onOpen('comm', 'events', a);
}