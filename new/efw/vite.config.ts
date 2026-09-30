import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { efwBridge } from './tools/bridge.mjs';

export default defineConfig({
  plugins: [react(), efwBridge()],
  base: './',
  // 预先发现懒加载的编辑器依赖，避免首次打开源码时 Vite 触发整页重载。
  optimizeDeps: { include: ['@monaco-editor/react', 'monaco-editor/esm/vs/editor/editor.api', 'monaco-editor/esm/vs/basic-languages/cpp/cpp.js'] },
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  build: { outDir: 'dist', chunkSizeWarningLimit: 4200 },
});
