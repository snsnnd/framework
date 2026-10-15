import { useEffect, useState } from 'react';
import { DiffEditor } from '@monaco-editor/react';
import { languageFor } from '../monaco';

export function DiffView({ path, before, after }: { path: string; before: string; after: string }) {
  const [dark, setDark] = useState(() => matchMedia('(prefers-color-scheme: dark)').matches);
  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)');
    const update = () => setDark(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return <DiffEditor original={before} modified={after} language={languageFor(path)} theme={dark ? 'vs-dark' : 'light'}
    loading={<p className="empty">正在载入差异视图…</p>}
    options={{ readOnly: true, renderSideBySide: false, minimap: { enabled: false }, fontSize: 12,
      scrollBeyondLastLine: false, automaticLayout: true, renderOverviewRuler: false, originalEditable: false,
      hideUnchangedRegions: { enabled: true }, ariaLabel: '生成文件差异' }} />;
}
