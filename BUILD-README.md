# WFH Agent - Single Installer Build

This project creates a single executable installer that contains both the Python backend and Electron frontend for easy deployment.

## Prerequisites

1. **Node.js** (v14 or higher) - Download from https://nodejs.org/
2. **Python** (v3.8 or higher) - Download from https://python.org/
3. **Windows** (for building Windows installer)

## Quick Build

### Option 1: Using Batch File (Recommended)
```cmd
build-installer.bat
```

### Option 2: Using PowerShell
```powershell
.\build-installer.ps1
```

### Option 3: Manual Build
```cmd
npm run clean
npm install
npm run build:single
```

## What Gets Built

The build process creates:

1. **Python Backend** - Compiled into a single `emp_monitor.exe` using PyInstaller
2. **Electron Frontend** - Packaged with the backend into a single NSIS installer
3. **Single Installer** - Located in `dist/` folder (typically ~100-200MB)

## Build Process Details

1. **Clean**: Removes previous build artifacts
2. **Backend Build**:
   - Installs Python dependencies from `requirements.txt`
   - Uses PyInstaller to create standalone `emp_monitor.exe`
   - Embeds all Python dependencies into the executable
3. **Frontend Build**:
   - Installs Node.js dependencies
   - Uses electron-builder to create NSIS installer
   - Includes the backend executable as an extra resource
   - Applies maximum compression

## Output

The final installer will be in the `dist/` folder with a name like:
- `WFH Agent Setup 0.1.0.exe`

This single file contains:
- Complete Electron application
- Python backend executable
- All dependencies
- Installation wizard
- Desktop shortcuts
- Start menu entries

## Deployment

Simply copy the generated `.exe` file to any Windows machine and run it. No additional dependencies or setup required.

## Troubleshooting

1. **Build fails with Python errors**: Ensure Python and pip are in your PATH
2. **Build fails with Node errors**: Run `npm install` manually first
3. **Large file size**: This is expected as it contains all dependencies
4. **Antivirus warnings**: The packaged executable may trigger false positives

## File Structure After Build

```
dist/
└── WFH Agent Setup 0.1.0.exe  (Single installer file)
```

The installer will extract and install to:
```
%USERPROFILE%/AppData/Local/Programs/WFH Agent/
├── WFH Agent.exe              (Main Electron app)
├── resources/
│   └── app.asar              (Frontend code)
├── backend/
│   └── emp_monitor.exe       (Python backend)
└── ...                       (Electron runtime files)
```