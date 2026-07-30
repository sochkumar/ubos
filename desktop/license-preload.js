const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ubos", {
  status: () => ipcRenderer.invoke("license:status"),
  loadLicense: () => ipcRenderer.invoke("license:load"),
});
