import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { efwBridge } from './tools/bridge.mjs';

export default defineConfig({
  plugins: [react(), efwBridge()],
  base: './',
  // 预先发现懒加载的编辑器依赖，避免首次打开源码时 Vite 触发整页重载。
  optimizeDeps: { include: ['@monaco-editor/react', 'monaco-editor/esm/vs/editor/editor.api', 'monaco-editor/esm/vs/basic-languages/cpp/cpp.js'] },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // 项目常放在 Windows 挂载盘（/mnt/d、/mnt/c）上，那里 inotify 收不到事件，
    // 热更新会静默失效、服务的是旧模块。用轮询兜底，但要排除大目录，
    // 否则每轮都要 stat 上万个 node_modules 文件，会把磁盘和测试拖垮。
    watch: {
      usePolling: true,
      interval: 1200,
      ignored: ['**/node_modules/**', '**/dist/**', '**/release/**', '**/backend-bin/**', '**/.efw/**', '**/test-results/**', '**/playwright-report/**', '**/.git/**', '**/.venv/**'],
    },
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 4200 },
});
