/**
 * UBOS desktop shell (Electron main process).
 *
 * Orchestrates the local stack:
 *   1. Verify/prompt for the license (offline, 2-machine).
 *   2. Spawn bundled mongod on a loopback port with data in %APPDATA%\UBOS\db.
 *   3. Spawn the PyInstaller backend (uvicorn) that also serves the React build.
 *   4. Load the app window at http://127.0.0.1:<port> once /api/health is up.
 *   5. Tree-kill both child processes on quit.
 *
 * Dev vs packaged:
 *   - packaged: sidecars live under process.resourcesPath (backend/, mongodb/, frontend/).
 *   - dev: backend runs via the repo venv's python; mongod = `mongod` on PATH
 *     (or $UBOS_MONGOD); frontend served from ../frontend/build.
 */
const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const http = require("http");
const crypto = require("crypto");
const { spawn } = require("child_process");

const isDev = !app.isPackaged;

// Embedded vendor public key. Replace after `desktop/licensing/keygen.py`.
// Env override is honored so dev/CI can inject a test key.
const LICENSE_PUBLIC_KEY =
  process.env.UBOS_LICENSE_PUBLIC_KEY || "REPLACE_WITH_YOUR_ED25519_PUBLIC_KEY";

let backendProc = null;
let mongoProc = null;
let mainWindow = null;
let licenseWindow = null;
let splashWindow = null;
let BACKEND_PORT = 0;
let MONGO_PORT = 0;

const userData = () => app.getPath("userData"); // %APPDATA%\UBOS
const APP_ICON = () => path.join(__dirname, "assets", "icon.png");

function resourcePath(...p) {
  return isDev
    ? path.join(__dirname, "..", ...p)
    : path.join(process.resourcesPath, ...p);
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function ensureDirs() {
  for (const d of ["db", "uploads"]) {
    fs.mkdirSync(path.join(userData(), d), { recursive: true });
  }
}

function getOrCreateSecret(name) {
  const f = path.join(userData(), name);
  if (fs.existsSync(f)) return fs.readFileSync(f, "utf8").trim();
  const s = crypto.randomBytes(32).toString("base64url");
  fs.writeFileSync(f, s);
  return s;
}

function isFirstRun() {
  return !fs.existsSync(path.join(userData(), ".seeded"));
}
function markSeeded() {
  fs.writeFileSync(path.join(userData(), ".seeded"), "1");
}

function mongoExe() {
  return isDev
    ? process.env.UBOS_MONGOD || "mongod"
    : resourcePath("mongodb", "mongod.exe");
}

function backendSpec() {
  if (isDev) {
    const py =
      process.env.UBOS_PY ||
      path.join(__dirname, "..", "backend", "venv", "bin", "python");
    return {
      cmd: py,
      args: ["-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
      cwd: path.join(__dirname, "..", "backend"),
    };
  }
  return {
    cmd: resourcePath("backend", "ubos-backend.exe"),
    args: ["--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    cwd: resourcePath("backend"),
  };
}

function httpGetJson(pathname) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: "127.0.0.1", port: BACKEND_PORT, path: pathname, timeout: 3000 },
      (r) => {
        let d = "";
        r.on("data", (c) => (d += c));
        r.on("end", () => {
          try {
            resolve(JSON.parse(d));
          } catch {
            resolve(null);
          }
        });
      }
    );
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
  });
}

function httpPostJson(pathname, body) {
  return new Promise((resolve) => {
    const data = Buffer.from(JSON.stringify(body));
    const req = http.request(
      {
        host: "127.0.0.1",
        port: BACKEND_PORT,
        path: pathname,
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": data.length },
      },
      (r) => {
        let d = "";
        r.on("data", (c) => (d += c));
        r.on("end", () => {
          try {
            resolve(JSON.parse(d));
          } catch {
            resolve(null);
          }
        });
      }
    );
    req.on("error", () => resolve(null));
    req.write(data);
    req.end();
  });
}

async function waitForHealth(timeoutMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const h = await httpGetJson("/api/health");
    if (h && h.status === "ok") return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function startServices() {
  ensureDirs();
  MONGO_PORT = await findFreePort();
  BACKEND_PORT = await findFreePort();

  mongoProc = spawn(
    mongoExe(),
    ["--dbpath", path.join(userData(), "db"), "--port", String(MONGO_PORT), "--bind_ip", "127.0.0.1"],
    { stdio: "ignore" }
  );
  mongoProc.on("error", (e) => console.error("[mongod] failed:", e.message));

  const b = backendSpec();
  const env = {
    ...process.env,
    MONGO_URL: `mongodb://127.0.0.1:${MONGO_PORT}`,
    DB_NAME: "ubos",
    JWT_SECRET: getOrCreateSecret("jwt_secret"),
    SECRET_KEY: getOrCreateSecret("jwt_secret"),
    LOCAL_STORAGE_ROOT: path.join(userData(), "uploads"),
    CORS_ORIGINS: `http://127.0.0.1:${BACKEND_PORT}`,
    UBOS_DESKTOP: "true",
    // Single-vertical (furnishing) build for the friend: global fields, no
    // industry starter packs/demo, one workspace, furnishing first-run seed.
    UBOS_SINGLE_BUSINESS: "true",
    UBOS_LICENSE_PUBLIC_KEY: LICENSE_PUBLIC_KEY,
    UBOS_LICENSE_PATH: path.join(userData(), "ubos.lic"),
    FRONTEND_DIR: resourcePath("frontend"),
    APP_BASE_URL: `http://127.0.0.1:${BACKEND_PORT}`,
    PUBLIC_APP_URL: `http://127.0.0.1:${BACKEND_PORT}`,
    SEED_USERS: isFirstRun() ? "true" : "false",
  };
  backendProc = spawn(b.cmd, b.args, { cwd: b.cwd, env, stdio: "ignore" });
  backendProc.on("error", (e) => console.error("[backend] failed:", e.message));

  const ok = await waitForHealth();
  if (ok && isFirstRun()) markSeeded();
  return ok;
}

function createSplash() {
  splashWindow = new BrowserWindow({
    width: 360,
    height: 300,
    frame: false,
    resizable: false,
    center: true,
    backgroundColor: "#0d9488",
    icon: APP_ICON(),
    webPreferences: { contextIsolation: true },
  });
  splashWindow.loadFile(path.join(__dirname, "splash.html"));
  splashWindow.on("closed", () => (splashWindow = null));
}

function closeSplash() {
  if (splashWindow) {
    splashWindow.close();
    splashWindow = null;
  }
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    title: "UBOS",
    icon: APP_ICON(),
    webPreferences: { contextIsolation: true },
  });
  mainWindow.loadURL(`http://127.0.0.1:${BACKEND_PORT}`);
  mainWindow.on("closed", () => (mainWindow = null));
}

function createLicenseWindow() {
  licenseWindow = new BrowserWindow({
    width: 560,
    height: 540,
    title: "UBOS — Activation",
    resizable: false,
    icon: APP_ICON(),
    webPreferences: {
      preload: path.join(__dirname, "license-preload.js"),
      contextIsolation: true,
    },
  });
  licenseWindow.loadFile(path.join(__dirname, "license.html"));
  licenseWindow.on("closed", () => (licenseWindow = null));
}

// ── IPC used by the activation screen ──
ipcMain.handle("license:status", async () => httpGetJson("/api/license/status"));

ipcMain.handle("license:load", async () => {
  const r = await dialog.showOpenDialog({
    title: "Select your ubos.lic file",
    filters: [{ name: "UBOS License", extensions: ["lic", "txt"] }],
    properties: ["openFile"],
  });
  if (r.canceled || !r.filePaths[0]) return { ok: false, reason: "cancelled" };
  const content = fs.readFileSync(r.filePaths[0], "utf8").trim();
  const result = await httpPostJson("/api/license/load", { license: content });
  if (result && result.licensed) {
    createMainWindow();
    if (licenseWindow) licenseWindow.close();
    return { ok: true };
  }
  return { ok: false, reason: (result && (result.detail || result.reason)) || "invalid license" };
});

app.whenReady().then(async () => {
  createSplash();
  const ok = await startServices();
  if (!ok) {
    closeSplash();
    dialog.showErrorBox("UBOS", "The UBOS engine failed to start. Please reinstall or contact support.");
    app.quit();
    return;
  }
  const status = await httpGetJson("/api/license/status");
  if (status && status.desktop && !status.licensed) {
    createLicenseWindow();
  } else {
    createMainWindow();
  }
  closeSplash();
});

// ── shutdown: tree-kill both children ──
function killTree(proc) {
  if (!proc || proc.killed) return;
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(proc.pid), "/T", "/F"]);
    } else {
      proc.kill("SIGTERM");
    }
  } catch {
    /* best effort */
  }
}
function shutdown() {
  killTree(backendProc);
  killTree(mongoProc);
}
app.on("before-quit", shutdown);
app.on("window-all-closed", () => {
  shutdown();
  app.quit();
});
process.on("exit", shutdown);
