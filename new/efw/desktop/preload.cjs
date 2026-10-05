// 渲染进程与主进程之间唯一的通道：只暴露白名单方法与事件订阅，不给 node 能力。
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('efw', {
  call: (method, params) => ipcRenderer.invoke('efw:call', method, params ?? {}),
  pickDirectory: () => ipcRenderer.invoke('efw:pickDirectory'),
  pickFile: (filters) => ipcRenderer.invoke('efw:pickFile', filters),
  onEvent: (fn) => {
    const handler = (_e, msg) => fn(msg);
    ipcRenderer.on('efw:event', handler);
    return () => ipcRenderer.off('efw:event', handler);
  },
});
