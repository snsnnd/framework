import { lazy, Suspense, useEffect, useState } from 'react';
import { call, RpcError } from '../rpc';
import { useStore } from '../store';
import type { FnInfo } from '../types';

const SourceEditor = lazy(() => import('../components/SourceEditor'));
const CONFIG = 'efw.json';
const TEMPLATE_NOTICE = '模板结构由工具维护：只能修改 EFW USER 标记内的逻辑。';
interface SourceFile { name: string; content: string; revision: string }
interface Draft { content: string; saved: string; revision: string | null }
interface Stub { file: string; header: string; text: string }
const dirty = (draft: Draft) => draft.revision === null || draft.content !== draft.saved;

export function Code() {
  const { project, analysis, refresh, reload, setSourcesDirty } = useStore();
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [active, setActive] = useState('');
  const [newName, setNewName] = useState('src/new.c');
  const [staged, setStaged] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const hasChanges = Object.values(drafts).some(dirty);
  useEffect(() => { setSourcesDirty(hasChanges); }, [hasChanges, setSourcesDirty]);
  useEffect(() => {
    if (!hasChanges) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [hasChanges]);
  if (!project) return null;
  const path = project.path;
  const draft = drafts[active];
  const files = [...new Set([...project.files, ...Object.keys(drafts)])].filter((name) => name !== CONFIG).sort();
  const functions = analysis?.functions.filter((f) => !f.defined || f.mismatch) ?? [];

  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function read(name: string): Promise<Draft> {
    const file = await call<SourceFile>('file.read', { path, name });
    return { content: file.content, saved: file.content, revision: file.revision };
  }
  function open(name: string) {
    void perform(async () => {
      if (!drafts[name]) {
        const loaded = await read(name);
        setDrafts((all) => ({ ...all, [name]: loaded }));
      }
      setActive(name);
    });
  }
  function openConfig() {
    void perform(async () => {
      const current = drafts[CONFIG];
      if (!current || (!dirty(current) && current.revision !== project!.revision)) {
        const content = JSON.stringify(project!.model, null, 2) + '\n';
        setDrafts((all) => ({ ...all, [CONFIG]: { content, saved: content, revision: project!.revision } }));
      }
      setActive(CONFIG);
    });
  }
  function save() {
    if (!draft) return;
    void perform(async () => {
      if (active === CONFIG) {
        let model: unknown;
        try { model = JSON.parse(draft.content); } catch (e) { throw new Error(`efw.json 格式错误：${(e as Error).message}`); }
        if (!model || typeof model !== 'object' || Array.isArray(model)) throw new Error('efw.json 顶层必须是对象。');
        await call('project.save', { path, model, layout: project!.layout, rev: draft.revision ?? '' });
        const reloaded = await reload();
        const content = JSON.stringify(reloaded?.model ?? model, null, 2) + '\n';
        setDrafts((all) => ({ ...all, [CONFIG]: { content, saved: content, revision: reloaded?.revision ?? draft.revision } }));
        setNotice('已保存 efw.json，各页面已按新模型刷新。');
        return;
      }
      const pending = Object.entries(staged).filter(([, file]) => file === active).map(([name]) => name);
      const saved = await call<SourceFile>(draft.revision === null ? 'file.create' : 'file.write', {
        path, name: active, content: draft.content,
        ...(draft.revision === null ? {} : { rev: draft.revision, ...(pending.length ? { add_functions: pending } : {}) }),
      });
      setDrafts((all) => ({ ...all, [active]: { content: saved.content, saved: saved.content, revision: saved.revision } }));
      setStaged((names) => Object.fromEntries(Object.entries(names).filter(([, file]) => file !== active)));
      setNotice(pending.length ? `已保存 ${active}，并补充了函数模板（请填写逻辑）。` : `已保存 ${active}`);
      await refresh();
    });
  }
  function prepareStub(fn: FnInfo) {
    void perform(async () => {
      const [stub] = await call<Stub[]>('project.stub', { model: project!.model, names: [fn.name] });
      if (!stub) throw new Error('函数配置已变更，请重新载入项目。');
      let current = drafts[stub.file];
      if (!current) {
        try { current = await read(stub.file); } catch (e) {
          if (!(e instanceof RpcError) || e.code !== 'NOT_FOUND') throw e;
          current = { content: stub.header, saved: '', revision: null };
        }
      }
      setDrafts((all) => ({ ...all, [stub.file]: { ...current, content: `${current.content}\n${stub.text}\n` } }));
      setActive(stub.file);
      setStaged((names) => ({ ...names, [fn.name]: stub.file }));
      setNotice(`已将 ${fn.name} 模板加入草稿，请填写 EFW USER 标记内的逻辑后保存。`);
    });
  }
  return <>
    <div><h1>代码</h1><p className="sub">编辑 src/ 与 board/ 中的逻辑；模板区域由工具维护。efw.json 是应用配置，保存后所有页面按新模型刷新。</p></div>
    {error && <div className="diag error" role="alert"><div>{error}<p className="hint">编辑内容仍保留在草稿中。发生冲突时，先复制需要保留的修改，再载入磁盘版本。</p></div></div>}
    {notice && <p className="sub" role="status">{notice}</p>}
    <div className="code-workspace card">
      <aside className="code-files" aria-label="源码文件">
        <h2>用户源码</h2>
        <button disabled={busy} aria-pressed={active === CONFIG} onClick={openConfig}><span className="id">{CONFIG}</span><span className="sub">应用配置{drafts[CONFIG] && dirty(drafts[CONFIG]) ? ' · 未保存' : ''}</span></button>
        {files.length ? files.map((name) => <button key={name} disabled={busy} aria-pressed={active === name} onClick={() => open(name)}><span className="id">{name}</span>{drafts[name] && dirty(drafts[name]) && <span className="sub">未保存</span>}</button>) : <p className="sub">还没有源码文件。</p>}
        <form onSubmit={(e) => { e.preventDefault(); setError(''); setNotice('');
          if (files.includes(newName)) { open(newName); return; }
          if (!/^(src|board)\/[a-zA-Z0-9_/-]+\.(c|h)$/.test(newName) || newName.includes('//')) { setError('请输入 src/ 或 board/ 下的 .c / .h 文件路径。'); return; }
          setDrafts((all) => ({ ...all, [newName]: { content: '#include "app.h"\n', saved: '', revision: null } })); setActive(newName);
        }}>
          <label htmlFor="source-name">新文件路径</label>
          <input id="source-name" className="input id" value={newName} onChange={(e) => setNewName(e.target.value)} disabled={busy} required />
          <button className="btn" disabled={busy}>新建草稿</button>
        </form>
      </aside>
      <section className="code-main" aria-label="代码编辑区">
        <header><span className="id">{active || '选择文件'}</span><span className="sub">{draft ? dirty(draft) ? '未保存' : '已保存' : ''}</span><span className="spacer" />
          {active === CONFIG
            ? <button className="btn" disabled={busy} onClick={() => void perform(async () => {
              const reloaded = await reload();
              const content = JSON.stringify(reloaded?.model ?? project!.model, null, 2) + '\n';
              setDrafts((all) => ({ ...all, [CONFIG]: { content, saved: content, revision: reloaded?.revision ?? project!.revision } }));
              setNotice('已载入磁盘模型。');
            })}>载入磁盘模型</button>
            : <button className="btn" disabled={busy || !draft || draft.revision === null} onClick={() => {
              if (dirty(draft) && !window.confirm('载入磁盘版本会丢弃此文件的草稿修改，继续吗？')) return;
              void perform(async () => { const loaded = await read(active); setDrafts((all) => ({ ...all, [active]: loaded })); setStaged((names) => Object.fromEntries(Object.entries(names).filter(([, file]) => file !== active))); await refresh(); });
            }}>载入磁盘版本</button>}
          <button className="btn primary" disabled={busy || !draft || !dirty(draft)} onClick={save}>{busy ? '处理中…' : '保存文件'}</button>
        </header>
        <div className="code-editor">{draft ? <Suspense fallback={<p className="empty">正在载入代码编辑器…</p>}><SourceEditor path={`${path}/${active}`} language={active === CONFIG ? 'json' : 'c'} value={draft.content} readOnly={busy}
          onRejected={() => setNotice(TEMPLATE_NOTICE)}
          onChange={(content) => setDrafts((all) => ({ ...all, [active]: { ...all[active], content } }))} /></Suspense> : <p className="empty">选择左侧文件开始编辑，或创建一个源码草稿。</p>}</div>
      </section>
    </div>
    <section className="card" aria-label="待实现函数"><header><h2>待实现函数</h2><span className="sub">依据磁盘源码分析</span></header>
      {!analysis ? <p className="empty">正在分析函数…</p> : functions.length === 0 ? <p className="empty">没有待补充的函数。</p> : functions.map((fn) => <div className="code-function" key={fn.name}>
        <div><code>{fn.signature}</code><p className="sub">{fn.file} · {fn.role}</p>{fn.mismatch && <p className="err-text">{fn.mismatch}</p>}</div>
        <button className="btn" disabled={busy || !!staged[fn.name]} onClick={() => fn.mismatch ? open(fn.file) : prepareStub(fn)}>{fn.mismatch ? '打开修正签名' : staged[fn.name] ? '已加入草稿' : '创建函数模板'}</button>
      </div>)}
    </section>
  </>;
}
