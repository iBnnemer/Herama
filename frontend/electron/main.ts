import { app, BrowserWindow, shell } from "electron";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import http from "http";

const BACKEND_PORT = 11434;
const BACKEND_URL  = `http://127.0.0.1:${BACKEND_PORT}`;
const isDev        = !app.isPackaged;

let backendProc: ChildProcess | null = null;

function checkBackend(): Promise<boolean> {
  return new Promise(resolve => {
    const req = http.get(`${BACKEND_URL}/health`, res => {
      resolve(res.statusCode === 200);
    });
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

// Only called when running as a packaged app (no START.bat)
function trySpawnBackend(): void {
  const repoRoot = path.join(process.resourcesPath, "app");
  const py = process.platform === "win32" ? "python" : "python3";
  backendProc = spawn(
    py,
    ["-m", "uvicorn", "app.main:app",
     "--host", "127.0.0.1",
     "--port", String(BACKEND_PORT),
     "--log-level", "warning"],
    { cwd: repoRoot, windowsHide: true, stdio: "ignore",
      env: { ...process.env, PYTHONUNBUFFERED: "1" } }
  );
  backendProc.on("error", err =>
    console.error("[herama] backend error:", err.message));
}

function createWindow(): void {
  const win = new BrowserWindow({
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

  win.once("ready-to-show", () => win.show());

  if (isDev) {
    win.loadURL(process.env["ELECTRON_RENDERER_URL"] || "http://localhost:5173");
    // uncomment to debug: win.webContents.openDevTools();
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(async () => {
  const alreadyUp = await checkBackend();
  if (!alreadyUp && !isDev) {
    // packaged mode: spawn backend ourselves
    trySpawnBackend();
    await waitForBackend(20_000);
  }
  // dev mode: START.bat already started the backend
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
});
