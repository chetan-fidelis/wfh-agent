# Group Policy Deployment Script for WFH Agent
# Place in: \\domain\SYSVOL\domain\Policies\{GPO-ID}\Machine\Scripts\Startup

# Configuration
$API_KEY = "b1jWosNKA3wAWrxYSRGmkpDoEaVH0bwKFarLBleL4Oo"
$SERVER_URL = "http://20.197.8.101:5050"
$INSTALLER_PATH = "\\domain\NETLOGON\WFHAgent-Setup.exe"
$INSTALL_DIR = "C:\Program Files\WFH Agent"

# Get employee info from AD
try {
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $adUser = Get-ADUser -Identity $env:USERNAME -Properties EmployeeID, Department
    $empId = $adUser.EmployeeID
    $empName = $adUser.Name
    $department = $adUser.Department
} catch {
    Write-EventLog -LogName Application -Source "WFH Agent" -EventID 1001 -EntryType Warning -Message "Could not retrieve AD user info"
    exit 1
}

# Check if already installed
if (-not (Test-Path $INSTALL_DIR)) {
    # Silent install
    Start-Process -FilePath $INSTALLER_PATH -ArgumentList "/S" -Wait
}

# Set API key
[System.Environment]::SetEnvironmentVariable("WFH_AGENT_API_KEY", $API_KEY, [System.EnvironmentVariableTarget]::Machine)

# Update config
$configPath = Join-Path $INSTALL_DIR "resources\app\monitor_data\config.json"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $config.emp_id = $empId
    $config.emp_name = $empName
    $config.department = $department
    $config.ingestion.api.base_url = $SERVER_URL
    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8
}

Write-EventLog -LogName Application -Source "WFH Agent" -EventID 1000 -EntryType Information -Message "WFH Agent configured for $empName (ID: $empId)"
