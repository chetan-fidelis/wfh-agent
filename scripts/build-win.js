/*
  Windows packaging script using electron-winstaller (Squirrel.Windows)
  - Assumes you have already run `npm run pack:win` to generate dist/WFH Agent-win32-x64
  - Produces installer under release/ with RELEASES and .nupkg files
*/

const path = require('path');
const fs = require('fs');
const { MSICreator } = (() => { try { return require('electron-wix-msi'); } catch (_) { return {}; } })();
const electronWinstaller = require('electron-winstaller');

async function main() {
  const root = __dirname ? path.resolve(__dirname, '..') : process.cwd();
  const pkg = require(path.join(root, 'package.json'));
  const appName = pkg.build && pkg.build.productName ? pkg.build.productName : 'WFH Agent';
  const appExeName = `${appName}.exe`;

  const outDir = path.join(root, 'dist');
  const releaseDir = path.join(root, 'release');
  const appDir = path.join(outDir, `${appName}-win32-x64`);

  if (!fs.existsSync(appDir)) {
    console.error(`Packaged app not found at ${appDir}. Run \`npm run pack:win\` first.`);
    process.exit(1);
  }
  if (!fs.existsSync(releaseDir)) fs.mkdirSync(releaseDir, { recursive: true });

  const iconPath = path.join(root, 'assets', 'icon.ico');
  const loadingGif = path.join(root, 'assets', 'installing.gif');

  try {
    const result = await electronWinstaller.createWindowsInstaller({
      appDirectory: appDir,
      outputDirectory: releaseDir,
      authors: pkg.author || 'Fidelis Technology Services Pvt. Ltd.',
      exe: appExeName,
      title: appName,
      setupExe: `${appName}-Setup-${pkg.version}.exe`,
      setupIcon: fs.existsSync(iconPath) ? iconPath : undefined,
      loadingGif: fs.existsSync(loadingGif) ? loadingGif : undefined,
      noMsi: true,
    });
    console.log('Squirrel.Windows artifacts created at:', releaseDir);
    console.log('Done. Upload the RELEASES and *.nupkg and Setup.exe to your GitHub Release for updates.');
  } catch (e) {
    console.error('Failed to create Windows installer:', e);
    process.exit(1);
  }
}

main();
