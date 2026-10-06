import { useMemo, useState } from 'react';
import { Bug, Code as CodeIcon, FlowArrow, GitBranch, Gauge, Package, Broadcast, CaretRight, FileText, Cpu } from '@phosphor-icons/react';
import type { Analysis, Diagnostic, Opened } from '../types';
import { repairFor, type RepairTarget } from '../focus';

// IDE 风格资源树：视图 / 项目文件 / 模型对象 / 诊断。点任意对象跳到能编辑它的页面。
export type PageId = 'overview' | 'flows' | 'machines' | 'comm' | 'code' | 'debug' | 'generate';

type CommKey = 'signals' | 'inputs' | 'outputs' | 'events' | 'queues';
const COMMS: readonly CommKey[] = ['signals', 'inputs', 'outputs', 'events', 'queues'];

const VIEWS = [
  { id: 'overview', label: '总览', icon: Gauge }, { id: 'flows', label: '数据流', icon: FlowArrow },
  { id: 'machines', label: '状态机', icon: GitBranch }, { id: 'comm', label: '通信', icon: Broadcast },
  { id: 'code', label: '代码', icon: CodeIcon }, { id: 'debug', label: '调试', icon: Bug },
  { id: 'generate', label: '生成', icon: Package },
] as const;

export function Explorer({ project, analysis, page, onPage, onRepair, collapsed, onToggle }: {
  project: Opened;
  analysis: Analysis | null;
  page: PageId;
  onPage: (page: PageId) => void;
  onRepair: (target: RepairTarget) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const [open, setOpen] = useState({ files: true, model: true, diag: true });
  const model = project.model;
  const toggle = (key: keyof typeof open) => setOpen((o) => ({ ...o, [key]: !o[key] }));

  const groups = useMemo(() => [
    { key: 'flows' as const, label: `数据流（${model.flows.length}）`, items: model.flows.map((f) => ({ id: f.id, label: f.label || f.id, sub: `${f.period_ms} ms` })) },
    { key: 'machines' as const, label: `状态机（${model.machines.length}）`, items: model.machines.map((m) => ({ id: m.id, label: m.label || m.id, sub: `${m.states.length} 状态` })) },
    { key: 'signals' as const, label: `信号（${model.signals.length}）`, items: model.signals.map((s) => ({ id: s.id, label: s.label || s.id, sub: s.type })) },
    { key: 'inputs' as const, label: `输入（${model.inputs.length}）`, items: model.inputs.map((i) => ({ id: i.id, label: i.label || i.id, sub: i.type })) },
    { key: 'outputs' as const, label: `输出（${model.outputs.length}）`, items: model.outputs.map((o) => ({ id: o.id, label: o.label || o.id, sub: o.type })) },
    { key: 'events' as const, label: `事件（${model.events.length}）`, items: model.events.map((e) => ({ id: e.id, label: e.label || e.id, sub: '通知' })) },
    { key: 'queues' as const, label: `队列（${model.queues.length}）`, items: model.queues.map((q) => ({ id: q.id, label: q.label || q.id, sub: `${q.capacity} 条` })) },
  ], [model]);
  const errors = (analysis?.diagnostics ?? []).filter((d) => d.level === 'error');
  const warns = (analysis?.diagnostics ?? []).filter((d) => d.level === 'warn');

  if (collapsed) {
    return <nav className="side is-collapsed" aria-label="主导航">
      <button className="brand" onClick={onToggle} title="展开资源树（Ctrl+B）">EFW</button>
      {VIEWS.map(({ id, label, icon: Icon }) => (
        <button key={id} className="nav" aria-current={page === id ? 'page' : undefined} title={label} onClick={() => onPage(id)}>
          <Icon size={18} /><span>{label}</span>
        </button>
      ))}
    </nav>;
  }

  return <nav className="side is-open" aria-label="资源树">
    <button className="brand" onClick={onToggle} title="收起资源树（Ctrl+B）">EFW</button>

    <Section title="视图" defaultOpen>
      {VIEWS.map(({ id, label, icon: Icon }) => (
        <button key={id} className="tree-item is-view" aria-current={page === id ? 'page' : undefined} onClick={() => onPage(id)}>
          <Icon size={14} />{label}
        </button>
      ))}
    </Section>

    <Section title="项目文件" open={open.files} onToggle={() => toggle('files')}>
      <button className="tree-item" onClick={() => { onPage('code'); onRepair({ page: 'code', item: 'efw.json' }); }}>
        <FileText size={14} />efw.json<span className="tree-sub">应用配置</span>
      </button>
      {project.files.map((name) => (
        <button key={name} className="tree-item" onClick={() => { onPage('code'); onRepair({ page: 'code', item: name }); }}>
          <CodeIcon size={14} />{name}
        </button>
      ))}
    </Section>

    <Section title="模型" open={open.model} onToggle={() => toggle('model')}>
      {groups.map((g) => <Group key={g.key} group={g} onRepair={onRepair} />)}
    </Section>

    <Section title={`诊断 ${errors.length} 错 ${warns.length} 提醒`} open={open.diag} onToggle={() => toggle('diag')}>
      {[...errors, ...warns].map((d: Diagnostic, i: number) => {
        const target = repairFor(d.at);
        return <button key={i} className={`tree-item is-diag ${d.level}`} title={d.message}
          onClick={() => { if (target) onRepair(target); else onPage('overview'); }}>
          <span className="tree-dot" />{d.at}<span className="tree-sub">{d.message.slice(0, 22)}</span>
        </button>;
      })}
      {!errors.length && !warns.length && <p className="tree-empty">没有诊断</p>}
    </Section>
  </nav>;
}

function Section({ title, children, open, defaultOpen, onToggle }: {
  title: string; children: React.ReactNode; open?: boolean; defaultOpen?: boolean; onToggle?: () => void;
}) {
  const [selfOpen, setSelfOpen] = useState(defaultOpen ?? true);
  const shown = onToggle ? open ?? true : selfOpen;
  const flip = () => (onToggle ? onToggle() : setSelfOpen(!selfOpen));
  return <section className="tree-group">
    <button className="tree-head" aria-expanded={shown} onClick={flip}>
      <CaretRight size={12} className={shown ? 'caret is-open' : 'caret'} />
      <span>{title}</span>
    </button>
    {shown && <div className="tree-body">{children}</div>}
  </section>;
}

function Group({ group, onRepair }: {
  group: { key: CommKey | 'flows' | 'machines'; label: string; items: { id: string; label: string; sub: string }[] };
  onRepair: (target: RepairTarget) => void;
}) {
  const [open, setOpen] = useState(group.key === 'flows' || group.key === 'machines');
  const comm = COMMS.includes(group.key as CommKey);
  const page = group.key === 'flows' ? 'flows' : group.key === 'machines' ? 'machines' : 'comm';
  return <>
    <button className="tree-head is-sub" aria-expanded={open} onClick={() => setOpen(!open)}>
      <CaretRight size={12} className={open ? 'caret is-open' : 'caret'} />
      <Cpu size={13} /><span>{group.label}</span>
    </button>
    {open && <div className="tree-body">
      {group.items.map((item) => <button key={item.id} className="tree-item" data-tree-id={item.id}
        onClick={() => onRepair({ page, ...(comm ? { category: group.key as CommKey } : {}), item: item.id })}>
        {item.label}<span className="tree-sub">{item.sub}</span>
      </button>)}
      {!group.items.length && <p className="tree-empty">空</p>}
    </div>}
  </>;
}