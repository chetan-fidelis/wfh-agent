# WFH Agent Single Installer Build Script
Write-Host "Building WFH Agent Single Installer..." -ForegroundColor Green
Write-Host ""

# Function to check if command exists
function Test-Command($cmdname) {
    try {
        if (Get-Command $cmdname -ErrorAction Stop) {
            return $true
        }
    }
    catch {
        return $false
    }
}

# Check if Node.js is installed
if (!(Test-Command "node")) {
    Write-Host "ERROR: Node.js is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Node.js from https://nodejs.org/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if Python is installed
if (!(Test-Command "python")) {
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python from https://python.org/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if pip is available
if (!(Test-Command "pip")) {
    Write-Host "ERROR: pip is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please ensure pip is installed with Python" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

try {
    # Clean previous builds
    Write-Host "Cleaning previous builds..." -ForegroundColor Blue
    npm run clean

    # Install dependencies
    Write-Host "Installing Node.js dependencies..." -ForegroundColor Blue
    npm install

    # Build the single installer
    Write-Host "Building single installer..." -ForegroundColor Blue
    npm run build:single

    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host "Build completed successfully!" -ForegroundColor Green
    Write-Host "Check the 'dist' folder for your installer." -ForegroundColor Green
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host ""
}
catch {
    Write-Host ""
    Write-Host "ERROR: Build failed" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
}

Read-Host "Press Enter to exit"