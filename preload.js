const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  getConfig: () => ipcRenderer.invoke('config:get'),
  getSession: () => ipcRenderer.invoke('session:get'),
  clearSession: () => ipcRenderer.invoke('session:clear'),
  sessionUpdate: (patch) => ipcRenderer.invoke('session:update', patch),
  login: (serverAuthUrl, username, password, empId) => ipcRenderer.invoke('auth:login', { serverAuthUrl, username, password, empId }),
  logout: () => ipcRenderer.invoke('auth:logout'),
  get: (path, baseUrl) => ipcRenderer.invoke('api:get', { path, baseUrl }),
  post: (path, body, baseUrl) => ipcRenderer.invoke('api:post', { path, baseUrl, body }),
  hrmsGet: (path) => ipcRenderer.invoke('hrms:get', { path }),
  netStatus: () => ipcRenderer.invoke('net:status'),
  navTo: (name) => ipcRenderer.invoke('nav:to', { name })
  ,
  onPowerBreak: (callback) => {
    try { ipcRenderer.on('power:break', (_evt, payload) => { try { callback(payload); } catch (_) {} }); } catch (_) {}
  },
  onWorkAutoStart: (callback) => {
    try { ipcRenderer.on('work:autoStart', (_evt, payload) => { try { callback(payload); } catch (_) {} }); } catch (_) {}
  },
  // Window controls (frameless)
  winMinimize: () => ipcRenderer.invoke('window:minimize'),
  winMaximizeToggle: () => ipcRenderer.invoke('window:maximizeToggle'),
  winClose: () => ipcRenderer.invoke('window:close'),
  
  // Work session API (local prototype; can be swapped to backend later)
  workStart: () => ipcRenderer.invoke('work:start'),
  workBreakToggle: () => ipcRenderer.invoke('work:breakToggle'),
  workEnd: () => ipcRenderer.invoke('work:end'),
  workState: () => ipcRenderer.invoke('work:state'),
  workSummary: (days) => ipcRenderer.invoke('work:summary', { days }),
  // Updater controls
  updaterCheck: () => ipcRenderer.invoke('updater:check'),
  updaterDownload: () => ipcRenderer.invoke('updater:download'),
  updaterInstall: () => ipcRenderer.invoke('updater:install'),
  // App info
  appVersion: () => ipcRenderer.invoke('app:version'),
  getVersion: () => ipcRenderer.invoke('app:version'),
  getSystemInfo: () => ipcRenderer.invoke('system:info'),
  // Native notification
  notify: (title, body) => ipcRenderer.invoke('notify', { title, body })
});
