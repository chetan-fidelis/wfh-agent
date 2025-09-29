const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const archiver = require('archiver');

console.log('Building single installer for WFH Agent...');

const PROJECT_DIR = __dirname;
const BUILD_DIR = path.join(PROJECT_DIR, 'build');
const TEMP_DIR = path.join(BUILD_DIR, 'temp');
const BACKEND_DIR = path.join(PROJECT_DIR, 'backend');

// Clean and create build directories
if (fs.existsSync(BUILD_DIR)) {
    fs.rmSync(BUILD_DIR, { recursive: true });
}
fs.mkdirSync(BUILD_DIR, { recursive: true });
fs.mkdirSync(TEMP_DIR, { recursive: true });

console.log('Building Python backend...');
process.chdir(BACKEND_DIR);
try {
    // Install requirements
    execSync('pip install -r requirements.txt', { stdio: 'inherit' });

    // Build with PyInstaller
    execSync('pyinstaller emp_monitor.spec --clean --noconfirm', { stdio: 'inherit' });

    // Copy the built exe to temp directory
    const backendExe = path.join(BACKEND_DIR, 'dist', 'emp_monitor.exe');
    const tempBackendExe = path.join(TEMP_DIR, 'emp_monitor.exe');

    if (fs.existsSync(backendExe)) {
        fs.copyFileSync(backendExe, tempBackendExe);
        console.log('Backend built successfully');
    } else {
        throw new Error('Backend exe not found after build');
    }
} catch (error) {
    console.error('Backend build failed:', error.message);
    process.exit(1);
}

console.log('Installing Electron dependencies...');
process.chdir(PROJECT_DIR);
try {
    execSync('npm install', { stdio: 'inherit' });
} catch (error) {
    console.error('npm install failed:', error.message);
    process.exit(1);
}

console.log('Building Electron app...');
try {
    // Copy backend exe to project root for electron-builder
    const projectBackendExe = path.join(PROJECT_DIR, 'backend', 'emp_monitor.exe');
    fs.copyFileSync(path.join(TEMP_DIR, 'emp_monitor.exe'), projectBackendExe);

    // Build with electron-builder for maximum compression
    execSync('npx electron-builder --win nsis --x64', { stdio: 'inherit' });

    console.log('Build completed successfully!');

    // Find the installer file
    const distDir = path.join(PROJECT_DIR, 'dist');
    if (fs.existsSync(distDir)) {
        const files = fs.readdirSync(distDir);
        const installer = files.find(file => file.endsWith('.exe'));
        if (installer) {
            const installerPath = path.join(distDir, installer);
            const stats = fs.statSync(installerPath);
            console.log(`Installer created: ${installer}`);
            console.log(`Size: ${(stats.size / 1024 / 1024).toFixed(2)} MB`);
            console.log(`Location: ${installerPath}`);
        }
    }

} catch (error) {
    console.error('Electron build failed:', error.message);
    process.exit(1);
}

console.log('Cleaning up temporary files...');
fs.rmSync(TEMP_DIR, { recursive: true });

console.log('Single installer build completed successfully!');