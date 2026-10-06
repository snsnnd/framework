import { useEffect, useMemo, useRef, useState } from 'react';
import type { Opened } from '../types';
import type { RepairTarget } from '../focus';
import type { PageId } from './Explorer';

export interface Command {
  id: string;
  title: string;
  hint?: string;
  group: string;
  run: () => void;
}

/** 命令面板：Ctrl+K / Ctrl+P 打开，输入即过滤，回车执行，Esc 关闭。 */
export function CommandPalette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    const pool = q
      ? commands.filter((c) => `${c.title} ${c.group} ${c.hint ?? ''}`.toLocaleLowerCase().includes(q))
      : commands;
    return pool.slice(0, 40);
  }, [commands, query]);

  useEffect(() => { setIndex(0); }, [query]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); setIndex((i) => Math.min(filtered.length - 1, i + 1)); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setIndex((i) => Math.max(0, i - 1)); return; }
      if (e.key === 'Enter') {
        e.preventDefault();
        const command = filtered[index];
        if (command) { command.run(); onClose(); }
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [filtered, index, onClose]);

  return <div className="palette-backdrop" onMouseDown={onClose}>
    <div className="palette" role="dialog" aria-label="命令面板" onMouseDown={(e) => e.stopPropagation()}>
      <input className="palette-input" aria-label="命令" placeholder="输入命令或对象名，例如 数据流、保存、temp"
        value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
      <ul className="palette-list" ref={listRef}>
        {filtered.map((c, i) => <li key={c.id}>
          <button className={`palette-item${i === index ? ' is-active' : ''}`} onMouseEnter={() => setIndex(i)}
            onClick={() => { c.run(); onClose(); }}>
            <span className="palette-group">{c.group}</span>
            <span className="palette-title">{c.title}</span>
            {c.hint && <span className="palette-hint">{c.hint}</span>}
          </button>
        </li>)}
        {!filtered.length && <li className="palette-empty">没有匹配的命令</li>}
      </ul>
      <p className="palette-foot sub">↑↓ 选择 · Enter 执行 · Esc 关闭</p>
    </div>
  </div>;
}

/** 从项目与页面动作生成命令表；对象跳转复用修复入口的定位机制。 */
export function buildCommands(project: Opened | null, actions: {
  goto: (page: PageId) => void;
  repair: (target: RepairTarget) => void;
  run: () => void;
  stop: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  reload: () => void;
  generate: () => void;
  code: () => void;
  palette: () => void;
  switchProject: () => void;
}): Command[] {
  const pages: [PageId, string][] = [
    ['overview', '总览'], ['flows', '数据流'], ['machines', '状态机'], ['comm', '通信'],
    ['code', '代码'], ['debug', '调试'], ['generate', '生成'],
  ];
  const commands: Command[] = pages.map(([page, title]) => ({
    id: `view:${page}`, title: `转到${title}页`, group: '视图', run: () => actions.goto(page),
  }));
  commands.push(
    { id: 'run', title: '运行 / 停止调试', group: '调试', hint: '顶栏运行按钮', run: actions.run },
    { id: 'debug', title: '打开调试页并选目标', group: '调试', run: () => actions.goto('debug') },
    { id: 'generate', title: '生成代码', group: '生成', run: actions.generate },
    { id: 'reload', title: '重新载入项目', group: '项目', run: actions.reload },
    { id: 'code', title: '打开代码页', group: '项目', run: actions.code },
    { id: 'switch', title: '切换项目 / 新建项目', group: '项目', hint: '回到欢迎页', run: actions.switchProject },
  );
  if (actions.canUndo) commands.push({ id: 'undo', title: '撤销模型编辑', group: '编辑', hint: 'Ctrl+Z', run: actions.undo });
  if (actions.canRedo) commands.push({ id: 'redo', title: '重做模型编辑', group: '编辑', hint: 'Ctrl+Shift+Z', run: actions.redo });
  if (!project) return commands;

  const model = project.model;
  for (const f of model.flows) commands.push({ id: `flow:${f.id}`, title: f.label || f.id, group: '数据流', hint: f.id, run: () => actions.repair({ page: 'flows', item: f.id }) });
  for (const m of model.machines) commands.push({ id: `machine:${m.id}`, title: m.label || m.id, group: '状态机', hint: m.id, run: () => actions.repair({ page: 'machines', machine: m.id }) });
  for (const s of model.signals) commands.push({ id: `sig:${s.id}`, title: s.label || s.id, group: '信号', hint: s.id, run: () => actions.repair({ page: 'comm', category: 'signals', item: s.id }) });
  for (const i of model.inputs) commands.push({ id: `in:${i.id}`, title: i.label || i.id, group: '输入', hint: i.id, run: () => actions.repair({ page: 'comm', category: 'inputs', item: i.id }) });
  for (const o of model.outputs) commands.push({ id: `out:${o.id}`, title: o.label || o.id, group: '输出', hint: o.id, run: () => actions.repair({ page: 'comm', category: 'outputs', item: o.id }) });
  for (const e of model.events) commands.push({ id: `ev:${e.id}`, title: e.label || e.id, group: '事件', hint: e.id, run: () => actions.repair({ page: 'comm', category: 'events', item: e.id }) });
  for (const q of model.queues) commands.push({ id: `q:${q.id}`, title: q.label || q.id, group: '队列', hint: q.id, run: () => actions.repair({ page: 'comm', category: 'queues', item: q.id }) });
  for (const file of ['efw.json', ...project.files]) {
    commands.push({ id: `file:${file}`, title: file, group: '源文件', run: () => actions.repair({ page: 'code', item: file }) });
  }
  return commands;
}