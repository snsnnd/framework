// Monaco 与 worker 都由 Vite 本地打包，不访问 CDN。编辑器与 Diff 视图共用这里。
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import { conf, language } from 'monaco-editor/esm/vs/basic-languages/cpp/cpp.js';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });
monaco.languages.register({ id: 'c', extensions: ['.c', '.h'] });
monaco.languages.setLanguageConfiguration('c', conf);
monaco.languages.setMonarchTokensProvider('c', language);
monaco.languages.register({ id: 'json' });
monaco.languages.setMonarchTokensProvider('json', {
  tokenizer: {
    root: [
      [/[{}[\],:]/, 'delimiter'],
      [/"(?:[^"\\]|\\.)*"/, 'string'],
      [/-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/, 'number'],
      [/\b(?:true|false|null)\b/, 'keyword'],
    ],
  },
});

export function languageFor(path: string): 'c' | 'json' | 'plaintext' {
  if (path.endsWith('.c') || path.endsWith('.h')) return 'c';
  if (path.endsWith('.json')) return 'json';
  return 'plaintext';
}
