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
          <h1 class="title">Harmony</h1>
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
      togglePassword.textContent = isPwd ? '🙈' : '👁️';
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
    authUrlInput.value = authUrlInput.value || 'https://nexoleats.fidelisam.in/api/auth/login';
  }

  loginBtn.addEventListener('click', async () => {
    console.log('Login button clicked');
    err.textContent = '';
    loginBtn.disabled = true;
    const oldHtml = loginBtn.innerHTML;
    loginBtn.innerHTML = '<span class="loading-spinner" style="display:inline-block"></span><span class="btn-text">Signing in...</span>';
    try {
      const serverAuthUrl = (authUrlInput ? authUrlInput.value : 'https://nexoleats.fidelisam.in/api/auth/login').trim();
      const username = (userInput ? userInput.value : '').trim();
      const password = passInput ? passInput.value : '';

      console.log('Login attempt:', { serverAuthUrl, username: username ? '[PROVIDED]' : '[MISSING]', password: password ? '[PROVIDED]' : '[MISSING]' });

      if (!serverAuthUrl || !username || !password) {
        const message = 'Please fill all fields';
        console.log('Validation error:', message);
        if (err) {
          err.textContent = message;
          err.classList.add('show');
        }
        return;
      }
      const empIdVal = empIdInput ? empIdInput.value.trim() : '';
      const effectiveEmpId = empIdVal || (cfg.empId || 101);

      console.log('Calling window.api.login...');
      const res = await window.api.login(serverAuthUrl, username, password, effectiveEmpId);
      console.log('Login response:', res);

      if (res && res.ok) {
        console.log('Login successful, navigating to dashboard');
        await window.api.navTo('dashboard');
      } else {
        const errorMsg = res?.error || 'Login failed';
        console.log('Login failed:', errorMsg);
        if (err) {
          err.textContent = errorMsg;
          err.classList.add('show');
        }
      }
    } catch (e) {
      const errorMsg = e.message || 'Login error';
      console.error('Login exception:', e);
      if (err) {
        err.textContent = errorMsg;
        err.classList.add('show');
      }
    } finally {
      loginBtn.disabled = false;
      loginBtn.innerHTML = oldHtml || 'Sign In';
    }
  });
})();
