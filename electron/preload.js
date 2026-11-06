const { contextBridge, ipcRenderer } = require('electron')

const portArg = process.argv.find((arg) => arg.startsWith('--neo-port='))
const port = portArg ? Number(portArg.split('=')[1]) : 47821

function subscribe(channel, callback) {
  const handler = (_event, payload) => callback(payload)
  ipcRenderer.on(channel, handler)
  return () => ipcRenderer.removeListener(channel, handler)
}

contextBridge.exposeInMainWorld('neo', {
  apiBase: `http://127.0.0.1:${port}`,
  info: () => ipcRenderer.invoke('app:info'),
  window: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    maximize: () => ipcRenderer.invoke('window:maximize'),
    close: () => ipcRenderer.invoke('window:close'),
    isMaximized: () => ipcRenderer.invoke('window:is-maximized'),
    onMaximized: (callback) => subscribe('window:maximized', callback),
  },
  openExternal: (url) => ipcRenderer.invoke('shell:open-external', url),
  pickDirectory: (title) => ipcRenderer.invoke('dialog:pick-directory', title),
  pickFile: (title, filters) => ipcRenderer.invoke('dialog:pick-file', { title, filters }),
  onCloseRequest: (callback) => subscribe('app:request-close', callback),
  closeReady: () => ipcRenderer.send('app:close-ready'),
  onBackendLog: (callback) => subscribe('backend:log', callback),
})
