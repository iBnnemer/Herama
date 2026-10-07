import { app, BrowserWindow, shell } from "electron";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import http from "http";

const BACKEND_PORT = 11434;
const BACKEND_URL  = `http://127.0.0.1:${BACKEND_PORT}`;
const isDev        = !app.isPackaged;

let backendProc: ChildProcess | null = null;
let mainWin: BrowserWindow | null = null;

// ── health check ──────────────────────────────────────────────────────────────
function checkBackend(): Promise<boolean> {
  return new Promise(resolve => {
    const req = http.get(`${BACKEND_URL}/health`, res => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

async function waitForBackend(maxMs = 30_000): Promise<boolean> {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    if (await checkBackend()) return true;
    await new Promise(r => setTimeout(r, 700));
  }
  return false;
}

// ── spawn Python backend ──────────────────────────────────────────────────────
function spawnBackend(): void {
  const repoRoot = isDev
    ? path.join(__dirname, "..", "..")
    : path.join(process.resourcesPath, "app");

  const pyCmd = process.platform === "win32" ? "python" : "python3";

  backendProc = spawn(
    pyCmd,
    ["-m", "uvicorn", "app.main:app",
     "--host", "127.0.0.1",
     "--port", String(BACKEND_PORT),
     "--log-level", "warning"],
    {
      cwd: repoRoot,
      windowsHide: true,
      detached: false,
      stdio: "ignore",
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    }
  );

  backendProc.on("error", err => {
    console.error("[herama] backend spawn error:", err.message);
  });
}

// ── loading splash ────────────────────────────────────────────────────────────
function createSplash(): BrowserWindow {
  const splash = new BrowserWindow({
    width: 320,
    height: 200,
    frame: false,
    resizable: false,
    center: true,
    backgroundColor: "#1c1c1e",
    alwaysOnTop: true,
    skipTaskbar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  splash.loadURL(
    "data:text/html;charset=utf-8," +
    encodeURIComponent(`<!doctype html>
<html><body style="margin:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;height:100vh;
  background:#1c1c1e;color:#aeaeb2;font-family:system-ui,sans-serif;
  font-size:14px;gap:14px">
  <div style="color:#f97316;font-size:32px;font-weight:700">herama</div>
  <div>starting backend...</div>
</body></html>`)
  );
  return splash;
}

// ── main window ───────────────────────────────────────────────────────────────
function createWindow(): void {
  mainWin = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 860,
    minHeight: 560,
    backgroundColor: "#1c1c1e",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWin.once("ready-to-show", () => { mainWin?.show(); });

  if (isDev) {
    mainWin.loadURL("http://localhost:5173");
  } else {
    mainWin.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWin.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWin.on("closed", () => { mainWin = null; });
}

// ── entry ─────────────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  const alreadyUp = await checkBackend();

  if (!alreadyUp) {
    const splash = createSplash();
    spawnBackend();
    await waitForBackend(30_000);
    splash.destroy();
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
  if (backendProc && !backendProc.killed) {
    backendProc.kill();
  }
});
