import { app, BrowserWindow, shell, ipcMain, dialog, IpcMainInvokeEvent } from "electron";
import { spawn, ChildProcess } from "child_process";
import fs from "fs";
import path from "path";
import http from "http";

const BACKEND_PORT = 11434;
const BACKEND_URL  = `http://127.0.0.1:${BACKEND_PORT}`;
const isDev        = !app.isPackaged;

let backendProc: ChildProcess | null = null;
const termProcs = new Map<string, ChildProcess>();

function checkBackend(): Promise<boolean> {
  return new Promise(resolve => {
    const req = http.get(`${BACKEND_URL}/health`, res => resolve(res.statusCode === 200));
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

async function waitForBackend(maxMs = 20_000): Promise<void> {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    if (await checkBackend()) return;
    await new Promise(r => setTimeout(r, 500));
  }
}

function trySpawnBackend(): void {
  const repoRoot = path.join(process.resourcesPath, "app");
  const py = process.platform === "win32" ? "python" : "python3";
  backendProc = spawn(
    py,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT), "--log-level", "warning"],
    { cwd: repoRoot, windowsHide: true, stdio: "ignore", env: { ...process.env, PYTHONUNBUFFERED: "1" } }
  );
  backendProc.on("error", err => console.error("[herama] backend error:", err.message));
}

function killTree(proc: ChildProcess): void {
  if (!proc.pid) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(proc.pid), "/t", "/f"], { windowsHide: true });
  } else {
    proc.kill("SIGTERM");
  }
}

function registerIpc(): void {
  ipcMain.handle("fs:default", () => (isDev ? path.join(__dirname, "..", "..") : app.getPath("home")));

  ipcMain.handle("fs:list", async (_e, dir: string) => {
    const entries = await fs.promises.readdir(dir, { withFileTypes: true });
    return entries
      .map(d => ({ name: d.name, isDir: d.isDirectory() }))
      .sort((a, b) => Number(b.isDir) - Number(a.isDir) || a.name.localeCompare(b.name))
      .slice(0, 800);
  });

  ipcMain.handle("fs:read", async (_e, file: string) => {
    const fh = await fs.promises.open(file, "r");
    try {
      const buf = Buffer.alloc(200_000);
      const { bytesRead } = await fh.read(buf, 0, buf.length, 0);
      return buf.subarray(0, bytesRead).toString("utf8");
    } finally {
      await fh.close();
    }
  });

  ipcMain.handle("fs:resolve", async (_e, cwd: string, target: string) => {
    const full = path.resolve(cwd, target);
    try {
      const st = await fs.promises.stat(full);
      return st.isDirectory() ? full : null;
    } catch {
      return null;
    }
  });

  ipcMain.handle("fs:pick", async () => {
    const r = await dialog.showOpenDialog({ properties: ["openDirectory"] });
    return r.canceled ? null : r.filePaths[0];
  });

  ipcMain.handle("term:run", (e: IpcMainInvokeEvent, id: string, cmd: string, cwd: string) => {
    const proc = spawn(cmd, { shell: true, cwd, windowsHide: true });
    termProcs.set(id, proc);
    const send = (data: string, code?: number | null) => {
      if (!e.sender.isDestroyed()) e.sender.send("term:data", { id, data, code });
    };
    proc.stdout?.on("data", d => send(d.toString()));
    proc.stderr?.on("data", d => send(d.toString()));
    proc.on("error", err => send(`${err.message}\n`));
    proc.on("close", code => { termProcs.delete(id); send("", code ?? -1); });
  });

  ipcMain.handle("term:kill", (_e, id: string) => {
    const proc = termProcs.get(id);
    if (proc) killTree(proc);
  });
}

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1400,
    height: 860,
    minWidth: 900,
    minHeight: 560,
    backgroundColor: "#1c1c1e",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });

  win.once("ready-to-show", () => win.show());

  if (isDev) {
    win.loadURL(process.env["ELECTRON_RENDERER_URL"] || "http://localhost:5173");
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(async () => {
  registerIpc();
  const alreadyUp = await checkBackend();
  if (!alreadyUp && !isDev) {
    trySpawnBackend();
    await waitForBackend(20_000);
  }
  createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on("before-quit", () => {
  if (backendProc && !backendProc.killed) backendProc.kill();
  termProcs.forEach(killTree);
});
