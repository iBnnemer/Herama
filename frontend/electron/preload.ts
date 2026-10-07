import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("herama", {
  backend: "http://127.0.0.1:11434",
  defaultDir: () => ipcRenderer.invoke("fs:default"),
  fsList: (dir: string) => ipcRenderer.invoke("fs:list", dir),
  fsRead: (file: string) => ipcRenderer.invoke("fs:read", file),
  fsResolve: (cwd: string, target: string) => ipcRenderer.invoke("fs:resolve", cwd, target),
  fsKnowledge: (dirs: string[], budget: number) => ipcRenderer.invoke("fs:knowledge", dirs, budget),
  pickFolder: () => ipcRenderer.invoke("fs:pick"),
  termRun: (id: string, cmd: string, cwd: string) => ipcRenderer.invoke("term:run", id, cmd, cwd),
  termKill: (id: string) => ipcRenderer.invoke("term:kill", id),
  onTermData: (cb: (m: { id: string; data: string; code?: number | null }) => void) => {
    const handler = (_e: unknown, m: { id: string; data: string; code?: number | null }) => cb(m);
    ipcRenderer.on("term:data", handler);
    return () => ipcRenderer.removeListener("term:data", handler);
  },
});
