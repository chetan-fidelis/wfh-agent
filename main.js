const { app, BrowserWindow, ipcMain, nativeTheme, Notification, powerMonitor, Tray, Menu, autoUpdater } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const https = require('https');
let axios; try { axios = require('axios'); } catch (_) { axios = null; }

// Minimal HTTP helpers (fallback if axios is unavailable)
function requestRaw(urlStr, { method = 'GET', headers = {}, body = undefined, timeout = 8000, insecure = false } = {}) {
  return new Promise((resolve, reject) => {
    try {
      const u = new URL(urlStr);
      const isHttps = u.protocol === 'https:';
      const mod = isHttps ? require('https') : require('http');
      const opts = {
        method,
        headers: { ...(headers || {}) },
        rejectUnauthorized: !insecure,
      };
      if (insecure && isHttps) {
        opts.agent = new https.Agent({ rejectUnauthorized: false });
      }
      const req = mod.request(u, opts, (res) => {
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => { data += chunk || ''; });
        res.on('end', () => {
          resolve({ status: res.statusCode || 0, headers: res.headers || {}, body: data });
        });
      });
      req.on('error', reject);
      if (timeout) {
        req.setTimeout(timeout, () => { try { req.destroy(new Error('ETIMEDOUT')); } catch (_) {} });
      }
      if (body !== undefined && body !== null) {
        const payload = typeof body === 'string' ? body : JSON.stringify(body);
        if (!opts.headers['Content-Type']) req.setHeader('Content-Type', 'application/json');
        req.setHeader('Content-Length', Buffer.byteLength(payload));
        req.write(payload);
      }
      req.end();
    } catch (e) {
      reject(e);
    }
  });
}

async function requestJson(urlStr, opts = {}) {
  const r = await requestRaw(urlStr, opts);
  if (r.status < 200 || r.status >= 300) throw new Error(`HTTP ${r.status}`);
  try { return { status: r.status, data: JSON.parse(r.body || 'null') }; } catch (_) { return { status: r.status, data: null }; }
}

async function httpGet(urlStr, { headers = {}, timeout = 8000, insecure = false } = {}) {
  if (axios) {
    const httpsAgent = insecure ? new https.Agent({ rejectUnauthorized: false }) : undefined;
    const r = await axios.get(urlStr, { headers, timeout, httpsAgent });
    return { status: r.status, data: r.data };
  }
  return await requestJson(urlStr, { method: 'GET', headers, timeout, insecure });
}

async function httpPost(urlStr, body, { headers = {}, timeout = 8000, insecure = false } = {}) {
  if (axios) {
    const httpsAgent = insecure ? new https.Agent({ rejectUnauthorized: false }) : undefined;
    const r = await axios.post(urlStr, body || {}, { headers, timeout, httpsAgent, validateStatus: () => true });
    if (r.status < 200 || r.status >= 300) throw new Error(`HTTP ${r.status}`);
    return { status: r.status, data: r.data };
  }
  return await requestJson(urlStr, { method: 'POST', headers, body: body || {}, timeout, insecure });
}

// Paths
const ROOT_DIR = path.join(__dirname);
const SRC_DIR = path.join(ROOT_DIR, 'src');
const ASSETS_DIR = path.join(ROOT_DIR, 'assets');
const MONITOR_CONFIG = path.join(__dirname, 'monitor_data', 'config.json');
const ALERTS_LOG = path.join(__dirname, 'monitor_data', 'alerts.log');
const OFFLINE_Q = path.join(__dirname, 'monitor_data', 'offline_queue.json');

// First-run helpers (top-level)
function userDataPath(...p) { return path.join(app.getPath('userData'), ...p); }
function firstRunFlagPath() { return userDataPath('first-run.json'); }
function ensureFirstRunCleanup() {
  try {
    if (!fs.existsSync(firstRunFlagPath())) {
      // Clear any packaged or stale session on first run for this user profile
      try { fs.unlinkSync(userDataPath('session.json')); } catch (_) {}
      fs.writeFileSync(firstRunFlagPath(), JSON.stringify({ ts: Date.now(), v: 1 }, null, 2), 'utf-8');
    }
  } catch (e) {
    console.warn('First-run cleanup failed:', e.message);
  }
}

function createTray() {
  try {
    if (tray) return tray;
    const iconPath = path.join(ASSETS_DIR, 'icon.png');
    tray = new Tray(iconPath);
    tray.setToolTip('WFH Agent');
    const showDashboard = () => {
      try {
        if (!dashWin || dashWin.isDestroyed()) {
          // No dashboard window, check if user is properly authenticated
          const sess = loadSession();
          const isAuthenticated = sess && sess.token && sess.username;
          if (isAuthenticated) {
            createDashboard();
          } else {
            // Not properly authenticated, show login instead
            if (!loginWin || loginWin.isDestroyed()) createLogin();
            if (loginWin && !loginWin.isDestroyed()) {
              if (loginWin.isMinimized()) loginWin.restore();
              loginWin.show();
              loginWin.focus();
            }
            return;
          }
        }
        if (dashWin && !dashWin.isDestroyed()) {
          if (dashWin.isMinimized()) dashWin.restore();
          dashWin.show();
          dashWin.focus();
        }
      } catch (_) {}
    };
    const buildMenu = () => {
      const items = [
        { label: 'Show Dashboard', click: showDashboard },
        { type: 'separator' },
        { label: 'Check for Updates…', enabled: app.isPackaged && !updateState.checking, click: () => checkForUpdates() },
        { label: updateState.available && !updateState.downloaded ? 'Download Update' : 'Download Update', enabled: app.isPackaged && updateState.available && !updateState.downloaded, click: () => downloadUpdate() },
        { label: 'Install and Restart', enabled: app.isPackaged && updateState.downloaded, click: () => installAndRestart() },
        { label: updateState.autoInstall ? '✓ Auto-Install Updates' : 'Auto-Install Updates', enabled: app.isPackaged, click: () => toggleAutoInstall() },
        { type: 'separator' },
        { label: 'Reset App Data', click: () => { try { fs.unlinkSync(userDataPath('session.json')); notify('App data reset', 'Session cleared.'); } catch (e) { notify('Reset failed', e.message || 'Unable to clear session'); } } },
        { type: 'separator' },
        { label: 'Quit', click: () => { isQuitting = true; app.quit(); } }
      ];
      const m = Menu.buildFromTemplate(items);
      tray.setContextMenu(m);
    };
    buildMenu();
    tray.on('click', showDashboard);
    tray.on('right-click', () => tray.popUpContextMenu());
    tray._rebuildMenu = buildMenu; // store for updater events
    return tray;
  } catch (e) {
    console.warn('Failed to create system tray:', e.message);
    return null;
  }
}

// Simple session storage in userData
function sessionPath() {
  return path.join(app.getPath('userData'), 'session.json');
}

function broadcast(channel, payload) {
  try {
    const wins = BrowserWindow.getAllWindows() || [];
    wins.forEach(w => {
      try { w.webContents.send(channel, payload); } catch (_) { }
    });
  } catch (_) { }
}

// Offline queue utils
function loadQueue() {
  try { if (fs.existsSync(OFFLINE_Q)) return JSON.parse(fs.readFileSync(OFFLINE_Q, 'utf-8')) || []; } catch (_) { }
  return [];
}
function saveQueue(q) {
  try { fs.writeFileSync(OFFLINE_Q, JSON.stringify(q, null, 2), 'utf-8'); } catch (_) { }
}
function enqueue(action) {
  const q = loadQueue();
  q.push({ ts: Date.now(), ...action });
  saveQueue(q);
}
async function canReachBackend() {
  try {
    const cfg = loadConfig();
    const base = cfg.serverUrl || 'http://127.0.0.1:5050';
    const url = new URL('/status', base).toString();
    await httpGet(url, { timeout: 3000 });
    return true;
  } catch (_) { return false; }
}
async function drainQueue() {
  const q = loadQueue();
  if (!q.length) return;
  if (!(await canReachBackend())) return;
  const cfg = loadConfig();
  const base = cfg.serverUrl || 'http://127.0.0.1:5050';
  const next = [];
  let startedSynced = false;
  for (const item of q) {
    try {
      const url = new URL(item.path, base).toString();
      await httpPost(url, item.body || {}, { timeout: 5000 });
      if (item.path === '/session/start') startedSynced = true;
    } catch (e) {
      console.warn('drainQueue failed', item.path, e.message);
      next.push(item); // keep for next round
    }
  }
  saveQueue(next);
  if (startedSynced) {
    // Inform renderer that server session is now synced
    broadcast('work:autoStart', { ok: true, synced: true });
  }
}

// Helper to POST to backend from main process (with offline queue)
async function backendPost(pathname, body) {
  try {
    const cfg = loadConfig();
    const base = cfg.serverUrl || 'http://127.0.0.1:5050';
    const url = new URL(pathname, base).toString();
    await httpPost(url, body || {}, { timeout: 5000 });
    return true;
  } catch (e) {
    console.warn('backendPost failed', pathname, e.message);
    // Enqueue for retry
    enqueue({ path: pathname, body: body || {} });
    return false;
  }
}
function loadSession() {
  try {
    const p = sessionPath();
    if (fs.existsSync(p)) {
      return JSON.parse(fs.readFileSync(p, 'utf-8'));
    }
  } catch (_) { }
  return { token: null, username: null, hrmsBase: null, hrmsEmpId: null, work: { current: null, sessions: [] } };
}
function saveSession(data) {
  try {
    const existing = loadSession();
    const merged = { ...existing, ...(data || {}) };
    fs.writeFileSync(sessionPath(), JSON.stringify(merged, null, 2), 'utf-8');
  } catch (e) {
    console.error('Failed to save session:', e);
  }
}
function clearSession() {
  saveSession({ token: null, username: null });

}

// Mirror backend Notify: lines to OS notifications via Electron
let lastNotifyTs = '';
function startAlertsWatcher() {
  try {
    if (!fs.existsSync(ALERTS_LOG)) {
      try { fs.writeFileSync(ALERTS_LOG, '', 'utf-8'); } catch (_) { }
    }
    fs.watch(ALERTS_LOG, { persistent: false }, (_evt, _fname) => {
      try {
        const data = fs.readFileSync(ALERTS_LOG, 'utf-8');
        const lines = data.trim().split(/\r?\n/);
        for (let i = Math.max(0, lines.length - 10); i < lines.length; i++) {
          const line = lines[i] || '';
          // Format: [ISO] Notify: Title - Message
          const m = line.match(/^\[(.+?)\]\s+Notify:\s*(.+?)\s*-\s*(.+)$/);
          if (m) {
            const ts = m[1];
            const title = m[2];
            const body = m[3];
            if (ts !== lastNotifyTs) {
              lastNotifyTs = ts;
              try {
                new Notification({ title, body }).show();
              } catch (e) {
                console.warn('Electron Notification failed:', e.message);
              }
            }
          }
        }
      } catch (e) {
        console.warn('alerts.log watch read error:', e.message);
      }
    });
  } catch (e) {
    console.warn('Failed to watch alerts.log:', e.message);
  }
}

// Backend POST routed through offline-aware backendPost()
ipcMain.handle('api:post', async (_evt, { path: apiPath, baseUrl, body }) => {
  try {
    const ok = await backendPost(apiPath, body || {});
    return ok ? { ok: true } : { ok: false, queued: true };
  } catch (e) {
    return { ok: false, error: e.message, queued: true };
  }
});

// ---------------- Work Session Engine (local prototype) ----------------
function nowIso() { return new Date().toISOString(); }
function loadWork() {
  const sess = loadSession();
  if (!sess.work) sess.work = { current: null, sessions: [] };
  return sess.work;
}
function saveWork(work) {
  const sess = loadSession();
  sess.work = work;
  saveSession(sess);
}

ipcMain.handle('work:state', async () => {
  const work = loadWork();
  return { ok: true, data: work };
});

ipcMain.handle('work:start', async () => {
  const work = loadWork();
  if (work.current && !work.current.end_ts) {
    return { ok: false, error: 'Session already active' };
  }
  work.current = { start_ts: nowIso(), end_ts: null, breaks: [], status: 'active' };
  saveWork(work);
  return { ok: true };
});

ipcMain.handle('work:breakToggle', async () => {
  const work = loadWork();
  if (!work.current || work.current.end_ts) return { ok: false, error: 'No active session' };
  const cur = work.current;
  // If currently on break, end break; otherwise start break
  const last = cur.breaks.length ? cur.breaks[cur.breaks.length - 1] : null;
  if (last && !last.end_ts) {
    last.end_ts = nowIso();
    cur.status = 'active';
  } else {
    cur.breaks.push({ start_ts: nowIso(), end_ts: null });
    cur.status = 'break';
  }
  saveWork(work);
  return { ok: true, data: cur.status };
});

ipcMain.handle('work:end', async () => {
  const work = loadWork();
  if (!work.current || work.current.end_ts) return { ok: false, error: 'No active session' };
  const cur = work.current;
  // Close any open break first
  const last = cur.breaks.length ? cur.breaks[cur.breaks.length - 1] : null;
  if (last && !last.end_ts) last.end_ts = nowIso();
  cur.end_ts = nowIso();
  // finalize and push to sessions
  work.sessions.push(cur);
  work.current = null;
  saveWork(work);
  return { ok: true };
});

ipcMain.handle('work:summary', async (_evt, { days = 7 }) => {
  const work = loadWork();
  const since = Date.now() - days * 24 * 3600 * 1000;
  function durMs(a, b) { return Math.max(0, new Date(b) - new Date(a)); }
  function sumBreakMs(brks) {
    return (brks || []).reduce((acc, b) => {
      if (b.start_ts && b.end_ts) return acc + durMs(b.start_ts, b.end_ts);
      return acc;
    }, 0);
  }
  const rows = (work.sessions || []).filter(s => new Date(s.start_ts).getTime() >= since).map(s => {
    const totalMs = durMs(s.start_ts, s.end_ts || nowIso());
    const breakMs = sumBreakMs(s.breaks);
    const workMs = Math.max(0, totalMs - breakMs);
    return { start_ts: s.start_ts, end_ts: s.end_ts, work_ms: workMs, break_ms: breakMs, total_ms: totalMs, status: 'completed' };
  });
  // KPIs
  const totals = rows.reduce((acc, r) => {
    acc.work += r.work_ms; acc.break += r.break_ms; acc.total += r.total_ms; return acc;
  }, { work: 0, break: 0, total: 0 });
  const activeCount = rows.length;
  const avgSessionMs = activeCount ? Math.round(totals.work / activeCount) : 0;
  return { ok: true, data: { rows, kpi: { total_work_ms: totals.work, total_break_ms: totals.break, avg_work_ms: avgSessionMs, sessions_completed: activeCount } } };
});

// Config
function loadConfig() {
  let cfg = {
    serverUrl: 'http://127.0.0.1:5050',
    empId: 0,
    refreshInterval: 10000,
    features: { wellness: true, esg: true, itsm: true },
    officeIps: ['139.167.219.110', '14.96.131.106'], // Whitelisted office public IPs
    officeSsids: [], // Optional Wi-Fi SSIDs considered office
    forceOffice: false,
    forceRemote: false
  };
  try {
    if (fs.existsSync(MONITOR_CONFIG)) {
      const raw = JSON.parse(fs.readFileSync(MONITOR_CONFIG, 'utf-8'));
      if (raw) {
        if (raw.ingestion && raw.ingestion.mode) {
          // keep
        }
        cfg.empId = raw.emp_id || cfg.empId;
        cfg.serverUrl = (raw.server_url || cfg.serverUrl);
        if (Array.isArray(raw.office_ips)) cfg.officeIps = raw.office_ips;
        if (Array.isArray(raw.office_ssids)) cfg.officeSsids = raw.office_ssids;
        if (typeof raw.force_office === 'boolean') cfg.forceOffice = raw.force_office;
        if (typeof raw.force_remote === 'boolean') cfg.forceRemote = raw.force_remote;
      }
    }
  } catch (e) {
    console.warn('Failed to read monitor config:', e.message);
  }
  return cfg;
}

let splashWin = null;
let loginWin = null;
let dashWin = null;
let backendProc = null;
let tray = null;
let isQuitting = false;
let updateState = {
  checking: false,
  available: false,
  downloaded: false,
  version: null,
  progress: null,
  autoInstall: true, // Auto-install updates by default
};

// Auto-update intervals
let updateCheckInterval = null;

async function waitForBackend(url, timeoutMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      // Try multiple health endpoints
      const statusUrl = new URL('/status', url).toString();
      const stateUrl = new URL('/session/state', url).toString();
      try { await httpGet(statusUrl, { timeout: 1000 }); return true; } catch (_) { /* ignore */ }
      try { await httpGet(stateUrl, { timeout: 1000 }); return true; } catch (_) { /* ignore */ }
      // Neither endpoint responded; wait and retry
    } catch (_) {
      await new Promise(r => setTimeout(r, 500));
    }
    await new Promise(r => setTimeout(r, 500));
  }
  return false;
}

function startBackend() {
  try {
    const cfg = loadConfig();
    const projectDir = path.join(__dirname);
    const scriptPath = path.join(projectDir, 'backend', 'emp_monitor.py');

    // 1) Try bundled executable first (so Python is not required on target machines)
    try {
      const resourcesDir = process.resourcesPath || projectDir;
      const bundledExe = process.platform === 'win32'
        ? path.join(resourcesDir, 'backend', 'emp_monitor.exe')
        : path.join(resourcesDir, 'backend', 'emp_monitor');
      if (fs.existsSync(bundledExe)) {
        backendProc = spawn(bundledExe, ['--serve', '--port', '5050'], {
          cwd: path.dirname(bundledExe),
          stdio: 'pipe',
          env: process.env,
          windowsHide: true,
        });
        console.log(`[backend] started bundled: ${bundledExe} --serve --port 5050`);
      }
    } catch (e) {
      console.warn('[backend] bundled start failed:', e.message);
      backendProc = null;
    }

    // 2) If no bundled backend, fall back to system Python
    if (!backendProc) {
      const override = process.env.EMP_PYTHON_EXE && process.env.EMP_PYTHON_EXE.trim();
      const candidates = override ? [[override, [scriptPath, '--serve', '--port', '5050']]] : (
        process.platform === 'win32'
          ? [["py", ["-3", scriptPath, '--serve', '--port', '5050']], ["python", [scriptPath, '--serve', '--port', '5050']]]
          : [["python3", [scriptPath, '--serve', '--port', '5050']], ["python", [scriptPath, '--serve', '--port', '5050']]]
      );
      for (const [cmd, args] of candidates) {
        try {
          backendProc = spawn(cmd, args, { cwd: projectDir, stdio: 'pipe', env: process.env, windowsHide: true });
          console.log(`[backend] started: ${cmd} ${args.join(' ')}`);
          break;
        } catch (e) {
          console.warn(`[backend] failed to start with ${cmd}: ${e.message}`);
          backendProc = null;
        }
      }
    }

    if (!backendProc) {
      console.error('Backend not started. Either bundle the backend executable or install Python (set EMP_PYTHON_EXE).');
      return null;
    }

    backendProc.stdout.on('data', d => console.log('[py]', d.toString().trim()));
    backendProc.stderr.on('data', d => console.error('[py]', d.toString().trim()));
    backendProc.on('exit', (code) => {
      console.log('Python backend exited with', code);
      backendProc = null;
    });

    // Return the expected local URL; config can still point to remote for HRMS
    return 'http://127.0.0.1:5050';
  } catch (e) {
    console.error('Failed to start backend:', e);
    return null;
  }
}

function createSplash() {
  splashWin = new BrowserWindow({
    width: 420,
    height: 320,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    icon: path.join(ASSETS_DIR, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });
  splashWin.loadFile(path.join(SRC_DIR, 'splash', 'index.html'));
}

function createLogin() {
  loginWin = new BrowserWindow({
    width: 520,
    height: 640,
    resizable: false,
    autoHideMenuBar: true,
    frame: false,
    title: 'Login',
    icon: path.join(ASSETS_DIR, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });
  loginWin.loadFile(path.join(SRC_DIR, 'login', 'index.html'));
  loginWin.on('closed', () => (loginWin = null));
}

function createDashboard() {
  dashWin = new BrowserWindow({
    width: 1200,
    height: 720,
    resizable: false,
    autoHideMenuBar: true,
    frame: false,
    title: 'Dashboard',
    icon: path.join(ASSETS_DIR, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });
  dashWin.loadFile(path.join(SRC_DIR, 'dashboard', 'index.html'));
  dashWin.on('closed', () => (dashWin = null));
  // Intercept close to minimize to tray
  dashWin.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      if (dashWin && !dashWin.isDestroyed()) {
        dashWin.hide();
      }
    }
  });
}

function showLoginOrDashboard() {
  const sess = loadSession();
  // Check if user has valid authentication (token AND username)
  const isAuthenticated = sess && sess.token && sess.username;

  if (isAuthenticated) {
    if (!dashWin || dashWin.isDestroyed()) {
      createDashboard();
    } else {
      if (dashWin.isMinimized()) dashWin.restore();
      dashWin.show();
      dashWin.focus();
    }
  } else {
    // Clear invalid session data
    if (sess && (sess.token || sess.username)) {
      console.log('Clearing invalid session data');
      clearSession();
    }
    if (!loginWin || loginWin.isDestroyed()) {
      createLogin();
    } else {
      if (loginWin.isMinimized()) loginWin.restore();
      loginWin.show();
      loginWin.focus();
    }
  }
  if (splashWin && !splashWin.isDestroyed()) {
    splashWin.close();
    splashWin = null;
  }
}

// Helper function to bring the app to foreground
function bringToForeground() {
  if (dashWin && !dashWin.isDestroyed()) {
    if (dashWin.isMinimized()) dashWin.restore();
    dashWin.show();
    dashWin.focus();
  } else if (loginWin && !loginWin.isDestroyed()) {
    if (loginWin.isMinimized()) loginWin.restore();
    loginWin.show();
    loginWin.focus();
  } else {
    showLoginOrDashboard();
  }
}

// ---------------- Startup helpers ----------------
// Cache network info to limit API calls
let netCache = { ts: 0, ip: '', ssid: '' };
async function getPublicIp() {
  const now = Date.now();
  if (now - netCache.ts < 5 * 60 * 1000 && netCache.ip) return netCache.ip; // 5 min cache
  const ts = Date.now();
  const endpoints = [
    `https://api64.ipify.org?format=json&_=${ts}`,
    `https://api.ipify.org?format=json&_=${ts}`,
    `https://checkip.amazonaws.com/?_=${ts}`,
    `https://ipv4.icanhazip.com/?_=${ts}`,
    `https://ifconfig.me/all.json?_=${ts}`
  ];
  for (const url of endpoints) {
    try {
      const r = await requestRaw(url, { timeout: 4000 });
      let ip = '';
      if (/json/i.test(r.headers['content-type'] || '') || url.includes('format=json') || url.endsWith('.json')) {
        try {
          const jd = JSON.parse(r.body || 'null');
          if (jd && jd.ip) ip = String(jd.ip).trim();
          else if (jd && (jd.ip_addr || jd.ip_address)) ip = String(jd.ip_addr || jd.ip_address).trim();
        } catch (_) { /* treat as text below */ }
      }
      if (!ip && typeof r.body === 'string') ip = r.body.trim();
      if (ip) { netCache.ip = ip; netCache.ts = now; return ip; }
    } catch (_) { /* try next */ }
  }
  return '';
}

async function getCurrentSsid() {
  if (process.platform !== 'win32') return '';
  try {
    const { execSync } = require('child_process');
    const out = execSync('netsh wlan show interfaces', { encoding: 'utf-8' });
    const m = out.match(/\bSSID\s*:\s*(.+)/i);
    if (m) {
      const ssid = m[1].trim();
      // netsh may include BSSID or SSID lines; ensure not "SSID" header
      if (ssid && !/^:$/.test(ssid) && !/BSSID/i.test(ssid)) return ssid;
    }
  } catch (_) { }
  return '';
}

function ensureWorkStarted() {
  try {
    const work = loadWork();
    if (!work.current || work.current.end_ts) {
      work.current = { start_ts: nowIso(), end_ts: null, breaks: [], status: 'active' };
      saveWork(work);
      console.log('[auto] Work session started at app startup');
    }
  } catch (e) {
    console.warn('Failed to auto-start work session:', e.message);
  }
}

function isWorkWindowNow(cfg) {
  try {
    const d = new Date();
    const day = d.getDay(); // 0..6, Mon=1
    const workdays = (cfg && cfg.workdays) || [1, 2, 3, 4, 5];
    const isWorkday = workdays.includes(day === 0 ? 7 : day); // convert Sun=7
    const wh = (cfg && cfg.work_hours) || { start: '09:30', end: '18:30' };
    const [sh, sm] = (wh.start || '09:30').split(':').map(n => parseInt(n, 10));
    const [eh, em] = (wh.end || '18:30').split(':').map(n => parseInt(n, 10));
    const start = new Date(d); start.setHours(sh || 9, sm || 30, 0, 0);
    const end = new Date(d); end.setHours(eh || 18, em || 30, 0, 0);
    return isWorkday && d >= start && d <= end;
  } catch (_) {
    return true; // be permissive if parsing fails
  }
}

// Single instance lock - prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  // Another instance is already running, quit this one
  app.quit();
} else {
  // This is the first instance, handle second instance attempts
  app.on('second-instance', (event, commandLine, workingDirectory) => {
    // Someone tried to run a second instance, focus our window instead
    console.log('Second instance detected, bringing app to foreground');
    bringToForeground();
  });
}

app.whenReady().then(async () => {
  nativeTheme.themeSource = 'light';
  // Ensure notifications work in dev on Windows
  try { app.setAppUserModelId('com.wfh.agent'); } catch (_) { }
  // Create tray early
  createTray();
  // Clear any baked session on first run (per user profile)
  ensureFirstRunCleanup();
  // Setup auto-updater if packaged
  setupAutoUpdater();
  try {
    // Auto-start at OS login
    app.setLoginItemSettings({ openAtLogin: true, openAsHidden: false });
  } catch (e) {
    console.warn('Failed to set login item settings:', e.message);
  }
  const url = startBackend() || (loadConfig().serverUrl);
  const ok = await waitForBackend(url, 30000);
  if (!ok) {
    console.warn('Backend did not respond in time, UI will still load.');
  }
  // Start watching for backend-generated notifications
  startAlertsWatcher();
  // Start periodic drain of offline queue
  setInterval(drainQueue, 30000);
  // Power/session state integration: auto break/resume (only for real system events)
  try {
    // Only monitor actual system suspend/resume - not session switching
    powerMonitor.on('suspend', () => {
      console.log('[power] System suspend detected -> break start');
      backendPost('/session/break/start', {});
      broadcast('power:break', { action: 'start', source: 'suspend' });
    });

    powerMonitor.on('resume', () => {
      console.log('[power] System resume detected -> break end');
      backendPost('/session/break/end', {});
      broadcast('power:break', { action: 'end', source: 'resume' });
    });

    // Only monitor actual screen lock/unlock - not window focus changes
    powerMonitor.on('lock-screen', () => {
      console.log('[power] Screen lock detected -> break start');
      backendPost('/session/break/start', {});
      broadcast('power:break', { action: 'start', source: 'lock-screen' });
    });

    powerMonitor.on('unlock-screen', () => {
      console.log('[power] Screen unlock detected -> break end');
      backendPost('/session/break/end', {});
      broadcast('power:break', { action: 'end', source: 'unlock-screen' });
    });

    // REMOVED: shutdown and session-end events as they trigger false positives
    // These events fire during normal window switching and application focus changes

  } catch (e) {
    console.warn('powerMonitor hook failed:', e.message);
  }
  // Determine if on office network and auto-start work (SSID takes precedence over IP)
  try {
    const cfg = loadConfig();
    const [ip, ssid] = await Promise.all([getPublicIp(), getCurrentSsid()]);
    let isOffice = false;
    if (cfg.forceRemote) {
      isOffice = false;
    } else if (cfg.forceOffice) {
      isOffice = true;
    } else if (ssid) {
      isOffice = (cfg.officeSsids || []).includes(ssid);
    } else if (ip) {
      isOffice = (cfg.officeIps || []).includes(ip);
    }
    if (isOffice) {
      console.log(`[net] Office network detected (ssid='${ssid || '-'}', ip='${ip || '-'}'); NOT auto-starting work timer`);
    } else {
      const within = isWorkWindowNow(cfg);
      console.log(`[net] Remote network (ssid='${ssid || '-'}', ip='${ip || '-'}'); withinWindow=${within}`);
      if (within) {
        // Start backend session and local tracker; broadcast to UI
        backendPost('/session/start', {}).then(ok => {
          console.log('[auto] Backend work start', ok);
          broadcast('work:autoStart', { ok: !!ok, ssid, ip });
        });
        ensureWorkStarted();
      } else {
        console.log('[auto] Outside work window; not auto-starting');
      }
    }
  } catch (e) {
    console.warn('Startup IP check failed:', e.message);
    // As a fallback, still start local tracker during typical hours
    const cfg = loadConfig();
    if (isWorkWindowNow(cfg)) ensureWorkStarted();
  }
  // Attempt initial drain after backend is up
  setTimeout(drainQueue, 5000);
  createSplash();
  setTimeout(showLoginOrDashboard, 4000); // 4 seconds
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  isQuitting = true;

  // Stop update checking
  stopPeriodicUpdateChecks();

  try {
    if (backendProc && !backendProc.killed) {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(backendProc.pid), '/f', '/t']);
      } else {
        backendProc.kill('SIGTERM');
      }
    }
  } catch (e) {
    console.warn('Failed to terminate backend:', e.message);
  }
});

// IPC bridge
ipcMain.handle('config:get', async () => loadConfig());
ipcMain.handle('session:get', async () => loadSession());
ipcMain.handle('session:clear', async () => clearSession());
ipcMain.handle('session:update', async (_evt, patch) => {
  try {
    const current = loadSession();
    const merged = { ...current, ...(patch || {}) };
    saveSession(merged);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// External HRMS login
ipcMain.handle('auth:login', async (_evt, { serverAuthUrl, username, password, empId }) => {
  try {
    const url = serverAuthUrl; // e.g., https://fhq.fidelisam.in/api/auth/login
    console.log('[AUTH] Login attempt:', { url, username, empId });

    let res;
    try {
      // Laravel example expects { email, password }
      const payload = { email: username, password };
      console.log('[AUTH] Request payload:', payload);
      res = await httpPost(url, payload, { timeout: 8000 });
      console.log('[AUTH] Response status:', res.status);
      console.log('[AUTH] Response data:', res.data);
    } catch (e) {
      console.error('[AUTH] Request failed:', e.message);
      // Retry with relaxed TLS if certificate cannot be verified
      const msg = (e && (e.code || e.message || '')) + '';
      if (/UNABLE_TO_VERIFY_LEAF_SIGNATURE|SELF_SIGNED_CERT_IN_CHAIN|ERR_SSL|unable to verify the first certificate/i.test(msg)) {
        console.log('[AUTH] Retrying with relaxed TLS...');
        res = await httpPost(url, { email: username, password }, { timeout: 8000, insecure: true });
        console.log('[AUTH] Insecure retry status:', res.status);
        console.log('[AUTH] Insecure retry data:', res.data);
      } else {
        throw e;
      }
    }

    console.log('[AUTH] Checking response for token...');
    if (res && res.data && (res.data.token || res.data.access_token)) {
      const token = res.data.token || res.data.access_token;
      console.log('[AUTH] Token found, saving session...');

      // Derive HRMS API base: if URL contains '/api/', trim after it, else use origin + '/api'
      let hrmsBase = '';
      try {
        const u = new URL(url);
        const path = u.pathname || '/';
        const idx = path.indexOf('/api/');
        if (idx >= 0) {
          hrmsBase = `${u.origin}${path.substring(0, idx + 4)}`; // include '/api'
        } else {
          hrmsBase = `${u.origin}/api`;
        }
      } catch (_) {
        hrmsBase = '';
      }
      // Persist hrmsEmpId for profile fetches
      saveSession({ token, username, hrmsBase, hrmsEmpId: empId });
      console.log('[AUTH] Login successful');
      return { ok: true };
    }

    console.error('[AUTH] No token in response:', res.data);
    return { ok: false, error: 'Invalid response from auth API - no token received' };
  } catch (e) {
    console.error('[AUTH] Login error:', e.message);
    return { ok: false, error: e.message };
  }
});

ipcMain.handle('auth:logout', async () => {
  clearSession();
  return { ok: true };
});

// Backend (Python) API proxy with stored token (if any)
ipcMain.handle('api:get', async (_evt, { path: apiPath, baseUrl }) => {
  try {
    const cfg = loadConfig();
    const sess = loadSession();
    const base = baseUrl || cfg.serverUrl;
    const url = new URL(apiPath, base).toString();
    const headers = {};
    if (sess && sess.token) headers['Authorization'] = `Bearer ${sess.token}`;
    let r;
    try { r = await httpGet(url, { headers, timeout: 8000 }); }
    catch (e) {
      const msg = (e && (e.code || e.message || '')) + '';
      if (/UNABLE_TO_VERIFY_LEAF_SIGNATURE|SELF_SIGNED_CERT_IN_CHAIN|ERR_SSL|unable to verify the first certificate/i.test(msg)) {
        r = await httpGet(url, { headers, timeout: 8000, insecure: true });
      } else { throw e; }
    }
    return { ok: true, data: r.data };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// HRMS GET using stored token and hrmsBase
ipcMain.handle('hrms:get', async (_evt, { path: apiPath }) => {
  try {
    const sess = loadSession();
    if (!sess || !sess.token || !sess.hrmsBase) {
      return { ok: false, error: 'Not authenticated to HRMS' };
    }
    const url = new URL(apiPath, sess.hrmsBase.endsWith('/') ? sess.hrmsBase : sess.hrmsBase + '/').toString();
    const headers = { Authorization: `Bearer ${sess.token}` };
    let r;
    try { r = await httpGet(url, { headers, timeout: 10000 }); }
    catch (e) {
      const msg = (e && (e.code || e.message || '')) + '';
      if (/UNABLE_TO_VERIFY_LEAF_SIGNATURE|SELF_SIGNED_CERT_IN_CHAIN|ERR_SSL|unable to verify the first certificate/i.test(msg)) {
        r = await httpGet(url, { headers, timeout: 10000, insecure: true });
      } else { throw e; }
    }
    return { ok: true, data: r.data };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// Navigation: open dashboard and close login
ipcMain.handle('nav:to', async (_evt, { name }) => {
  if (name === 'dashboard') {
    if (!dashWin || dashWin.isDestroyed()) createDashboard();
    if (loginWin && !loginWin.isDestroyed()) {
      loginWin.close();
      loginWin = null;
    }
    return { ok: true };
  }
  if (name === 'login') {
    if (!loginWin || loginWin.isDestroyed()) createLogin();
    if (dashWin && !dashWin.isDestroyed()) {
      dashWin.close();
      dashWin = null;
    }
    return { ok: true };
  }
  return { ok: false, error: 'unknown target' };
});

// Window controls for frameless window
ipcMain.handle('window:minimize', async () => {
  const w = BrowserWindow.getFocusedWindow() || dashWin || loginWin;
  if (w && !w.isDestroyed()) {
    w.minimize();
    return { ok: true };
  }
  return { ok: false, error: 'no window' };
});
ipcMain.handle('window:maximizeToggle', async () => {
  const w = BrowserWindow.getFocusedWindow() || dashWin || loginWin;
  if (!w || w.isDestroyed()) return { ok: false, error: 'no window' };
  if (w.isMaximized()) { w.unmaximize(); } else { w.maximize(); }
  return { ok: true, maximized: w.isMaximized() };
});
ipcMain.handle('window:close', async () => {
  const w = BrowserWindow.getFocusedWindow() || dashWin || loginWin;
  if (w) {
    if (w === dashWin && dashWin) {
      dashWin.hide();
      return { ok: true, hidden: true };
    }
    w.close();
    return { ok: true };
  }
  return { ok: false, error: 'no window' };
});

// ===== Auto Updater (core) =====
function notify(title, body) {
  try {
    new Notification({ title, body }).show();
  } catch (_) {}
}

function setupAutoUpdater() {
  if (!app.isPackaged) return; // only in packaged builds
  try {
    const pkg = require(path.join(__dirname, 'package.json'));
    const repo = 'chetan-fidelis/wfh-agent';
    // Using update.electronjs.org for GitHub provider
    // See: https://www.electronjs.org/docs/latest/tutorial/updates
    const feedURL = `https://update.electronjs.org/${repo}/${process.platform}-${process.arch}/${pkg.version}`;
    // setFeedURL is required on win32/darwin for core autoUpdater
    autoUpdater.setFeedURL({ url: feedURL });

    autoUpdater.on('checking-for-update', () => {
      updateState.checking = true; updateState.available = false; updateState.downloaded = false; updateState.progress = null;
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    autoUpdater.on('update-available', (info) => {
      updateState.checking = false; updateState.available = true; updateState.version = info && info.version;
      console.log(`[auto-updater] Update available: ${updateState.version}`);
      notify('Update available', `Version ${updateState.version || ''} is downloading in background...`);
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
      // Automatically start download
      try {
        autoUpdater.downloadUpdate();
      } catch (e) {
        console.warn('Auto-download failed:', e.message);
      }
    });
    autoUpdater.on('update-not-available', () => {
      updateState.checking = false; updateState.available = false; updateState.downloaded = false;
      console.log('[auto-updater] No updates available');
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    autoUpdater.on('error', (err) => {
      updateState.checking = false;
      console.warn('autoUpdater error:', err && err.message || err);
      notify('Update error', (err && err.message) || 'Unknown error');
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    autoUpdater.on('download-progress', (p) => {
      updateState.progress = p;
      console.log(`[auto-updater] Download progress: ${Math.round(p.percent)}%`);
    });
    autoUpdater.on('update-downloaded', (info) => {
      updateState.downloaded = true; updateState.available = true; updateState.checking = false;
      console.log(`[auto-updater] Update downloaded: ${updateState.version}`);

      if (updateState.autoInstall) {
        // Auto-install after a short delay
        notify('Update installing', 'Automatically installing update and restarting...');
        setTimeout(() => {
          try {
            autoUpdater.quitAndInstall();
          } catch (e) {
            console.warn('Auto-install failed:', e.message);
            notify('Update ready', 'Please restart manually to apply the update.');
          }
        }, 3000); // 3 second delay
      } else {
        notify('Update ready', 'Restart to apply the update.');
      }
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    // Start periodic update checks (every 4 hours)
    startPeriodicUpdateChecks();
  } catch (e) {
    console.warn('Failed to setup autoUpdater:', e.message);
  }
}

function startPeriodicUpdateChecks() {
  if (!app.isPackaged) return;

  // Check for updates every 4 hours (14400000 ms)
  updateCheckInterval = setInterval(() => {
    console.log('[auto-updater] Periodic update check...');
    checkForUpdates(true); // Silent check
  }, 4 * 60 * 60 * 1000);

  // Initial check after 30 seconds (startup delay)
  setTimeout(() => {
    console.log('[auto-updater] Initial startup update check...');
    checkForUpdates(true); // Silent check
  }, 30000);
}

function stopPeriodicUpdateChecks() {
  if (updateCheckInterval) {
    clearInterval(updateCheckInterval);
    updateCheckInterval = null;
  }
}

function checkForUpdates(silent = false) {
  if (!app.isPackaged) {
    if (!silent) notify('Updater disabled', 'Updates only work in packaged builds.');
    return;
  }
  try {
    if (!silent) console.log('[auto-updater] Checking for updates...');
    autoUpdater.checkForUpdates();
  } catch (e) {
    console.warn('checkForUpdates failed:', e.message);
  }
}
function downloadUpdate() {
  if (!app.isPackaged) return;
  try { autoUpdater.downloadUpdate(); } catch (e) { console.warn('downloadUpdate failed:', e.message); }
}
function installAndRestart() {
  if (!app.isPackaged) return;
  try { autoUpdater.quitAndInstall(); } catch (e) { console.warn('quitAndInstall failed:', e.message); }
}

function toggleAutoInstall() {
  updateState.autoInstall = !updateState.autoInstall;
  console.log(`[auto-updater] Auto-install ${updateState.autoInstall ? 'enabled' : 'disabled'}`);
  notify('Auto-Install', `Automatic update installation ${updateState.autoInstall ? 'enabled' : 'disabled'}.`);
  if (tray && tray._rebuildMenu) tray._rebuildMenu();
}

// Network status for UI (Office vs Remote)
ipcMain.handle('net:status', async () => {
  try {
    const cfg = loadConfig();
    const [ip, ssid] = await Promise.all([getPublicIp(), getCurrentSsid()]);
    // SSID takes precedence: if SSID is known and not in office list, treat as Remote
    let isOffice = false;
    if (cfg.forceRemote) {
      isOffice = false;
    } else if (cfg.forceOffice) {
      isOffice = true;
    } else if (ssid) {
      isOffice = (cfg.officeSsids || []).includes(ssid);
    } else if (ip) {
      isOffice = (cfg.officeIps || []).includes(ip);
    }
    return { ok: true, data: { ip, ssid, isOffice } };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});
