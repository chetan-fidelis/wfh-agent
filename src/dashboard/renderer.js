(function(){
  const logoutBtn = document.getElementById('logoutBtn');
  const startBtn = document.getElementById('startBtn');
  const breakBtn = document.getElementById('breakBtn');
  const endBtn = document.getElementById('endBtn');
  const empNameEl = document.getElementById('empName');
  const empMetaEl = document.getElementById('empMeta');
  const mgrNameEl = document.getElementById('mgrName');
  const mgrMetaEl = document.getElementById('mgrMeta');
  const sysInfoEl = document.getElementById('sysInfo');
  const sysMetaEl = document.getElementById('sysMeta');
  const kpiTotalWork = document.getElementById('kpiTotalWork');
  const kpiSessions = document.getElementById('kpiSessions');
  const kpiBreak = document.getElementById('kpiBreak');
  const kpiAvg = document.getElementById('kpiAvg');
  const wsBody = document.getElementById('wsBody');
  const wsPageSizeSel = document.getElementById('wsPageSize');
  const wsPagePrev = document.getElementById('wsPagePrev');
  const wsPageNext = document.getElementById('wsPageNext');
  const wsPageInfo = document.getElementById('wsPageInfo');
  const wsPageNums = document.getElementById('wsPageNums');
  const rangeSel = document.getElementById('rangeSel');
  const applyRange = document.getElementById('applyRange');
  const netBadge = document.getElementById('netBadge');
  const winMin = document.getElementById('winMin');
  const winMax = document.getElementById('winMax');
  const winClose = document.getElementById('winClose');
  const sessionTimer = document.getElementById('sessionTimer');
  const banner = document.getElementById('banner');
  const bannerText = document.getElementById('bannerText');
  const bannerClose = document.getElementById('bannerClose');
  const offlineChip = document.getElementById('offlineChip');
  const footerClock = document.getElementById('footerClock');
  const footerVer = document.getElementById('footerVer');
  let toastHost = document.getElementById('toastHost');

  function msToHuman(ms) {
    const s = Math.floor(ms / 1000);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const rs = s % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m`;
    return `${rs}s`;
  }

  function notifyNative(title, msg) {
    try { if (window.api && window.api.notify) window.api.notify(title, msg); } catch (_) {}
  }
  // Listen to auto-start ack
  if (window.api && window.api.onWorkAutoStart) {
    window.api.onWorkAutoStart(({ ok }) => {
      console.log('work:autoStart', { ok });
      
      if (!banner || !bannerText) return;
      banner.classList.remove('success', 'info', 'error');
      banner.classList.add(ok ? 'success' : 'error');
      bannerText.textContent = ok ? 'Work started automatically.' : 'Tried to auto-start work, but backend was unreachable.';
      banner.style.display = 'flex';
      setTimeout(() => { if (banner && banner.style.display !== 'none') banner.style.display = 'none'; }, 6000);
      showToast({ title: ok ? 'Sync Successful' : 'Sync Failed', msg: ok ? 'Auto-start synced with server.' : 'Auto-start queued; will retry when online.', type: ok ? 'success' : 'error' });
      refreshState();
    });
  }

  // Footer clock
  function tickClock() {
    try { if (footerClock) footerClock.textContent = new Date().toLocaleString(); } catch(_) {}
  }
  tickClock();
  setInterval(tickClock, 1000);

  // Toasts
  function showToast({ title = '', msg = '', type = 'info', timeout = 4000 } = {}) {
    if (!toastHost) {
      // Create host dynamically if missing (script may load before element)
      toastHost = document.createElement('div');
      toastHost.id = 'toastHost';
      toastHost.className = 'toast-host';
      document.body.appendChild(toastHost);
    }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `${title ? `<div class="title">${title}</div>` : ''}${msg ? `<div class="msg">${msg}</div>` : ''}`;
    toastHost.appendChild(el);
    const t = setTimeout(() => {
      try { el.remove(); } catch (_) {}
      clearTimeout(t);
    }, Math.max(1500, timeout|0));
  }

  // Footer version
  async function setVersion() {
    try {
      // Dont Show Electron version
      const v = await (window.api && window.api.appVersion ? window.api.appVersion() : null);
      if (v && v.ok && footerVer) {
        const parts = [];
        if (v.app) parts.push(`v${v.app}`);
        footerVer.textContent = parts.join(' • ');
      }
    } catch (_) {}
  }
  setVersion();

  // Connectivity check and offline chip
  async function checkConnectivity() {
    try {
      const cfg = await window.api.getConfig();
      const pong = await window.api.get('/status', cfg.serverUrl);
      const online = pong && pong.ok !== false; // treat 200 as online      

      if (offlineChip) {
        offlineChip.textContent = online ? 'Online' : 'Offline';
        offlineChip.classList.toggle('chip-online', !!online);
        offlineChip.classList.toggle('chip-offline', !online);
      }
      return online;
    } catch (_) {
      if (offlineChip) {
        offlineChip.textContent = 'Offline';
        offlineChip.classList.remove('chip-online');
        offlineChip.classList.add('chip-offline');
      }
      return false;
    }
  }
  checkConnectivity();
  setInterval(checkConnectivity, 15000);

  async function refreshNetBadge() {
    try {
      if (!netBadge) return;
      const r = await window.api.netStatus();
      if (r && r.ok && r.data) {
        const isOffice = r.data.isOffice;
        const ip = r.data.ip;

        netBadge.textContent = isOffice ? 'Office' : 'Remote';
        netBadge.classList.remove('office', 'remote');
        netBadge.classList.add(isOffice ? 'office' : 'remote');
        netBadge.title = (isOffice ? 'Office IP ' : 'Remote IP ') + (ip || '');
      } else {
        netBadge.textContent = '—';
        netBadge.title = 'Network status unavailable';
        netBadge.classList.remove('office', 'remote');
      }
    } catch (_) {}
  }

  async function refreshState() {
    const cfg = await window.api.getConfig();
    const st = await window.api.get('/session/state', cfg.serverUrl);
    let state = 'idle';
    if (st.ok && st.data && st.data.state) {
      state = st.data.state.status || 'idle';
    } else {
      // Fallback to local tracker state
      try {
        const ls = await window.api.workState();
        if (ls && ls.current && !ls.current.end_ts) state = (ls.current.status || 'active');
      } catch (_) {}
    }
    // If backend says idle but local tracker is active, prefer local (offline started)
    if (state === 'idle') {
      try {
        const ls = await window.api.workState();
        if (ls && ls.current && !ls.current.end_ts) state = (ls.current.status || 'active');
      } catch (_) {}
    }
    startBtn.disabled = state === 'active' || state === 'break';
    breakBtn.disabled = state === 'idle';
    breakBtn.textContent = state === 'break' ? 'Resume' : 'Take Break';
    endBtn.disabled = state === 'idle';
    currentState = state;
  }

  // Live timer
  let currentState = 'idle';
  let currentStartTs = 0; // ms
  let currentBreakAccum = 0; // ms
  async function computeTimerState() {
    try {
      const cfg = await window.api.getConfig();
      const st = await window.api.get('/session/state', cfg.serverUrl);
      if (st.ok && st.data && st.data.state && st.data.state.start_ts) {
        const startMs = new Date(st.data.state.start_ts).getTime();
        let breakMs = 0;
        const br = st.data.state.breaks || [];
        for (const b of br) {
          if (b.start_ts) {
            const bs = new Date(b.start_ts).getTime();
            const be = b.end_ts ? new Date(b.end_ts).getTime() : Date.now();
            breakMs += Math.max(0, be - bs);
          }
        }
        currentStartTs = startMs;
        currentBreakAccum = breakMs;
        currentState = br.length > 0 && !br[br.length - 1].end_ts ? 'break' : 'active';
        return;
      }
    } catch (_) {}
    // Fallback to local
    try {
      const ls = await window.api.workState();
      if (ls && ls.current && ls.current.start_ts && !ls.current.end_ts) {
        currentStartTs = new Date(ls.current.start_ts).getTime();
        let breakMs = 0;
        const br = ls.current.breaks || [];
        for (const b of br) {
          if (b.start_ts) {
            const bs = new Date(b.start_ts).getTime();
            const be = b.end_ts ? new Date(b.end_ts).getTime() : Date.now();
            breakMs += Math.max(0, be - bs);
          }
        }
        currentBreakAccum = breakMs;
        currentState = br.length > 0 && !br[br.length - 1].end_ts ? 'break' : 'active';
        return;
      }
    } catch (_) {}
    currentStartTs = 0; currentBreakAccum = 0; currentState = 'idle';
  }

  function tickTimer() {
    if (!sessionTimer) return;
    if (!currentStartTs) {
      sessionTimer.textContent = '—';
      return;
    }
    const now = Date.now();
    const total = now - currentStartTs;
    const work = Math.max(0, total - currentBreakAccum);
    const label = currentState === 'break' ? 'Break' : 'Work';
    sessionTimer.textContent = `${label}: ${msToHuman(work)}`;
  }

  async function refreshSummary() {
    const cfg = await window.api.getConfig();
    const defaultDays = (cfg && cfg.ui && Number.isFinite(parseInt(cfg.ui.session_days_default)))
      ? parseInt(cfg.ui.session_days_default, 10)
      : 7;
    const days = parseInt(rangeSel ? rangeSel.value : String(defaultDays), 10) || defaultDays;
    const res = await window.api.get(`/session/summary?days=${days}`, cfg.serverUrl);
    if (res.ok && res.data) {
      const k = res.data.kpi || {};
      kpiTotalWork.textContent = msToHuman(k.total_work_ms || 0);
      kpiBreak.textContent = msToHuman(k.total_break_ms || 0);
      kpiAvg.textContent = msToHuman(k.avg_work_ms || 0);
      kpiSessions.textContent = (k.sessions_completed || 0).toString();

      // Show newest first (descending by start_ts)
      const fetched = (res.data.rows || []).slice().sort((a, b) => {
        const ad = new Date(a.start_ts || a.start || 0).getTime();
        const bd = new Date(b.start_ts || b.start || 0).getTime();
        return bd - ad; // newest first
      });
      // If API returned empty, keep previous list to avoid flicker/empty state during active session start
      if (fetched.length > 0) {
        pagination.allRows = fetched;
        pagination.pageIndex = 0;
      }
      const pagEl = document.querySelector('.table-pagination');
      if (pagEl) pagEl.style.display = 'flex';
      renderSessionsPage();
    }
  }

  // Pagination state and helpers
  const pagination = {
    allRows: [],
    pageIndex: 0,
    pageSize: 10,
  };

  function renderSessionsPage() {
    const { allRows, pageIndex, pageSize } = pagination;
    const total = allRows.length;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    const clampedIndex = Math.min(Math.max(0, pageIndex), pages - 1);
    pagination.pageIndex = clampedIndex;
    const start = clampedIndex * pageSize;
    const end = Math.min(start + pageSize, total);
    const slice = allRows.slice(start, end);

    if (wsBody) wsBody.innerHTML = '';
    slice.forEach(r => {
      const tr = document.createElement('tr');
      const startDt = new Date(r.start_ts);
      const endDt = r.end_ts ? new Date(r.end_ts) : null;
      const dateStr = startDt.toLocaleDateString();
      const stStr = startDt.toLocaleTimeString();
      const enStr = endDt ? endDt.toLocaleTimeString() : '—';
      const td1 = document.createElement('td'); td1.textContent = dateStr;
      const td2 = document.createElement('td'); td2.textContent = stStr;
      const td3 = document.createElement('td'); td3.textContent = enStr;
      const td4 = document.createElement('td'); td4.textContent = msToHuman(r.work_ms || 0);
      const td5 = document.createElement('td'); td5.textContent = msToHuman(r.break_ms || 0);
      const td6 = document.createElement('td'); td6.textContent = msToHuman(r.total_ms || 0);
      const td7 = document.createElement('td'); td7.textContent = r.status || 'completed';
      tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3); tr.appendChild(td4); tr.appendChild(td5); tr.appendChild(td6); tr.appendChild(td7);
      wsBody.appendChild(tr);
    });

    if (wsPageInfo) {
      wsPageInfo.textContent = `Page ${clampedIndex + 1} of ${pages}`;
    }
    if (wsPagePrev) wsPagePrev.disabled = clampedIndex <= 0;
    if (wsPageNext) wsPageNext.disabled = clampedIndex >= pages - 1;

    // Render numbered page buttons
    if (wsPageNums) {
      wsPageNums.innerHTML = '';

      if (pages <= 7) {
        // Show all pages if 7 or fewer
        for (let p = 0; p < pages; p++) {
          const b = document.createElement('button');
          b.className = 'btn sm pager-btn' + (p === clampedIndex ? ' active' : '');
          b.textContent = String(p + 1);
          b.addEventListener('click', () => {
            pagination.pageIndex = p;
            renderSessionsPage();
          });
          wsPageNums.appendChild(b);
        }
      } else {
        // For many pages: show first, pages around current, and last
        const addBtn = (label, page, active=false) => {
          const b = document.createElement('button');
          b.className = 'btn sm pager-btn' + (active ? ' active' : '');
          b.textContent = String(label);
          b.addEventListener('click', () => {
            pagination.pageIndex = page;
            renderSessionsPage();
          });
          wsPageNums.appendChild(b);
        };

        const addEllipsis = () => {
          const span = document.createElement('span');
          span.textContent = '...';
          span.style.margin = '0 4px';
          wsPageNums.appendChild(span);
        };

        // Always show first page
        addBtn(1, 0, clampedIndex === 0);

        if (clampedIndex > 3) {
          addEllipsis();
        }

        // Show pages around current page
        const start = Math.max(1, clampedIndex - 1);
        const end = Math.min(pages - 2, clampedIndex + 1);

        for (let p = start; p <= end; p++) {
          addBtn(p + 1, p, p === clampedIndex);
        }

        if (clampedIndex < pages - 4) {
          addEllipsis();
        }

        // Always show last page
        addBtn(pages, pages - 1, clampedIndex === pages - 1);
      }
    }
  }

  if (wsPageSizeSel) {
    wsPageSizeSel.addEventListener('change', () => {
      const v = parseInt(wsPageSizeSel.value, 10) || 10;
      pagination.pageSize = v;
      pagination.pageIndex = 0;
      renderSessionsPage();
    });
  }
  if (wsPagePrev) {
    wsPagePrev.addEventListener('click', () => {
      pagination.pageIndex = Math.max(0, pagination.pageIndex - 1);
      renderSessionsPage();
    });
  }
  if (wsPageNext) {
    wsPageNext.addEventListener('click', () => {
      const pages = Math.max(1, Math.ceil((pagination.allRows.length || 0) / pagination.pageSize));
      pagination.pageIndex = Math.min(pages - 1, pagination.pageIndex + 1);
      renderSessionsPage();
    });
  }

  async function loadSystemInfo() {
    try {
      const appVer = await window.api.getVersion();
      const osInfo = await window.api.getSystemInfo();
      
      const osName = osInfo && osInfo.platform ? osInfo.platform.toUpperCase() : 'Unknown';
      const osArch = osInfo && osInfo.arch ? osInfo.arch : '';
      const appVersion = appVer && appVer.app ? `v${appVer.app}` : 'Unknown';
      
      sysInfoEl.textContent = `${osName} ${osArch}`;
      sysMetaEl.textContent = `Harmony ${appVersion}`;
    } catch (e) {
      sysInfoEl.textContent = 'System';
      sysMetaEl.textContent = 'Info unavailable';
    }
  }

  async function loadProfile() {
    try {
      const cfg = await window.api.getConfig();
      const sess = await window.api.getSession();
      const empId = (sess && sess.hrmsEmpId) || (cfg.empId || 101); // prefer dynamic login id
      const res = await window.api.hrmsGet(`employees/${empId}/details`);
      if (res && res.ok && res.data) {
        const emp = res.data.employee || {};
        const mgr = res.data.manager || {};
        empNameEl.textContent = `${emp.name || '-'} (${emp.id || ''})`;
        empMetaEl.textContent = `${emp.designation || ''} • ${emp.department || ''}`;
        mgrNameEl.textContent = `${mgr.name || '-'} (${mgr.id || ''})`;
        mgrMetaEl.textContent = mgr.email || '';
      } else {
        empNameEl.textContent = '—';
        empMetaEl.textContent = res && res.error ? res.error : 'Profile not available';
        mgrNameEl.textContent = '—';
        mgrMetaEl.textContent = '';
      }
      // Load system info
      loadSystemInfo();
    } catch (e) {
      empMetaEl.textContent = e.message || 'Failed to load profile';
      loadSystemInfo();
    }
  }

  logoutBtn.addEventListener('click', async () => {
    await window.api.logout();
    await window.api.navTo('login');
  });

  startBtn.addEventListener('click', async () => {
    const cfg = await window.api.getConfig();
    const r = await window.api.post('/session/start', {} , cfg.serverUrl);
    if (!r.ok) {
      console.error('start error', r.error);
      // Offline/local fallback: start local tracker and show banner
      try { await window.api.workStart(); } catch (_) {}
      notifyNative('Work Started', 'Tracking started locally (offline).');
      if (banner && bannerText) {
        banner.classList.remove('success', 'info', 'error');
        banner.classList.add('info');
        bannerText.textContent = 'Started work locally (offline). Will sync when online.';
        banner.style.display = 'flex';
        setTimeout(() => { if (banner && banner.style.display !== 'none') banner.style.display = 'none'; }, 6000);
      }
      showToast({ title: 'Sync Queued', msg: 'Start will sync when online.', type: 'info' });
    } else {
      notifyNative('Work Started', 'Synced with server.');
      showToast({ title: 'Sync Successful', msg: 'Work start synced with server.', type: 'success' });
    }
    await refreshState();
    await refreshSummary();
    await computeTimerState();
  });

  breakBtn.addEventListener('click', async () => {
    const cfg = await window.api.getConfig();
    const st = await window.api.get('/session/state', cfg.serverUrl);
    if (st.ok && st.data && st.data.state) {
      const state = st.data.state.status || 'idle';
      const path = state === 'break' ? '/session/break/end' : '/session/break/start';
      const r = await window.api.post(path, {}, cfg.serverUrl);
      if (!r.ok) {
        console.error('break toggle error', r.error);
        showToast({ title: 'Sync Queued', msg: 'Break toggle will sync when online.', type: 'info' });
      } else {
        showToast({ title: 'Sync Successful', msg: 'Break toggle synced with server.', type: 'success' });
      }
      await refreshState();
      await refreshSummary();
      await computeTimerState();
      notifyNative(state === 'break' ? 'Resumed Work' : 'Break Started', state === 'break' ? 'Work resumed.' : 'Enjoy your break.');
    }
  });

  endBtn.addEventListener('click', async () => {
    const cfg = await window.api.getConfig();
    const r = await window.api.post('/session/end', {}, cfg.serverUrl);
    if (!r.ok) {
      console.error('end error', r.error);
      showToast({ title: 'Sync Queued', msg: 'End session will sync when online.', type: 'info' });
    } else {
      showToast({ title: 'Sync Successful', msg: 'Work end synced with server.', type: 'success' });
    }
    await refreshState();
    await refreshSummary();
    await computeTimerState();
    notifyNative('Work Ended', 'Good job today!');
  });

  if (applyRange) {
    applyRange.addEventListener('click', async () => {
      await refreshSummary();
    });
  }

  // Initial loads
  refreshState();
  refreshSummary();
  computeTimerState();
  loadProfile();
  refreshNetBadge();
  setInterval(computeTimerState, 5000);
  setInterval(tickTimer, 1000);
  // Wire window controls
  if (winMin) winMin.addEventListener('click', () => window.api.winMinimize());
  if (winMax) winMax.addEventListener('click', () => window.api.winMaximizeToggle());
  if (winClose) winClose.addEventListener('click', () => window.api.winClose());
  // Banner dismiss
  if (bannerClose) bannerClose.addEventListener('click', () => { if (banner) banner.style.display = 'none'; });
  // Listen to power break events
  if (window.api && window.api.onPowerBreak) {
    window.api.onPowerBreak(({ action, source }) => {
      if (!banner || !bannerText) return;
      banner.classList.remove('success', 'info', 'error');
      if (action === 'start') {
        banner.classList.add('info');
        bannerText.textContent = `System ${source}: Work paused (Break started).`;
      } else {
        banner.classList.add('success');
        bannerText.textContent = `System ${source}: Break ended. Resumed work.`;
      }
      banner.style.display = 'flex';
      setTimeout(() => { if (banner && banner.style.display !== 'none') banner.style.display = 'none'; }, 8000);
    });
  }
  setInterval(refreshState, 15000);
  setInterval(refreshSummary, 120000);
  setInterval(loadProfile, 10 * 60 * 1000);
  setInterval(refreshNetBadge, 5 * 60 * 1000);
})();
