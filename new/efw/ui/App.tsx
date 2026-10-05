import { useEffect, useRef, useState } from 'react';
import { ArrowCounterClockwise, ArrowClockwise, ArrowsClockwise, Broadcast, Bug, Code as CodeIcon, FlowArrow, Gauge, GitBranch, Package } from '@phosphor-icons/react';
import { KIND_LABEL, useStore } from './store';
import { Welcome } from './pages/Welcome';
import { Overview } from './pages/Overview';
import { Flows } from './pages/Flows';
import { Machines } from './pages/Machines';
import { Communication } from './pages/Communication';
import { Code } from './pages/Code';
import { Debug } from './pages/Debug';
import { Generate } from './pages/Generate';
import type { Repair, RepairTarget } from './focus';

const NAV = [
  { id: 'overview', label: '总览', icon: Gauge },
  { id: 'flows', label: '数据流', icon: FlowArrow },
  { id: 'machines', label: '状态机', icon: GitBranch },
  { id: 'comm', label: '通信', icon: Broadcast },
  { id: 'code', label: '代码', icon: CodeIcon },
  { id: 'debug', label: '调试', icon: Bug },
  { id: 'generate', label: '生成', icon: Package },
] as const;
type PageId = (typeof NAV)[number]['id'];
const READY: PageId[] = ['overview', 'flows', 'machines', 'comm', 'code', 'debug', 'generate'];

export function App() {
  const { project, analysis, refresh, debug, target, canUndo, canRedo, undoModel, redoModel, startDebug, stopDebug, sourcesDirty } = useStore();
  const [page, setPage] = useState<PageId>('overview');
  // 总览页“下一步”的修复入口：跳转并让目标页选中出问题的对象
  const [repair, setRepair] = useState<Repair | null>(null);
  const repairToken = useRef(0);
  // 撤销/重做走快捷键；焦点在输入框或编辑器里时交给它们自己处理
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z') return;
      const el = document.activeElement;
      if (el && (el.closest('.monaco-editor') || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) return;
      e.preventDefault();
      if (e.shiftKey) void redoModel(); else void undoModel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undoModel, redoModel]);

  const goto = (target: RepairTarget) => {
    setRepair({ ...target, token: ++repairToken.current });
    setPage(target.page);
  };

  if (!project) return <Welcome />;

  const errors = analysis?.diagnostics.filter((d) => d.level === 'error').length ?? 0;
  const warns = analysis?.diagnostics.filter((d) => d.level === 'warn').length ?? 0;
  const running = debug.session !== null && !['stopped', 'error', 'ended'].includes(debug.state);
  const blocked = sourcesDirty || !analysis || !analysis.ok;
  const runTitle = sourcesDirty ? '有未保存的源码草稿，请先在代码页保存'
    : !analysis ? '正在分析模型'
      : !analysis.ok ? '模型有错误，先修复诊断'
        : running ? '停止调试' : '按调试页选定的目标启动';

  return (
    <div className="shell">
      <nav className="side" aria-label="主导航">
        <div className="brand">EFW</div>
        {NAV.map(({ id, label, icon: Icon }) => (
          <button key={id} className="nav" aria-current={page === id ? 'page' : undefined} disabled={!READY.includes(id)} title={READY.includes(id) ? label : `${label}（开发中）`} onClick={() => setPage(id)}>
            <Icon size={18} />
            {label}
          </button>
        ))}
      </nav>

      <header className="top">
        <span className="name">{project.model.name}</span>
        <span className="path">{project.path}</span>
        <span className="spacer" />
        <button className="btn" onClick={() => void refresh()}><ArrowsClockwise size={14} /> 重新载入</button>
        <span className="row">
          <button className="btn" aria-label="撤销" title="撤销模型编辑（Ctrl+Z）" disabled={!canUndo} onClick={() => void undoModel()}><ArrowCounterClockwise size={14} /></button>
          <button className="btn" aria-label="重做" title="重做模型编辑（Ctrl+Shift+Z）" disabled={!canRedo} onClick={() => void redoModel()}><ArrowClockwise size={14} /></button>
        </span>
        <button className="btn primary" disabled={blocked && !running} title={runTitle} onClick={() => {
          if (running) { void stopDebug(); return; }
          void startDebug(target);
          setPage('debug');
        }}>{running ? '停止' : debug.state === 'starting' ? '启动中…' : '运行'}</button>
      </header>

      <main className="page">
        <div className="inner">
          {page === 'overview' && <Overview onRepair={goto} />}
          {page === 'flows' && <Flows repair={repair} />}
          {page === 'machines' && <Machines key={project.path} repair={repair} />}
          {page === 'comm' && <Communication key={project.path} repair={repair} />}
          <div className="code-page" hidden={page !== 'code'}><Code key={project.path} repair={repair} /></div>
          {page === 'debug' && <Debug onOpenCode={() => setPage('code')} />}
          {page === 'generate' && <Generate key={project.path} />}
        </div>
      </main>

      <footer className="status">
        <span className={`dot ${errors ? 'err' : warns ? 'warn' : 'ok'}`}>{errors ? `${errors} 个错误` : warns ? `${warns} 个提醒` : '模型正常'}</span>
        <span className={`dot ${running ? 'ok' : debug.state === 'error' ? 'err' : ''}`}>
          目标：{running ? KIND_LABEL[debug.kind] ?? debug.kind : '未连接'}
        </span>
        <span className="spacer" />
        <span className="id">{analysis?.hash}</span>
      </footer>
    </div>
  );
}
