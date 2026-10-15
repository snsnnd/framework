import { useCallback, useEffect, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import '../monaco';
import { parseTemplate, templateSignature } from '../template';

const TYPING_KEYS = new Set(['Enter', 'Tab', 'Backspace', 'Delete']);

export default function SourceEditor({ path, language: lang = 'c', value, onChange, readOnly, onRejected }: {
  path: string; language?: 'c' | 'json'; value: string; onChange: (value: string) => void; readOnly: boolean; onRejected?: () => void;
}) {
  const [dark, setDark] = useState(() => matchMedia('(prefers-color-scheme: dark)').matches);
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const valueRef = useRef(value);
  const rejectedRef = useRef(onRejected);
  const lockedRef = useRef<string | null>(null);
  const editableRef = useRef<{ from: number; to: number }[]>([]);
  const decorationsRef = useRef<string[]>([]);
  valueRef.current = value;
  rejectedRef.current = onRejected;

  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)');
    const update = () => setDark(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const refresh = useCallback((text: string) => {
    const info = parseTemplate(text);
    lockedRef.current = templateSignature(text);
    editableRef.current = info.ok ? info.segments.filter((s) => s.editable) : [{ from: 0, to: text.length }];
    const model = editorRef.current?.getModel();
    if (!model) return;
    const locked = info.ok && info.fixed !== null
      ? info.segments.filter((s) => !s.editable).map((s) => ({
        range: monaco.Range.fromPositions(model.getPositionAt(s.from), model.getPositionAt(s.to)),
        options: { isWholeLine: true, className: 'efw-locked' },
      }))
      : [];
    decorationsRef.current = model.deltaDecorations(decorationsRef.current, locked);
  }, []);

  useEffect(() => {
    decorationsRef.current = [];
    refresh(valueRef.current);
  }, [path, refresh]);

  useEffect(() => { refresh(value); }, [value, refresh]);

  const handleMount = useCallback((editor: monaco.editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.onKeyDown((e) => {
      const key = e.browserEvent.key;
      const typing = key.length === 1 || TYPING_KEYS.has(key) || ((e.ctrlKey || e.metaKey) && (key === 'v' || key === 'x'));
      if (!typing) return;
      const model = editor.getModel();
      const selection = editor.getSelection();
      if (!model || !selection) return;
      const from = model.getOffsetAt(selection.getStartPosition());
      const to = model.getOffsetAt(selection.getEndPosition());
      if (!editableRef.current.some((r) => from >= r.from && to <= r.to)) {
        e.preventDefault();
        e.stopPropagation();
        rejectedRef.current?.();
      }
    });
    refresh(valueRef.current);
  }, [refresh]);

  const handleChange = useCallback((next: string | undefined) => {
    const text = next ?? '';
    const previous = lockedRef.current;
    const signature = templateSignature(text);
    if (previous !== null && previous !== 'INVALID' && signature !== previous) {
      editorRef.current?.trigger('efw-template', 'undo', null);
      rejectedRef.current?.();
      return;
    }
    refresh(text);
    onChange(text);
  }, [refresh, onChange]);

  return <Editor path={path} language={lang} theme={dark ? 'vs-dark' : 'light'} value={value}
    onMount={handleMount} onChange={handleChange} loading={<p className="empty">正在载入代码编辑器…</p>}
    options={{ automaticLayout: true, minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false,
      readOnly, tabSize: 4, ariaLabel: '源码编辑器', wordWrap: 'on' }} />;
}
