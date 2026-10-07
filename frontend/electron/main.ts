import { app, BrowserWindow, shell } from "electron";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import http from "http";

const BACKEND_URL = "http://127.0.0.1:11434";
const isDev = !app.isPackaged;

let backendProc: ChildProcess | null = null;
let mainWin: BrowserWindow | null = null;

// ── backend health check ──────────────────────────────────────────────────────
function checkBackend(): Promise<boolean> {
  return new Promise(resolve => {
    const req = http.get(`${BACKEND_URL}/health`, res => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

// ── wait until backend is ready (up to 30 s) ─────────────────────────────────
async function waitForBackend(maxMs = 30_000): Promise<boolean> {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    if (await checkBackend()) return true;
    await new Promise(r => setTimeout(r, 600));
  }
  return false;
}

// ── launch Python backend ─────────────────────────────────────────────────────
function spawnBackend(): void {
  // root of the repo relative to the dist-electron/ folder in packaged app,
  // or relative to project root in dev
  const repoRoot = isDev
    ? path.join(__dirname, "..", "..")          // herama/
    : path.join(process.resourcesPath, "app");  // resources/app/ after packaging

  const py = process.platform === "win32" ? "python" : "python3";

  backendProc = spawn(
    py,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "11434", "--log-level", "warning"],
    {
      cwd: repoRoot,
      windowsHide: true,
      detached: false,
      stdio: "ignore",
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    }
  );

  backendProc.on("error", err => {
    console.error("backend spawn error:", err.message);
  });
}

// ── create main window ────────────────────────────────────────────────────────
function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 860,
    minHeight: 560,
    backgroundColor: "#1c1c1e",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    win.loadURL("http://localhost:5173");
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  return win;
}

// ── loading splash ────────────────────────────────────────────────────────────
function showSplash(): BrowserWindow {
  const splash = new BrowserWindow({
    width: 340,
    height: 220,
    frame: false,
    resizable: false,
    center: true,
    backgroundColor: "#1c1c1e",
    alwaysOnTop: true,
  });
  splash.loadURL(`data:text/html,
    <html><body style="margin:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
      height:100vh;background:#1c1c1e;color:#aeaeb2;font-family:system-ui;font-size:14px;gap:16px">
      <div style="color:#f97316;font-size:36px">◈</div>
      <div style="font-weight:600;color:#f5f5f7;font-size:16px">herama</div>
      <div>starting backend…</div>
    </body></html>`);
  return splash;
}

// ── main entry ────────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  const alreadyUp = await checkBackend();

  if (!alreadyUp) {
    const splash = showSplash();
    spawnBackend();
    const ready = await waitForBackend(30_000);
    splash.destroy();
    if (!ready) {
      // still open the window; the frontend will show "backend offline"
    }
  }

  mainWin = createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) mainWin = createWindow();
});

app.on("before-quit", () => {
  if (backendProc && !backendProc.killed) {
    backendProc.kill();
  }
});
