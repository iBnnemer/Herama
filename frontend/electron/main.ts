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

/** Starts the backend without a console window; it stops again when the app quits. */
function trySpawnBackend(): void {
  const repoRoot = isDev ? path.join(__dirname, "..", "..") : path.join(process.resourcesPath, "app");
  const py = process.platform === "win32" ? "python" : "python3";
  let out: number | "ignore" = "ignore";
  try { out = fs.openSync(path.join(repoRoot, "herama-backend.log"), "w"); } catch { /* read-only folder: no log */ }
  backendProc = spawn(
    py,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT), "--log-level", isDev ? "info" : "warning"],
    { cwd: repoRoot, windowsHide: true, stdio: ["ignore", out, out], env: { ...process.env, PYTHONUNBUFFERED: "1" } }
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

  ipcMain.handle("fs:knowledge", async (_e, dirs: string[], budget: number) => {
    const skip = new Set(["node_modules", ".git", "dist", "build", "out", "__pycache__", ".venv", "venv", ".next", "target"]);
    const tree: string[] = [];
    const chunks: string[] = [];
    let room = Math.max(0, budget);
    const walk = async (root: string, dir: string, depth: number): Promise<void> => {
      if (depth > 6 || tree.length >= 400) return;
      let entries: fs.Dirent[];
      try { entries = await fs.promises.readdir(dir, { withFileTypes: true }); } catch { return; }
      entries.sort((a, b) => Number(b.isDirectory()) - Number(a.isDirectory()) || a.name.localeCompare(b.name));
      for (const d of entries) {
        if (d.name.startsWith(".") || skip.has(d.name) || tree.length >= 400) continue;
        const full = path.join(dir, d.name);
        const rel = path.relative(root, full).split(path.sep).join("/");
        if (d.isDirectory()) { tree.push(`${path.basename(root)}/${rel}/`); await walk(root, full, depth + 1); continue; }
        tree.push(`${path.basename(root)}/${rel}`);
        try {
          const st = await fs.promises.stat(full);
          if (st.size > 100_000 || room < 600) continue;
          const buf = await fs.promises.readFile(full);
          if (buf.subarray(0, 4096).includes(0)) continue;
          let text = buf.toString("utf8");
          const head = `### ${path.basename(root)}/${rel}\n`;
          if (head.length + text.length > room) text = text.slice(0, Math.max(0, room - head.length - 20)) + "\n[truncated]";
          chunks.push(head + text);
          room -= head.length + text.length;
        } catch { /* unreadable file */ }
      }
    };
    for (const root of dirs) await walk(root, root, 0);
    return { tree: tree.join("\n"), text: chunks.join("\n\n") };
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
  if (!alreadyUp) {
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
  if (backendProc && !backendProc.killed) killTree(backendProc);
  termProcs.forEach(killTree);
});
