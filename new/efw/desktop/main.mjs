// Electron 主进程：以 stdio 启动 Python 服务（开发时用源码，打包后用 PyInstaller 产物），
// 把 JSON Lines 转成 IPC；渲染进程只经 preload 的白名单方法调用。界面代码与浏览器版一致。
import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const isDev = !app.isPackaged;

/** 白名单：渲染进程只能调这些方法，其余一律拒绝。 */
const METHODS = new Set([
  'system.info', 'templates.list',
  'project.create', 'project.open', 'project.save', 'project.analyze', 'project.stub',
  'file.read', 'file.write', 'file.create',
  'generate.preview', 'generate.commit',
  'debug.start', 'debug.control', 'debug.send', 'debug.stop', 'debug.runs',
]);

let backend = null;
let seq = 0;
const pending = new Map();
const windows = new Set();

function backendCommand() {
  // 打包产物优先；开发时直接跑源码，虚拟目标构建还需要 runtime/ 与编译器
  const packaged = join(process.resourcesPath ?? '', 'backend-bin', process.platform === 'win32' ? 'efw-backend.exe' : 'efw-backend');
  if (!isDev) return [packaged];
  return [process.env.EFW_PYTHON ?? 'python3', ['-m', 'studio_core.server']];
}

function startBackend() {
  const [cmd, args = []] = backendCommand();
  const env = { ...process.env };
  // 让生成器找到 C 编译器与 runtime 目录（打包后 runtime 在 resources/runtime）
  if (!isDev) {
    env.EFW_RUNTIME = join(process.resourcesPath, 'runtime');
    if (process.platform === 'win32' && process.env.SystemRoot) {
      env.PATH = `${join(process.env.SystemRoot, 'System32')};${process.env.PATH ?? ''}`;
    }
  }
  const child = spawn(cmd, args, {
    stdio: ['pipe', 'pipe', 'pipe'],
    cwd: isDev ? join(here, '..') : undefined,
    env,
    windowsHide: true,
  });
  child.stderr.on('data', (chunk) => console.error('[backend]', String(chunk).trimEnd()));
  createInterface({ input: child.stdout }).on('line', (line) => {
    let msg;
    try { msg = JSON.parse(line); } catch { console.error('[backend] 忽略非协议输出：', line.slice(0, 200)); return; }
    if (msg.id != null && pending.has(msg.id)) {
      const done = pending.get(msg.id);
      pending.delete(msg.id);
      done(msg);
    } else if (msg.event) {
      for (const win of windows) {
        if (!win.isDestroyed()) win.webContents.send('efw:event', msg);
      }
    }
  });
  child.on('exit', (code) => {
    console.error(`[backend] 退出：${code}`);
    for (const done of pending.values()) done({ error: { code: 'INTERNAL', message: '后端服务已退出' } });
    pending.clear();
    backend = null;
  });
  child.on('error', (err) => console.error('[backend] 无法启动：', err.message));
  backend = child;
}

function stopBackend() {
  if (!backend) return;
  backend.stdin.write(JSON.stringify({ id: ++seq, method: 'debug.stop', params: { session: currentSession } }) + '\n');
  backend.kill();
  backend = null;
}

let currentSession = '';

function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    if (!METHODS.has(method)) { reject(new Error(`不允许的方法：${method}`)); return; }
    if (!backend) { reject(new Error('后端服务未启动')); return; }
    const id = ++seq;
    pending.set(id, (msg) => (msg.error ? reject(new Error(`${msg.error.code}: ${msg.error.message}`)) : resolve(msg.result)));
    backend.stdin.write(JSON.stringify({ id, method, params }) + '\n');
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    backgroundColor: '#14161a',
    title: 'EFW Studio',
    webPreferences: {
      preload: join(here, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  windows.add(win);
  win.on('closed', () => windows.delete(win));
  // 外部链接交给系统浏览器，窗口内只允许自己的页面
  win.webContents.setWindowOpenHandler(({ url }) => { void shell.openExternal(url); return { action: 'deny' }; });
  if (isDev) void win.loadURL(process.env.EFW_DEV_URL ?? 'http://127.0.0.1:5173/');
  else void win.loadFile(join(here, '..', 'dist', 'index.html'));
  return win;
}

ipcMain.handle('efw:call', async (_e, method, params) => call(method, params));
ipcMain.handle('efw:pickDirectory', async () => {
  const win = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0];
  const result = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] });
  return result.canceled ? null : result.filePaths[0];
});
ipcMain.handle('efw:pickFile', async (_e, filters) => {
  const win = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0];
  const result = await dialog.showOpenDialog(win, { properties: ['openFile'], filters });
  return result.canceled ? null : result.filePaths[0];
});
ipcMain.handle('efw:backendEnv', async () => ({ dev: isDev, runtime: backend?.spawnargs ?? null }));

app.whenReady().then(() => {
  startBackend();
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});
app.on('before-quit', stopBackend);