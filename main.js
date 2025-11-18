const { app, BrowserWindow, ipcMain, Notification, Menu, Tray, dialog, shell, nativeTheme, netLog, powerMonitor } = require('electron');
let autoUpdater;
try {
  autoUpdater = require('electron-updater').autoUpdater;
} catch (e) {
  console.warn('Auto-updater not available:', e.message);
  autoUpdater = null;
}

function setDownloadMonitorToken(token) {
  try {
    // Load existing config or initialize
    let cfg = {};
    try { if (fs.existsSync(MONITOR_CONFIG)) cfg = JSON.parse(fs.readFileSync(MONITOR_CONFIG, 'utf-8')) || {}; } catch (_) {}
    if (!cfg.download_monitor) cfg.download_monitor = {};
    cfg.download_monitor.auth_token = token;
    // Persist
    fs.writeFileSync(MONITOR_CONFIG, JSON.stringify(cfg, null, 2), 'utf-8');
    // Emit a Notify line so Electron toast shows
    try {
      const ts = new Date().toISOString();
      fs.appendFileSync(ALERTS_LOG, `[${ts}] Notify: Download Monitor - Authenticated - Token updated for CV uploads\n`, 'utf-8');
    } catch (_) {}
  } catch (e) {
    console.warn('[auth] Failed to persist download monitor token:', e.message);
  }
}
const { spawn, spawnSync, execSync } = require('child_process');
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
const NETLOG_DIR = path.join(__dirname, 'monitor_data', 'netlogs');
const CV_UPLOADS = path.join(__dirname, 'monitor_data', 'cv_uploads.json');

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

// Format milliseconds to human readable time
function formatDuration(ms) {
  if (!ms || ms < 0) return '0m';
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

// Real-time timer update for tray menu (kept as no-op to avoid duplicate intervals)
let menuUpdateTimer = null;

function startMenuUpdateTimer() {
  // No-op: createTray manages a single 60s interval. Avoid a second timer.
  console.log('[timer] Real-time menu updates managed by tray interval');
}

function stopMenuUpdateTimer() {
  if (menuUpdateTimer) {
    clearInterval(menuUpdateTimer);
    menuUpdateTimer = null;
    console.log('[timer] Stopped auxiliary menu updates');
  }
}

// Configure auto-updater for silent background updates (packaged builds only)
function setupAutoUpdater() {
  try {
    if (!autoUpdater || !app.isPackaged) return;
    autoUpdater.logger = {
      info: (m) => console.log('[updater]', m),
      error: (m) => console.error('[updater]', m)
    };
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true; // install on next quit as a fallback
    autoUpdater.allowPrerelease = false;

    autoUpdater.on('checking-for-update', () => console.log('[updater] checking for updates...'));
    autoUpdater.on('update-available', (info) => console.log('[updater] update available ->', info && info.version));
    autoUpdater.on('update-not-available', () => console.log('[updater] update not available'));
    autoUpdater.on('error', (err) => console.error('[updater] error', err && (err.stack || err.message || err)));
    autoUpdater.on('download-progress', (p) => {
      try { console.log(`[updater] download ${Math.round(p.percent || 0)}%`); } catch (_) {}
    });
    autoUpdater.on('update-downloaded', (info) => {
      console.log('[updater] update downloaded ->', info && info.version);
      // Silent install and restart app; avoids showing NSIS UI
      try {
        autoUpdater.quitAndInstall(true, true);
      } catch (e) {
        console.warn('[updater] quitAndInstall failed, will install on quit:', e.message);
      }
    });

    // Initial check and periodic re-check
    autoUpdater.checkForUpdatesAndNotify().catch(() => {});
    setInterval(() => {
      autoUpdater.checkForUpdates().catch(() => {});
    }, 4 * 60 * 60 * 1000);
  } catch (e) {
    console.warn('setupAutoUpdater error:', e.message);
  }
}

// Get current work session status from backend (cached for 45s)
let _wsCache = { ts: 0, value: null };
let _wsInFlight = null;
async function getWorkStatus() {
  try {
    const nowTs = Date.now();
    // Return cached value if within TTL
    if (_wsCache.value && nowTs - _wsCache.ts < 45000) {
      return _wsCache.value;
    }
    // Deduplicate concurrent requests
    if (_wsInFlight) return await _wsInFlight;
    _wsInFlight = (async () => {
      // Fetch live session state from backend
      const cfg = loadConfig();
      const baseUrl = cfg.serverUrl || 'http://127.0.0.1:5050';
      try {
        const { data } = await httpGet(`${baseUrl}/session/state`, { timeout: 3000 });
        if (data && data.ok && data.state && data.state.start_ts && !data.state.end_ts) {
          // Active session from backend
          const startTime = new Date(data.state.start_ts).getTime();
          const now = Date.now();
          const totalMs = now - startTime;
          const breakMs = (data.state.breaks || []).reduce((acc, b) => {
            if (b.start_ts) {
              const bStart = new Date(b.start_ts).getTime();
              const bEnd = b.end_ts ? new Date(b.end_ts).getTime() : now;
              return acc + Math.max(0, bEnd - bStart);
            }
            return acc;
          }, 0);
          const workMs = Math.max(0, totalMs - breakMs);
          const breaks = data.state.breaks || [];
          const onBreak = breaks.length > 0 && !breaks[breaks.length - 1].end_ts;
          const result = { status: onBreak ? 'break' : 'working', label: onBreak ? '☕ On Break' : '⏱️ Working', duration: workMs, totalDuration: totalMs, breakDuration: breakMs };
          _wsCache = { ts: Date.now(), value: result };
          return result;
        }
      } catch (backendErr) {
        console.warn('[tray] Backend session fetch failed:', backendErr.message);
      }
      // Fallback to local session if backend unavailable or idle
      const work = loadWork();
      if (!work.current || work.current.end_ts) {
        const idle = { status: 'idle', label: 'Not Working', duration: 0 };
        _wsCache = { ts: Date.now(), value: idle };
        return idle;
      }
      const startTime = new Date(work.current.start_ts).getTime();
      const now = Date.now();
      const totalMs = now - startTime;
      const breakMs = (work.current.breaks || []).reduce((acc, b) => {
        if (b.start_ts) {
          const bStart = new Date(b.start_ts).getTime();
          const bEnd = b.end_ts ? new Date(b.end_ts).getTime() : now;
          return acc + Math.max(0, bEnd - bStart);
        }
        return acc;
      }, 0);
      const workMs = Math.max(0, totalMs - breakMs);
      const breaks = work.current.breaks || [];
      const onBreak = breaks.length > 0 && !breaks[breaks.length - 1].end_ts;
      const result = { status: onBreak ? 'break' : 'working', label: onBreak ? '☕ On Break' : '⏱️ Working', duration: workMs, totalDuration: totalMs, breakDuration: breakMs };
      _wsCache = { ts: Date.now(), value: result };
      return result;
    })();
    try {
      const r = await _wsInFlight;
      return r;
    } finally {
      _wsInFlight = null;
    }
  } catch (e) {
    console.error('Error getting work status:', e);
    return { status: 'idle', label: 'Not Working', duration: 0 };
  }
}

function createTray() {
  try {
    if (tray) return tray;
    const iconPath = path.join(ASSETS_DIR, 'icon.png');
    tray = new Tray(iconPath);
    tray.setToolTip('Harmony');

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

    const startWork = async () => {
      try {
        const work = loadWork();
        if (work.current && !work.current.end_ts) {
          notify('Already Working', 'You already have an active work session');
          return;
        }
        work.current = { start_ts: nowIso(), end_ts: null, breaks: [], status: 'active' };
        saveWork(work);
        await backendPost('/session/start', {});

        // Enhanced notification with current time
        const startTime = new Date(work.current.start_ts);
        const timeStr = startTime.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        notify('Work Started ✓', `Your work timer has started at ${timeStr}. Have a productive day!`);

        buildMenu();
        startMenuUpdateTimer(); // Start real-time timer updates
      } catch (e) {
        console.error('Error starting work:', e);
      }
    };

    const takeBreak = async () => {
      try {
        const work = loadWork();
        if (!work.current || work.current.end_ts) {
          notify('Not Working', 'Please start work before taking a break');
          return;
        }

        const breaks = work.current.breaks || [];
        const onBreak = breaks.length > 0 && !breaks[breaks.length - 1].end_ts;

        if (onBreak) {
          // End break
          breaks[breaks.length - 1].end_ts = nowIso();
          work.current.status = 'active';
          await backendPost('/session/break/end', {});
          notify('Break Ended', 'Welcome back! Resuming work timer.');
        } else {
          // Start break
          breaks.push({ start_ts: nowIso(), end_ts: null });
          work.current.status = 'break';
          await backendPost('/session/break/start', {});
          notify('Break Started', 'Take a rest. Click again when ready to resume.');
        }

        saveWork(work);
        buildMenu();
      } catch (e) {
        console.error('Error toggling break:', e);
      }
    };

    const endWork = async () => {
      try {
        const work = loadWork();
        if (!work.current || work.current.end_ts) {
          notify('Not Working', 'No active work session to end');
          return;
        }

        // Close any open break
        const breaks = work.current.breaks || [];
        if (breaks.length > 0 && !breaks[breaks.length - 1].end_ts) {
          breaks[breaks.length - 1].end_ts = nowIso();
        }

        work.current.end_ts = nowIso();

        // Calculate duration
        const startTime = new Date(work.current.start_ts).getTime();
        const endTime = new Date(work.current.end_ts).getTime();
        const durationMs = endTime - startTime;
        const breakMs = breaks.reduce((acc, b) => {
          if (b.start_ts && b.end_ts) {
            return acc + (new Date(b.end_ts).getTime() - new Date(b.start_ts).getTime());
          }
          return acc;
        }, 0);
        const workMs = Math.max(0, durationMs - breakMs);

        // Enhanced notification with end time and work summary
        const endTimeObj = new Date(work.current.end_ts);
        const timeStr = endTimeObj.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

        work.sessions.push(work.current);
        work.current = null;
        saveWork(work);

        await backendPost('/session/end', {});

        notify('Work Ended ✓', `Great job! You worked for ${formatDuration(workMs)} today. Ended at ${timeStr}.`);

        buildMenu();
        stopMenuUpdateTimer(); // Stop real-time timer updates
      } catch (e) {
        console.error('Error ending work:', e);
      }
    };

    const buildMenu = async () => {
      const status = await getWorkStatus();
      const cfg = loadConfig();
      const items = [];

      // Status header
      items.push({
        label: `Status: ${status.label}`,
        enabled: false
      });

      if (status.status !== 'idle') {
        items.push({
          label: `⏱️ Time Worked: ${formatDuration(status.duration)}`,
          enabled: false
        });
      }

      items.push({ type: 'separator' });

      // Action buttons based on current status
      if (status.status === 'idle') {
        items.push({
          label: '▶️ Start Work',
          click: startWork
        });
      } else if (status.status === 'working') {
        items.push({
          label: '☕ Take Break',
          click: takeBreak
        });
        items.push({
          label: '⏹️ End Work',
          click: endWork
        });
      } else if (status.status === 'break') {
        items.push({
          label: '▶️ Resume Work',
          click: takeBreak
        });
        items.push({
          label: '⏹️ End Work',
          click: endWork
        });
      }

      items.push({ type: 'separator' });
      items.push({ label: '📊 Show Dashboard', click: showDashboard });
      try {
        if (isRecruitmentDesignation(cfg.designation)) {
          const hist = loadCvUploads();
          if (hist && hist.length) {
            items.push({ type: 'separator' });
            items.push({ label: 'Recent CV Uploads', enabled: false });
            const last5 = hist.slice(-5).reverse();
            for (const h of last5) {
              const name = (h && h.file_name) ? h.file_name : 'Unknown';
              const when = (h && h.ts) ? new Date(h.ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '';
              items.push({ label: `• ${name}  (${when})`, enabled: false });
            }
          }
        }
      } catch (_) {}
      items.push({ type: 'separator' });
      items.push({ label: '❌ Quit', click: () => { isQuitting = true; app.quit(); } });

      const m = Menu.buildFromTemplate(items);
      tray.setContextMenu(m);

      // Update tooltip with status
      if (status.status !== 'idle') {
        tray.setToolTip(`Harmony - ${status.label}\nTime: ${formatDuration(status.duration)}`);
      } else {
        tray.setToolTip('Harmony - Not Working');
      }
    };

    buildMenu();
    tray.on('click', showDashboard);
    tray.on('right-click', () => tray.popUpContextMenu());
    tray._rebuildMenu = buildMenu; // store for updater events

    // Auto-update tray menu every minute to show elapsed time
    setInterval(() => {
      if (tray && !tray.isDestroyed()) {
        buildMenu();
      }
    }, 60000); // Update every minute

    // Periodic work notifications (deferred to avoid startup contention)
    setTimeout(() => {
      try { startWorkNotifications(); } catch (e) { console.warn('startWorkNotifications defer error:', e.message); }
    }, 5000);

    return tray;
  } catch (e) {
    console.warn('Failed to create system tray:', e.message);
    return null;
  }
}

// Periodic work notifications for better employee engagement
let lastNotificationTime = 0;
let notificationInterval = null;

function startWorkNotifications() {
  // Check every 5 minutes for notification triggers
  if (notificationInterval) clearInterval(notificationInterval);

  notificationInterval = setInterval(() => {
    try {
      const status = getWorkStatus();
      const now = Date.now();

      // Skip if idle or notification sent recently (within 10 minutes)
      if (status.status === 'idle' || now - lastNotificationTime < 600000) {
        return;
      }

      const workMinutes = Math.floor(status.duration / 60000);

      // Break reminders every 2 hours of continuous work
      if (status.status === 'working' && workMinutes > 0 && workMinutes % 120 === 0) {
        notify('Time for a Break', `You've been working for ${Math.floor(workMinutes / 60)} hours. Consider taking a short break!`);
        lastNotificationTime = now;
        return;
      }

      // Milestone notifications
      if (status.status === 'working') {
        // 4 hours milestone
        if (workMinutes >= 240 && workMinutes < 245) {
          notify('Great Progress!', 'You\'ve completed 4 hours of work. Keep it up!');
          lastNotificationTime = now;
          return;
        }

        // 6 hours milestone
        if (workMinutes >= 360 && workMinutes < 365) {
          notify('Excellent Work!', 'You\'ve completed 6 hours of work today. Almost done!');
          lastNotificationTime = now;
          return;
        }

        // 8 hours milestone
        if (workMinutes >= 480 && workMinutes < 485) {
          notify('Full Day Complete!', 'Congratulations! You\'ve completed 8 hours of work today.');
          lastNotificationTime = now;
          return;
        }
      }

      // Long break reminder (over 30 minutes)
      if (status.status === 'break') {
        const work = loadWork();
        if (work.current && work.current.breaks) {
          const breaks = work.current.breaks;
          const currentBreak = breaks[breaks.length - 1];
          if (currentBreak && !currentBreak.end_ts) {
            const breakStart = new Date(currentBreak.start_ts).getTime();
            const breakDuration = now - breakStart;
            const breakMinutes = Math.floor(breakDuration / 60000);

            if (breakMinutes >= 30 && breakMinutes < 35) {
              notify('Long Break', 'You\'ve been on break for 30+ minutes. Ready to resume?');
              lastNotificationTime = now;
            }
          }
        }
      }
    } catch (e) {
      console.error('Error in work notifications:', e);
    }
  }, 300000); // Check every 5 minutes
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
  const MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

  for (const item of q) {
    try {
      // Skip items older than 24 hours
      const age = Date.now() - (item.ts || 0);
      if (age > MAX_AGE_MS) {
        console.log(`[queue] Discarding stale item: ${item.path} (age: ${Math.round(age/3600000)}h)`);
        continue;
      }

      const url = new URL(item.path, base).toString();
      const response = await httpPost(url, item.body || {}, { timeout: 5000 });
      if (item.path === '/session/start') startedSynced = true;
      console.log(`[queue] Successfully processed: ${item.path}`);
    } catch (e) {
      const errMsg = e.message || String(e);

      // Don't retry 400/404 errors (bad requests)
      if (errMsg.includes('HTTP 400') || errMsg.includes('HTTP 404')) {
        console.warn(`[queue] Discarding invalid request: ${item.path} - ${errMsg}`);
        continue; // Don't re-queue
      }

      // Retry other errors (network issues, 500s, etc.)
      console.warn(`[queue] Retrying later: ${item.path} - ${errMsg}`);
      next.push(item);
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
                if (tray && !tray.isDestroyed()) {
                  tray.setToolTip(`Harmony - ${title}\n${body}`);
                  setTimeout(() => {
                    try {
                      tray.setToolTip('Harmony');
                    } catch (_) {}
                  }, 5000);
                }
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

// App/version info for footer
ipcMain.handle('app:version', async () => {
  try {
    return {
      ok: true,
      app: app.getVersion ? app.getVersion() : null,
      electron: (process && process.versions && process.versions.electron) || null,
      node: (process && process.versions && process.versions.node) || null,
      chrome: (process && process.versions && process.versions.chrome) || null
    };
  } catch (e) {
    return { ok: false, error: e.message };
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

// Validate and clean stale sessions
async function validateAndCleanSessions() {
  try {
    const work = loadWork();
    const now = Date.now();
    const MAX_SESSION_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

    // Check if there's a current session
    if (work.current && work.current.start_ts && !work.current.end_ts) {
      const sessionAge = now - new Date(work.current.start_ts).getTime();

      if (sessionAge > MAX_SESSION_AGE_MS) {
        console.log(`[session] Detected stale session from ${work.current.start_ts} (age: ${Math.round(sessionAge / 3600000)}h)`);

        // Auto-end the stale session with proper end time (24h after start or at work end time)
        const startDate = new Date(work.current.start_ts);
        const endDate = new Date(startDate);

        // Set end time to 18:30 on the same day, or 24h later if that's passed
        endDate.setHours(18, 30, 0, 0);
        if (endDate <= startDate) {
          endDate.setTime(startDate.getTime() + MAX_SESSION_AGE_MS);
        }

        work.current.end_ts = endDate.toISOString();

        // Close any open breaks
        if (work.current.breaks && work.current.breaks.length > 0) {
          const lastBreak = work.current.breaks[work.current.breaks.length - 1];
          if (lastBreak && !lastBreak.end_ts) {
            lastBreak.end_ts = work.current.end_ts;
          }
        }

        // Move to completed sessions
        work.sessions.push(work.current);
        work.current = null;
        saveWork(work);

        console.log('[session] Stale session auto-ended and archived');

        // Try to sync to backend
        try {
          await backendPost('/session/end', {});
        } catch (e) {
          console.warn('[session] Failed to sync stale session to backend:', e.message);
        }
      }
    }

    return { ok: true, cleaned: work.current === null };
  } catch (e) {
    console.error('[session] Validation error:', e.message);
    return { ok: false, error: e.message };
  }
}

// Sync Electron session with backend state
async function syncSessionWithBackend() {
  try {
    const cfg = loadConfig();
    const base = cfg.serverUrl || 'http://127.0.0.1:5050';
    const url = new URL('/session/state', base).toString();

    const response = await httpGet(url, { timeout: 3000 });
    const backendState = response.data;

    const work = loadWork();

    console.log('[session] Backend state:', backendState.state?.status || 'unknown');
    console.log('[session] Local state:', work.current ? 'active' : 'idle');

    // If backend has active session but local doesn't, sync from backend
    if (backendState.state?.start_ts && !backendState.state?.end_ts && !work.current) {
      console.log('[session] Syncing active session from backend to local');
      work.current = {
        start_ts: backendState.state.start_ts,
        end_ts: null,
        breaks: backendState.state.breaks || [],
        status: backendState.state.status || 'active'
      };
      saveWork(work);
    }

    // If local has active but backend doesn't, sync to backend
    if (work.current && !work.current.end_ts && backendState.state?.status === 'idle') {
      console.log('[session] Syncing active session from local to backend');
      await backendPost('/session/start', {
        start_ts: work.current.start_ts,
        breaks: work.current.breaks || [],
        status: work.current.status || 'active'
      });
    }

    return { ok: true, synced: true };
  } catch (e) {
    console.warn('[session] Sync with backend failed:', e.message);
    return { ok: false, error: e.message };
  }
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

  // Update tray menu to reflect new status
  if (tray && tray._rebuildMenu) {
    tray._rebuildMenu();
  }

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

  // Update tray menu to reflect new status
  if (tray && tray._rebuildMenu) {
    tray._rebuildMenu();
  }

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

  // Validate session duration (should not exceed 24 hours)
  const startTime = new Date(cur.start_ts).getTime();
  const endTime = new Date(cur.end_ts).getTime();
  const durationMs = endTime - startTime;
  const MAX_SESSION_DURATION = 24 * 60 * 60 * 1000; // 24 hours

  if (durationMs > MAX_SESSION_DURATION || durationMs < 0) {
    console.warn(`[session] Invalid session duration detected: ${Math.round(durationMs / 3600000)}h`);
    // Cap end time to max 24 hours or work end time
    const startDate = new Date(startTime);
    const cappedEndDate = new Date(startDate);
    cappedEndDate.setHours(18, 30, 0, 0);

    if (cappedEndDate <= startDate || new Date().getTime() - cappedEndDate.getTime() > MAX_SESSION_DURATION) {
      cappedEndDate.setTime(startTime + Math.min(durationMs, MAX_SESSION_DURATION));
    }

    cur.end_ts = cappedEndDate.toISOString();
    console.log(`[session] Session duration capped to ${Math.round((new Date(cur.end_ts).getTime() - startTime) / 3600000)}h`);
  }

  // finalize and push to sessions
  work.sessions.push(cur);
  work.current = null;
  saveWork(work);

  // Sync to backend
  try {
    await backendPost('/session/end', {});
  } catch (e) {
    console.warn('[session] Failed to sync ended session to backend:', e.message);
  }

  // Update tray menu to reflect new status
  if (tray && tray._rebuildMenu) {
    tray._rebuildMenu();
  }

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
    designation: '',
    refreshInterval: 10000,
    features: { wellness: true, esg: true, itsm: true },
    officeIps: ['139.167.219.110', '14.96.131.106', '49.205.34.70', '139.167.219.110'], // Whitelisted office public IPs
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
        if (raw.designation) cfg.designation = String(raw.designation || '').toLowerCase();
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

function isRecruitmentDesignation(desig) {
  if (!desig) return false;
  const d = String(desig).toLowerCase().replace(/\u2013/g, '-').replace(/\s+/g, ' ').trim();
  const targets = [
    'recruiter', 'hr', 'hiring_manager',
    'manager - talent acquisition',
    'associate manager - talent acquisition',
    'senior executive - talent acquisition',
    'team lead - talent acquisition',
    'executive - talent acquisition',
    'vice president - talent acquisition',
    'trainee - talent acquisition',
    'senior executive - talent acquisition - rpo',
    'talent acquisition partner',
    'talent acquisition',
    'associate vice president - talent acquisition'
  ].map(x => x.toLowerCase());
  return targets.includes(d);
}

function loadCvUploads() {
  try {
    if (fs.existsSync(CV_UPLOADS)) {
      const arr = JSON.parse(fs.readFileSync(CV_UPLOADS, 'utf-8')) || [];
      if (Array.isArray(arr)) return arr;
    }
  } catch (_) {}
  return [];
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
  try { app.setAppUserModelId('Harmony'); } catch (_) { }

  // Silent background updates (packaged only)
  try { setupAutoUpdater(); } catch (_) {}

  // Initialize netLog for network debugging
  try {
    // Create netlogs directory
    if (!fs.existsSync(NETLOG_DIR)) {
      fs.mkdirSync(NETLOG_DIR, { recursive: true });
    }

    // Start network logging
    const netLogPath = path.join(NETLOG_DIR, `netlog-${Date.now()}.json`);
    await netLog.startLogging(netLogPath, { captureMode: 'includeSensitive', maxFileSize: 10485760 }); // 10MB max
    console.log(`[netLog] Network logging started: ${netLogPath}`);

    // Clean up old netlogs (keep last 5)
    try {
      const files = fs.readdirSync(NETLOG_DIR)
        .filter(f => f.startsWith('netlog-') && f.endsWith('.json'))
        .map(f => ({ name: f, time: fs.statSync(path.join(NETLOG_DIR, f)).mtime.getTime() }))
        .sort((a, b) => b.time - a.time);

      if (files.length > 5) {
        for (let i = 5; i < files.length; i++) {
          fs.unlinkSync(path.join(NETLOG_DIR, files[i].name));
          console.log(`[netLog] Deleted old log: ${files[i].name}`);
        }
      }
    } catch (e) {
      console.warn('[netLog] Failed to clean old logs:', e.message);
    }
  } catch (e) {
    console.warn('[netLog] Failed to start network logging:', e.message);
  }

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

  // Validate and clean stale sessions
  console.log('[session] Running session validation...');
  await validateAndCleanSessions();

  // Sync session state with backend
  console.log('[session] Syncing with backend...');
  await syncSessionWithBackend();

  // Check if there's an active work session and start timer
  const initialStatus = await getWorkStatus();
  if (initialStatus.status !== 'idle') {
    console.log('[timer] Active session detected on startup, starting timer');
    startMenuUpdateTimer();
  }

  // Start watching for backend-generated notifications
  startAlertsWatcher();
  // Start periodic drain of offline queue (reduced frequency to 60s)
  setInterval(drainQueue, 60000);

  // Periodic session sync (every hour)
  setInterval(async () => {
    console.log('[session] Periodic sync check...');
    await validateAndCleanSessions();
    await syncSessionWithBackend();
  }, 60 * 60 * 1000); // 1 hour

  // Real-time active session sync (every 5 minutes)
  setInterval(async () => {
    try {
      const work = loadWork();
      if (work.current && !work.current.end_ts) {
        console.log('[session] Syncing active session state to backend...');

        // Calculate current work/break durations
        const startTime = new Date(work.current.start_ts).getTime();
        const now = Date.now();
        const totalMs = now - startTime;

        const breakMs = (work.current.breaks || []).reduce((acc, b) => {
          if (b.start_ts && b.end_ts) {
            return acc + (new Date(b.end_ts).getTime() - new Date(b.start_ts).getTime());
          }
          return acc;
        }, 0);

        const workMs = Math.max(0, totalMs - breakMs);

        // Send heartbeat update to backend
        await backendPost('/session/heartbeat', {
          start_ts: work.current.start_ts,
          status: work.current.status,
          breaks: work.current.breaks,
          work_ms: workMs,
          break_ms: breakMs,
          total_ms: totalMs
        });

        console.log(`[session] Active session synced (work: ${Math.round(workMs/60000)}m)`);
      }
    } catch (e) {
      console.warn('[session] Real-time sync failed:', e.message);
    }
  }, 5 * 60 * 1000); // 5 minutes
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
      } else if (ssid && Array.isArray(cfg.officeSsids) && cfg.officeSsids.length > 0) {
        isOffice = cfg.officeSsids.includes(ssid);
      } else if (ip) {
        isOffice = (cfg.officeIps || []).includes((ip || '').trim());
      }
      return { ok: true, data: { ip, ssid, isOffice } };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  });
  // Determine if on office network and auto-start work
  try {
    const cfg = loadConfig();
    const [ip, ssid] = await Promise.all([getPublicIp(), getCurrentSsid()]);
    let isOffice = false;
    if (cfg.forceRemote) {
      isOffice = false;
    } else if (cfg.forceOffice) {
      isOffice = true;
    } else if (ssid && Array.isArray(cfg.officeSsids) && cfg.officeSsids.length > 0) {
      isOffice = cfg.officeSsids.includes(ssid);
    } else if (ip) {
      isOffice = (cfg.officeIps || []).includes((ip || '').trim());
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
  // Directly show login or dashboard without splash screen
  showLoginOrDashboard();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', async () => {
  isQuitting = true;

  // Notify admin about app quit
  try {
    const work = loadWork();
    const hasActiveSession = work.current && !work.current.end_ts;

    await backendPost('/app/quit', {
      reason: 'user_action',
      has_active_session: hasActiveSession
    });

    console.log('[admin] Quit notification sent');
  } catch (e) {
    console.warn('[admin] Failed to send quit notification:', e.message);
  }

  // Stop network logging
  try {
    if (netLog.currentlyLogging) {
      await netLog.stopLogging();
      console.log('[netLog] Network logging stopped');
    }
  } catch (e) {
    console.warn('[netLog] Failed to stop logging:', e.message);
  }

  // Stop update checking
  stopPeriodicUpdateChecks();

  try {
    if (backendProc && !backendProc.killed) {
      if (process.platform === 'win32') {
        try {
          execSync(`taskkill /pid ${backendProc.pid} /f /t`, { timeout: 5000 });
        } catch (e) {
          console.warn('[backend] Failed to kill by PID:', e.message);
        }
      } else {
        backendProc.kill('SIGTERM');
      }
    }

    // Force kill ALL emp_monitor.exe processes synchronously
    if (process.platform === 'win32') {
      try {
        execSync('taskkill /IM emp_monitor.exe /F', { timeout: 5000 });
        console.log('[backend] Killed all emp_monitor.exe processes');
      } catch (e) {
        // taskkill returns error if no processes found, which is fine
        if (!e.message.includes('not found')) {
          console.warn('[backend] Failed to kill emp_monitor.exe:', e.message);
        }
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
      try { setDownloadMonitorToken(token); } catch (_) {}
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

// Expose notifications to renderer via IPC
ipcMain.handle('notify', async (_evt, { title, body }) => {
  try {
    notify(String(title || 'Notification'), String(body || ''));
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// Append a line to alerts.log so admins can see updater activity in the shared log
function alertsLog(msg) {
  try {
    // Ensure directory exists
    const dir = path.dirname(ALERTS_LOG);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    const line = `[${new Date().toISOString()}] ${msg}`;
    fs.appendFileSync(ALERTS_LOG, `${line}\n`, 'utf-8');
  } catch (_) { /* ignore */ }
}

function setupAutoUpdater() {

  alertsLog('Auto updater setup');

  //if (!app.isPackaged || !autoUpdater) return; // only in packaged builds with autoUpdater available
  try {
    // Dev-mode visibility and guards
    if (!autoUpdater) {
      alertsLog('auto-updater: unavailable (autoUpdater is null)');
      return;
    }
    if (!app.isPackaged) {
      // In dev, disable actual update checking to avoid 404 errors
      // but still set up logging and event handlers for testing
      alertsLog('auto-updater: dev mode detected - disabling actual update checks to avoid 404 errors');

      // Set up event handlers that just log (no actual checking)
      autoUpdater.on('checking-for-update', () => {
        alertsLog('auto-updater: would check for updates (dev mode)');
      });
      autoUpdater.on('update-available', (info) => {
        alertsLog('auto-updater: update would be available (dev mode)');
      });
      autoUpdater.on('update-not-available', () => {
        alertsLog('auto-updater: no updates available (dev mode)');
      });
      autoUpdater.on('error', (err) => {
        alertsLog(`auto-updater: error in dev mode -> ${err.message}`);
      });

      // Simulate a check result for dev mode
      setTimeout(() => {
        alertsLog('auto-updater: dev mode check complete - no updates available');
      }, 3000);

      return; // Don't set up actual updater in dev mode
    }
    // Configure electron-updater for GitHub releases
    // Force dev update config for testing in development mode - set this first
    autoUpdater.forceDevUpdateConfig = true;

    autoUpdater.logger = {
      info: (msg) => {
        console.log(`[auto-updater] ${msg}`);
        alertsLog(`auto-updater: ${msg}`);
      },
      warn: (msg) => {
        console.warn(`[auto-updater] ${msg}`);
        alertsLog(`auto-updater: ${msg}`);
      },
      error: (msg) => {
        console.error(`[auto-updater] ${msg}`);
        alertsLog(`auto-updater: ${msg}`);
      }
    };

    alertsLog('auto-updater: initialized');

    // electron-updater automatically detects GitHub releases from package.json repository field
    autoUpdater.checkForUpdatesAndNotify = true; // We'll handle notifications manually

    autoUpdater.on('checking-for-update', () => {
      updateState.checking = true; updateState.available = false; updateState.downloaded = false; updateState.progress = null;
      alertsLog('auto-updater: checking for updates...');
      console.log('[auto-updater] Event: checking-for-update fired');
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    autoUpdater.on('update-available', (info) => {
      updateState.checking = false; updateState.available = true; updateState.version = info && info.version;
      console.log(`[auto-updater] Event: update-available fired: ${updateState.version}`);
      alertsLog(`auto-updater: update available -> ${updateState.version || ''}`);
      notify('Update available', `Version ${updateState.version || ''} is downloading in background...`);
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
      // Automatically start download
      try {
        autoUpdater.downloadUpdate();
      } catch (e) {
        console.warn('Auto-download failed:', e.message);
        alertsLog(`auto-updater: auto-download failed -> ${e.message}`);
      }
    });
    autoUpdater.on('update-not-available', () => {
      updateState.checking = false; updateState.available = false; updateState.downloaded = false;
      console.log('[auto-updater] Event: update-not-available fired');
      alertsLog('auto-updater: no updates available');
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    autoUpdater.on('error', (err) => {
      updateState.checking = false;
      console.warn('autoUpdater error:', err && err.message || err);
      alertsLog(`auto-updater: error -> ${(err && err.message) || String(err)}`);

      // Don't show error notifications for common issues in development/testing
      if (err && err.message) {
        const errorMsg = err.message.toLowerCase();
        if (!errorMsg.includes('squirrel') &&
            !errorMsg.includes('no published versions') &&
            !errorMsg.includes('404') &&
            !errorMsg.includes('releases.atom') &&
            !errorMsg.includes('dev-app-update.yml') &&
            !errorMsg.includes('enoent')) {
          notify('Update error', err.message);
        }
      }

      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    autoUpdater.on('download-progress', (p) => {
      updateState.progress = p;
      console.log(`[auto-updater] Download progress: ${Math.round(p.percent)}%`);
      alertsLog(`auto-updater: download ${Math.round(p.percent)}%`);
    });
    autoUpdater.on('update-downloaded', (info) => {
      updateState.downloaded = true; updateState.available = true; updateState.checking = false;
      console.log(`[auto-updater] Update downloaded: ${updateState.version}`);
      alertsLog(`auto-updater: update downloaded -> ${updateState.version || ''}`);

      if (updateState.autoInstall) {
        // Auto-install after a short delay
        notify('Update installing', 'Automatically installing update and restarting...');
        setTimeout(() => {
          try {
            autoUpdater.quitAndInstall(true, true);
          } catch (e) {
            console.warn('Auto-install failed:', e.message);
            alertsLog(`auto-updater: auto-install failed -> ${e.message}`);
          }
        }, 2000);
      } else {
        notify('Update ready', 'Restart to apply the update.');
      }
      if (tray && tray._rebuildMenu) tray._rebuildMenu();
    });
    autoUpdater.on('before-quit-for-update', () => {
      alertsLog('auto-updater: before quit for update');
    });
    // Start periodic update checks (every 4 hours)
    startPeriodicUpdateChecks();
  } catch (e) {
    console.warn('Failed to setup autoUpdater:', e.message);
  }
}

function startPeriodicUpdateChecks() {
  if (!autoUpdater) return;

  // Check for updates every 4 hours (14400000 ms)
  updateCheckInterval = setInterval(() => {
    console.log('[auto-updater] Periodic update check...');
    checkForUpdates(true); // Silent check
  }, 4 * 60 * 60 * 1000);

  // Initial check after 30 seconds (startup delay)
  setTimeout(() => {
    console.log('[auto-updater] Initial startup update check...');
    alertsLog('auto-updater: initial update check scheduled');
    // Make initial check non-silent so it is visible in alerts.log
    checkForUpdates(false);
  }, 30000);
}

function stopPeriodicUpdateChecks() {
  if (updateCheckInterval) {
    clearInterval(updateCheckInterval);
    updateCheckInterval = null;
  }
}

function checkForUpdates(silent = false) {
  if (!autoUpdater) {
    if (!silent) notify('Updater disabled', 'Updates only work in packaged builds.');
    // Also log to alerts so devs see why nothing appears in logs
    alertsLog('auto-updater: disabled (dev mode or unavailable)');
    return;
  }
  try {
    if (!silent) {
      console.log('[auto-updater] Checking for updates...');
      alertsLog('auto-updater: calling checkForUpdates()');
    }
    autoUpdater.checkForUpdates().catch(err => {
      console.warn('checkForUpdates failed:', err.message);
      alertsLog(`auto-updater: checkForUpdates error -> ${err.message}`);
      if (!silent && !err.message.toLowerCase().includes('squirrel')) {
        // Only show notification for non-dev errors
        const errorMsg = err.message.toLowerCase();
        if (!errorMsg.includes('no published versions') &&
            !errorMsg.includes('404') &&
            !errorMsg.includes('releases.atom') &&
            !errorMsg.includes('dev-app-update.yml') &&
            !errorMsg.includes('enoent')) {
          notify('Update check failed', 'Unable to check for updates. Please try again later.');
        }
      }
    });
  } catch (e) {
    console.warn('checkForUpdates failed:', e.message);
    alertsLog(`auto-updater: checkForUpdates exception -> ${e.message}`);
  }
}
function downloadUpdate() {
  if (!autoUpdater) return;
  try { autoUpdater.downloadUpdate(); } catch (e) { console.warn('downloadUpdate failed:', e.message); }
}
function installAndRestart() {
  if (!autoUpdater) return;
  try { autoUpdater.quitAndInstall(true, true); } catch (e) { console.warn('quitAndInstall failed:', e.message); }
}

function toggleAutoInstall() {
  updateState.autoInstall = !updateState.autoInstall;
  console.log(`[auto-updater] Auto-install ${updateState.autoInstall ? 'enabled' : 'disabled'}`);
  notify('Auto-Install', `Automatic update installation ${updateState.autoInstall ? 'enabled' : 'disabled'}.`);
  if (tray && tray._rebuildMenu) tray._rebuildMenu();
}

// IPC handlers for manual update checks
ipcMain.handle('updater:check', async () => {
  try {
    alertsLog('auto-updater: manual check triggered via IPC');
    checkForUpdates(false);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

ipcMain.handle('updater:download', async () => {
  try {
    alertsLog('auto-updater: manual download triggered via IPC');
    downloadUpdate();
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

ipcMain.handle('updater:install', async () => {
  try {
    alertsLog('auto-updater: manual install triggered via IPC');
    installAndRestart();
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});
