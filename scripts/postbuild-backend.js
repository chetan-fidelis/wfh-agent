// Copies PyInstaller output to backend/emp_monitor.exe in a shell-agnostic way
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function killExistingProcess() {
  try {
    execSync('taskkill /F /IM emp_monitor.exe /T 2>nul', { stdio: 'ignore' });
    console.log('[build:backend] Killed existing emp_monitor.exe processes');
    // Wait a moment for the process to fully terminate
    setTimeout(() => {}, 1000);
  } catch (err) {
    // Process wasn't running, which is fine
  }
}

function copyFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });

  // Remove destination file if it exists
  if (fs.existsSync(dest)) {
    try {
      fs.unlinkSync(dest);
      console.log('[build:backend] Removed existing destination file');
    } catch (err) {
      console.warn('[build:backend] Could not remove existing file:', err.message);
    }
  }

  fs.copyFileSync(src, dest);
  console.log(`[build:backend] Copied ${src} -> ${dest}`);
}

(function main() {
  const root = path.resolve(__dirname, '..');
  const src = path.join(root, 'dist', 'emp_monitor.exe');
  const dest = path.join(root, 'backend', 'emp_monitor.exe');

  if (!fs.existsSync(src)) {
    console.error(`[build:backend] Source not found: ${src}`);
    process.exit(1);
  }

  // Kill any existing processes first
  killExistingProcess();

  // Small delay to ensure process is fully terminated
  setTimeout(() => {
    copyFile(src, dest);
  }, 1000);
})();
