import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { applyDebugEvent, EMPTY_DEBUG, type DebugState } from './debug';
import { call, onEvent } from './rpc';
import type { Analysis, Diagnostic, Manifest, Model, Opened } from './types';

export interface DebugTarget { kind: 'virtual' | 'serial' | 'tcp' | 'replay'; run?: string; port?: string; baud?: number; host?: string }

export const KIND_LABEL: Record<string, string> = {
  virtual: '虚拟目标', serial: '串口目标', tcp: 'TCP 目标', replay: '记录回放',
};


/** 目标参数没填全时给出可行动的错误，而不是让后端抛 KeyError。 */
export function targetProblem(target: DebugTarget): string {
  if (target.kind === 'serial' && !target.port?.trim()) return '请先填写串口设备，例如 /dev/ttyUSB0 或 COM3';
  if (target.kind === 'serial' && !(target.baud ?? 0)) return '请先填写波特率';
  if (target.kind === 'tcp' && !target.host?.trim()) return '请先填写目标主机或 IP';
  if (target.kind === 'tcp' && !(target.port && Number(target.port) > 0)) return '请先填写端口号';
  if (target.kind === 'replay' && !target.run) return '请先选择一份记录';
  return '';
}
interface DebugStart { session: string; kind: string; manifest: Manifest; state: string }

interface Store {
  project: Opened | null;
  analysis: Analysis | null;
  busy: boolean;
  error: string | null;
  sourcesDirty: boolean;
  setSourcesDirty: (value: boolean) => void;
  debug: DebugState;
  startDebug: (target: DebugTarget) => Promise<void>;
  target: DebugTarget;
  setTarget: (target: DebugTarget) => void;
  stopDebug: () => Promise<void>;
  controlDebug: (action: string, value?: number) => Promise<void>;
  sendDebug: (line: string) => Promise<void>;
  updateModel: (mutate: (model: Model) => Model) => Promise<{ ok: boolean; diagnostics: Diagnostic[] }>;
  open: (path: string) => Promise<void>;
  create: (path: string, name: string, template: string) => Promise<void>;
  refresh: () => Promise<void>;
  reload: () => Promise<Opened | null>;
}

const Ctx = createContext<Store | null>(null);
const LAST = 'efw.lastProject';

export function StoreProvider({ children }: { children: ReactNode }) {
  const [project, setProject] = useState<Opened | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourcesDirty, setSourcesDirty] = useState(false);
  const [debug, setDebug] = useState<DebugState>(EMPTY_DEBUG);
  const sessionRef = useRef<string | null>(null);
  const projectRef = useRef<Opened | null>(null);
  projectRef.current = project;
  const chainRef = useRef<Promise<unknown>>(Promise.resolve());
  // 顶栏“运行”和调试页共用同一个目标选择
  const [target, setTarget] = useState<DebugTarget>({ kind: 'virtual' });

  const applyProject = useCallback(async (p: Opened) => {
    setProject(p);
    setAnalysis(await call<Analysis>('project.analyze', { path: p.path, model: p.model }));
    localStorage.setItem(LAST, p.path);
  }, []);

  const load = useCallback(async (p: Opened) => {
    const active = sessionRef.current;
    if (active) {
      sessionRef.current = null;
      void call('debug.stop', { session: active }).catch(() => undefined);
    }
    setDebug(EMPTY_DEBUG);
    setSourcesDirty(false);
    await applyProject(p);
  }, [applyProject]);

  const guard = useCallback(async (work: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await work(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }, []);

  const open = useCallback((path: string) => guard(async () => load(await call<Opened>('project.open', { path }))), [guard, load]);
  const create = useCallback(
    (path: string, name: string, template: string) => guard(async () => load(await call<Opened>('project.create', { path, name, template }))),
    [guard, load],
  );
  const refresh = useCallback(() => (project ? open(project.path) : Promise.resolve()), [project, open]);
  const reload = useCallback(async () => {
    if (!project) return null;
    const next = await call<Opened>('project.open', { path: project.path });
    await load(next);
    return next;
  }, [project, load]);

// 串行执行：连续编辑共用一条 revision 链，避免第二次提交撞上旧 revision。
  const updateModel = useCallback(async (mutate: (model: Model) => Model) => {
    const run = async (): Promise<{ ok: boolean; diagnostics: Diagnostic[] }> => {
      const failure = (message: string) => ({ ok: false, diagnostics: [{ level: 'error', at: 'model', message, hint: '' } as Diagnostic] });
      const current = projectRef.current;
      if (!current) return failure('没有打开项目');
      let candidate: Model;
      try { candidate = mutate(structuredClone(current.model)); }
      catch (e) { return failure((e as Error).message); }
      setBusy(true); setError(null);
      try {
        const info = await call<Analysis>('project.analyze', { path: current.path, model: candidate });
        if (!info.ok) return { ok: false, diagnostics: info.diagnostics.filter((d) => d.level === 'error') };
        const saved = await call<{ revision: string }>('project.save', { path: current.path, model: candidate, layout: current.layout, rev: current.revision });
        projectRef.current = { ...current, model: candidate, revision: saved.revision };
        setProject(projectRef.current);
        setAnalysis(info);
        return { ok: true, diagnostics: [] };
      } catch (e) {
        return failure((e as Error).message);
      } finally { setBusy(false); }
    };
    const task = chainRef.current.then(run, run);
    chainRef.current = task.catch(() => undefined);
    return task;
  }, []);

  useEffect(() => onEvent((event) => {
    const session = typeof event.session === 'string' ? event.session : '';
    if (!session) return;
    setDebug((current) => (current.session === session ? applyDebugEvent(current, event) : current));
  }), []);

  useEffect(() => () => {
    const active = sessionRef.current;
    if (active) void call('debug.stop', { session: active }).catch(() => undefined);
  }, []);

  const startDebug = useCallback(async (target: DebugTarget) => {
    if (!project) return;
    const problem = targetProblem(target);
    if (problem) { setDebug({ ...EMPTY_DEBUG, state: 'error', kind: target.kind, message: problem }); return; }
    const previous = sessionRef.current;
    if (previous) {
      sessionRef.current = null;
      await call('debug.stop', { session: previous }).catch(() => undefined);
    }
    setDebug({ ...EMPTY_DEBUG, state: 'starting', kind: target.kind });
    try {
      const info = await call<DebugStart>('debug.start', { path: project.path, target });
      sessionRef.current = info.session;
      setDebug({ ...EMPTY_DEBUG, session: info.session, kind: info.kind, manifest: info.manifest, state: info.state });
      if (info.state !== 'running') await call('debug.control', { session: info.session, action: 'play' });
    } catch (e) {
      setDebug({ ...EMPTY_DEBUG, state: 'error', kind: target.kind, message: (e as Error).message });
    }
  }, [project]);

  const stopDebug = useCallback(async () => {
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    try { await call('debug.stop', { session }); }
    catch { /* 会话可能已断开 */ }
    setDebug((current) => ({ ...current, state: 'stopped' }));
  }, []);

  const controlDebug = useCallback(async (action: string, value?: number) => {
    const session = sessionRef.current;
    if (!session) return;
    try { await call('debug.control', { session, action, value }); }
    catch (e) { setDebug((current) => ({ ...current, message: (e as Error).message })); }
  }, []);

  const sendDebug = useCallback(async (line: string) => {
    const session = sessionRef.current;
    if (!session) return;
    try { await call('debug.send', { session, line }); }
    catch (e) { setDebug((current) => ({ ...current, message: (e as Error).message })); }
  }, []);

  useEffect(() => {
    const last = localStorage.getItem(LAST);
    if (last) void open(last);
  }, [open]);

  return <Ctx.Provider value={{ project, analysis, busy, error, sourcesDirty, setSourcesDirty, debug, target, setTarget, startDebug, stopDebug, controlDebug, sendDebug, updateModel, open, create, refresh, reload }}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error('StoreProvider missing');
  return s;
}
