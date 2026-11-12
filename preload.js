const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  invoke: (channel, data) => ipcRenderer.invoke(channel, data),
  on: (channel, fn) => ipcRenderer.on(channel, (_e, payload) => fn(payload)),
});
