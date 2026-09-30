import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { applyDebugEvent, EMPTY_DEBUG, type DebugState } from './debug';
import { call, onEvent } from './rpc';
import type { Analysis, Manifest, Opened } from './types';

export interface DebugTarget { kind: 'virtual' | 'serial' | 'tcp' | 'replay'; run?: string; port?: string; baud?: number; host?: string }
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
  stopDebug: () => Promise<void>;
  controlDebug: (action: string, value?: number) => Promise<void>;
  sendDebug: (line: string) => Promise<void>;
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

  const load = useCallback(async (p: Opened) => {
    const active = sessionRef.current;
    if (active) {
      sessionRef.current = null;
      void call('debug.stop', { session: active }).catch(() => undefined);
    }
    setDebug(EMPTY_DEBUG);
    setSourcesDirty(false);
    setProject(p);
    setAnalysis(await call<Analysis>('project.analyze', { path: p.path, model: p.model }));
    localStorage.setItem(LAST, p.path);
  }, []);

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

  return <Ctx.Provider value={{ project, analysis, busy, error, sourcesDirty, setSourcesDirty, debug, startDebug, stopDebug, controlDebug, sendDebug, open, create, refresh, reload }}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error('StoreProvider missing');
  return s;
}
