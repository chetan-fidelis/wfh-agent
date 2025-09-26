(async function() {
  const cfg = await window.api.getConfig();
  const authUrlInput = document.getElementById('authUrl');
  const userInput = document.getElementById('username');
  const passInput = document.getElementById('password');
  const empIdInput = document.getElementById('empId'); // may be absent
  const loginBtn = document.getElementById('loginBtn');
  const err = document.getElementById('err') || document.getElementById('errorMessage');

  // Inject minimal header with window controls if not present
  try {
    const container = document.querySelector('.container');
    if (container && !document.querySelector('.header')) {
      const header = document.createElement('div');
      header.className = 'header';
      header.innerHTML = `
        <div class="header-left">
          <h1 class="title">WFH - Harmony</h1>
        </div>
        <div class="header-right">
          <div class="win-controls">
            <div id="winMin" class="win-btn" title="Minimize"><span></span></div>
            <div id="winMax" class="win-btn max" title="Maximize"><span></span></div>
            <div id="winClose" class="win-btn close" title="Close"><span></span></div>
          </div>
        </div>`;
      container.prepend(header);

      // Wire window controls
      const winMin = document.getElementById('winMin');
      const winMax = document.getElementById('winMax');
      const winClose = document.getElementById('winClose');
      if (winMin) winMin.addEventListener('click', () => window.api.winMinimize());
      if (winMax) winMax.addEventListener('click', () => window.api.winMaximizeToggle());
      if (winClose) winClose.addEventListener('click', () => window.api.winClose());
    }
  } catch {}

  // Password show/hide toggle (if present)
  const togglePassword = document.getElementById('togglePassword');
  if (togglePassword && passInput) {
    togglePassword.addEventListener('click', () => {
      const isPwd = passInput.getAttribute('type') === 'password';
      passInput.setAttribute('type', isPwd ? 'text' : 'password');
    });
  }

  // Handle form submit if present to prevent full page reload
  const loginForm = document.getElementById('loginForm');
  if (loginForm && loginBtn) {
    loginForm.addEventListener('submit', (e) => {
      e.preventDefault();
      loginBtn.click();
    });
  }

  // Default HRMS auth endpoint
  if (authUrlInput) {
    authUrlInput.value = authUrlInput.value || 'https://fhq.fidelisam.in/api/auth/login';
  }

  loginBtn.addEventListener('click', async () => {
    err.textContent = '';
    loginBtn.disabled = true;
    const oldHtml = loginBtn.innerHTML;
    loginBtn.innerHTML = '<span class="loading-spinner" style="display:inline-block"></span><span class="btn-text">Signing in...</span>';
    try {
      const serverAuthUrl = (authUrlInput ? authUrlInput.value : 'https://fhq.fidelisam.in/api/auth/login').trim();
      const username = (userInput ? userInput.value : '').trim();
      const password = passInput ? passInput.value : '';
      if (!serverAuthUrl || !username || !password) {
        if (err) err.textContent = 'Please fill all fields';
        return;
      }
      const empIdVal = empIdInput ? empIdInput.value.trim() : '';
      const effectiveEmpId = empIdVal || (cfg.empId || 101);
      const res = await window.api.login(serverAuthUrl, username, password, effectiveEmpId);
      if (res && res.ok) {
        await window.api.navTo('dashboard');
      } else {
        if (err) err.textContent = res.error || 'Login failed';
      }
    } catch (e) {
      if (err) err.textContent = e.message || 'Login error';
    } finally {
      loginBtn.disabled = false;
      loginBtn.innerHTML = oldHtml || 'Login';
    }
  });
})();
