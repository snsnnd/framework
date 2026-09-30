import { lazy, Suspense, useEffect, useState } from 'react';
import { call } from '../rpc';
import { useStore } from '../store';

const DiffView = lazy(() => import('../components/DiffView').then((m) => ({ default: m.DiffView })));
type Status = 'create' | 'update' | 'delete' | 'same' | 'conflict';
interface PreviewFile { path: string; status: Status; before: string; after: string }
interface Preview { token: string; files: PreviewFile[]; blocked: boolean; reason: string }
interface CommitResult { output: string; files: { path: string; status: Status }[] }

const STATUS: Record<Status, { label: string; cls: string }> = {
  create: { label: '新增', cls: 'ok' },
  update: { label: '更新', cls: 'warn' },
  delete: { label: '删除', cls: 'err' },
  conflict: { label: '冲突', cls: 'err' },
  same: { label: '未变化', cls: 'sub' },
};

export function Generate() {
  const { project, analysis } = useStore();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const hash = analysis?.hash ?? '';

  async function runPreview() {
    if (!project) return;
    setBusy(true); setError('');
    try {
      const result = await call<Preview>('generate.preview', { path: project.path, model: project.model });
      setPreview(result);
      setSelected((current) => (result.files.some((f) => f.path === current)
        ? current
        : result.files.find((f) => f.status !== 'same')?.path ?? result.files[0]?.path ?? ''));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  useEffect(() => { void runPreview(); }, [project?.path, hash]);

  async function commit() {
    if (!project || !preview || preview.blocked) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await call<CommitResult>('generate.commit', { path: project.path, model: project.model, token: preview.token });
      const written = result.files.filter((f) => f.status !== 'same').length;
      setNotice(`已生成 ${written} 个文件到 ${result.output}；原始文件保留在 .efw/backups/。`);
      setPreview(await call<Preview>('generate.preview', { path: project.path, model: project.model }));
    } catch (e) {
      setError((e as Error).message);
      try { setPreview(await call<Preview>('generate.preview', { path: project.path, model: project.model })); } catch { /* 后端已给出原因 */ }
    } finally { setBusy(false); }
  }

  if (!project) return null;
  const files = preview?.files ?? [];
  const changed = files.filter((f) => f.status !== 'same');
  const count = (status: Status) => files.filter((f) => f.status === status).length;
  const selectedFile = files.find((f) => f.path === selected);

  return <>
    <div><h1>生成</h1><p className="sub">把模型渲染成 generated/ 下的代码。先预览逐文件差异，再一次性写入；手改过的生成文件不会被覆盖。</p></div>
    {error && <div className="diag error" role="alert"><div>{error}</div></div>}
    {notice && <p className="sub" role="status">{notice}</p>}
    {preview?.blocked && <div className="diag error"><div>{preview.reason}</div></div>}
    <div className="generate-summary">
      {changed.length > 0 && <>
        {count('create') > 0 && <span className="chip ok">新增 {count('create')}</span>}
        {count('update') > 0 && <span className="chip warn">更新 {count('update')}</span>}
        {count('delete') > 0 && <span className="chip err">删除 {count('delete')}</span>}
        {count('conflict') > 0 && <span className="chip err">冲突 {count('conflict')}</span>}
      </>}
      {preview && !preview.blocked && changed.length === 0 && <span className="sub">generated/ 与当前模型一致，无需写入。</span>}
      <span className="spacer" />
      <button className="btn" disabled={busy} onClick={() => void runPreview()}>{busy ? '处理中…' : '重新预览'}</button>
      <button className="btn primary" disabled={busy || !preview || preview.blocked} onClick={() => void commit()}>提交生成</button>
    </div>
    <section className="card" aria-label="生成预览">
      <header><h2>文件差异</h2><span className="sub">{busy && !preview ? '正在预览…' : `${changed.length} 个文件将变更 · 输出到 generated/`}</span></header>
      <div className="generate-workspace">
        <div className="generate-files">
          {files.length ? files.map((file) => {
            const meta = STATUS[file.status];
            return <button key={file.path} data-path={file.path} aria-pressed={selected === file.path} onClick={() => setSelected(file.path)}>
              <span className="id">{file.path}</span>
              <span className={`chip ${meta.cls}`}>{meta.label}</span>
            </button>;
          }) : <p className="empty">{busy ? '正在预览…' : '没有可生成的文件。'}</p>}
        </div>
        <div className="generate-diff">
          {selectedFile ? (selectedFile.status === 'same'
            ? <p className="empty">{selectedFile.path} 与当前生成结果一致，没有差异。</p>
            : <Suspense fallback={<p className="empty">正在载入差异视图…</p>}>
              <DiffView path={selectedFile.path} before={selectedFile.before} after={selectedFile.after} />
            </Suspense>)
            : <p className="empty">选择左侧文件查看差异。</p>}
        </div>
      </div>
    </section>
  </>;
}
