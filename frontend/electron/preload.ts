import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("herama", {
  backend: "http://127.0.0.1:11434",
});
