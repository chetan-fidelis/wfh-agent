# WFH Agent Client Deployment Script
# Run as Administrator

param(
    [Parameter(Mandatory=$true)]
    [int]$EmployeeId,

    [Parameter(Mandatory=$true)]
    [string]$EmployeeName,

    [Parameter(Mandatory=$true)]
    [string]$Department,

    [Parameter(Mandatory=$true)]
    [string]$ApiKey,

    [string]$ServerUrl = "http://20.197.8.101:5050",

    [string]$InstallPath = "C:\Program Files\WFH Agent"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "WFH Agent Client Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    exit 1
}

# Step 1: Set API Key as System Environment Variable
Write-Host "[1/5] Setting API Key environment variable..." -ForegroundColor Yellow
[System.Environment]::SetEnvironmentVariable("WFH_AGENT_API_KEY", $ApiKey, [System.EnvironmentVariableTarget]::Machine)
Write-Host "✓ API Key configured" -ForegroundColor Green

# Step 2: Update config.json
Write-Host "[2/5] Configuring employee details..." -ForegroundColor Yellow
$configPath = Join-Path $InstallPath "resources\app\monitor_data\config.json"

if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json

    # Update employee info
    $config.emp_id = $EmployeeId
    $config.emp_name = $EmployeeName
    $config.department = $Department

    # Update API settings
    $config.ingestion.enabled = $true
    $config.ingestion.mode = "api"
    $config.ingestion.api.base_url = $ServerUrl
    $config.ingestion.api.auth_env = "WFH_AGENT_API_KEY"

    $config.screenshot_upload.enabled = $true
    $config.screenshot_upload.server_url = $ServerUrl

    # Save config
    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8
    Write-Host "✓ Employee configured: $EmployeeName (ID: $EmployeeId)" -ForegroundColor Green
} else {
    Write-Host "⚠ Config file not found at: $configPath" -ForegroundColor Yellow
    Write-Host "  Please run installer first!" -ForegroundColor Yellow
}

# Step 3: Create firewall rules
Write-Host "[3/5] Configuring Windows Firewall..." -ForegroundColor Yellow
try {
    # Allow outbound connections to server
    $serverHost = ([System.Uri]$ServerUrl).Host
    New-NetFirewallRule -DisplayName "WFH Agent - Outbound" `
                        -Direction Outbound `
                        -Action Allow `
                        -RemoteAddress $serverHost `
                        -Protocol TCP `
                        -ErrorAction SilentlyContinue | Out-Null
    Write-Host "✓ Firewall configured" -ForegroundColor Green
} catch {
    Write-Host "⚠ Firewall configuration skipped" -ForegroundColor Yellow
}

# Step 4: Test connectivity
Write-Host "[4/5] Testing server connectivity..." -ForegroundColor Yellow
try {
    $healthUrl = "$ServerUrl/health"
    $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
    if ($response.status -eq "healthy") {
        Write-Host "✓ Server is reachable and healthy" -ForegroundColor Green
    } else {
        Write-Host "⚠ Server responded but status is not healthy" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ Cannot reach server at $ServerUrl" -ForegroundColor Yellow
    Write-Host "  Please check network connectivity" -ForegroundColor Yellow
}

# Step 5: Restart WFH Agent service/app
Write-Host "[5/5] Restarting WFH Agent..." -ForegroundColor Yellow
try {
    # Kill any running instances
    Get-Process | Where-Object {$_.ProcessName -like "*wfh*" -or $_.ProcessName -eq "emp_monitor"} | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    # Start the app
    $exePath = Join-Path $InstallPath "WFH Agent.exe"
    if (Test-Path $exePath) {
        Start-Process $exePath
        Write-Host "✓ WFH Agent started" -ForegroundColor Green
    } else {
        Write-Host "⚠ Executable not found. Please start manually." -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ Could not restart app automatically" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Employee: $EmployeeName (ID: $EmployeeId)" -ForegroundColor White
Write-Host "Department: $Department" -ForegroundColor White
Write-Host "Server: $ServerUrl" -ForegroundColor White
Write-Host "API Key: $($ApiKey.Substring(0, 8))..." -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Verify app is running (system tray icon)" -ForegroundColor White
Write-Host "2. Check server logs: sudo journalctl -u wfh-ingestion -f" -ForegroundColor White
Write-Host "3. Verify data in database after 1-2 minutes" -ForegroundColor White
Write-Host ""
