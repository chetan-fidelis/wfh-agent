# WFH Agent - Installation Guide for IT Administrators

## 📋 Pre-Installation Checklist

### Server Requirements
- ✅ Ingestion server deployed and running
- ✅ API key generated and documented
- ✅ Server URL accessible from client network
- ✅ PostgreSQL database configured
- ✅ Firewall rules allow outbound connections to server

### Client Requirements
- Windows 10/11 (64-bit)
- 200 MB disk space
- Administrator access for installation
- Network connectivity to ingestion server

---

## 🚀 Installation Methods

### Method 1: Manual Installation (Small Scale)

**Step 1: Run Installer**
```
1. Double-click WFHAgent-Setup.exe
2. Follow installation wizard
3. Install to default location (C:\Program Files\WFH Agent)
```

**Step 2: Configure Environment Variable**
```powershell
# Run as Administrator
setx WFH_AGENT_API_KEY "b1jWosNKA3wAWrxYSRGmkpDoEaVH0bwKFarLBleL4Oo" /M
```

**Step 3: Update Configuration**
```
1. Navigate to: C:\Program Files\WFH Agent\resources\app\monitor_data
2. Edit config.json
3. Set:
   - emp_id: <employee_id>
   - emp_name: <employee_name>
   - department: <department>
   - ingestion.api.base_url: http://20.197.8.101:5050
```

**Step 4: Start Application**
```
1. Launch "WFH Agent" from Start Menu
2. Verify system tray icon appears
3. Check server logs for incoming data
```

---

### Method 2: Automated Deployment (Recommended)

**Using PowerShell Script**

```powershell
# Run as Administrator
.\scripts\deploy-client.ps1 `
    -EmployeeId 18698 `
    -EmployeeName "John Doe" `
    -Department "Engineering" `
    -ApiKey "b1jWosNKA3wAWrxYSRGmkpDoEaVH0bwKFarLBleL4Oo" `
    -ServerUrl "http://20.197.8.101:5050"
```

**Using Batch File (Even Easier)**

```cmd
REM Double-click: scripts\setup-employee.bat
REM Follow prompts to enter employee details
```

---

### Method 3: Group Policy Deployment (Enterprise)

**For Active Directory Environments**

1. **Prepare Network Share**
   ```
   Copy installer to: \\domain\NETLOGON\WFHAgent-Setup.exe
   ```

2. **Create GPO**
   ```
   Group Policy Management Console
   → Create new GPO: "WFH Agent Deployment"
   → Edit GPO
   ```

3. **Configure Startup Script**
   ```
   Computer Configuration
   → Policies
   → Windows Settings
   → Scripts (Startup/Shutdown)
   → Startup → Add
   → Script: \\domain\SYSVOL\domain\Policies\{GPO}\Machine\Scripts\Startup\gpo-deploy.ps1
   ```

4. **Link GPO to OU**
   ```
   Link to appropriate Organizational Unit
   Apply to all employee computers
   ```

---

### Method 4: SCCM/Intune Deployment (Enterprise)

**Microsoft Endpoint Manager**

1. **Package Application**
   ```
   Application Type: Windows Installer (.msi)
   Source: WFHAgent-Setup.exe
   Install Command: WFHAgent-Setup.exe /S
   ```

2. **Configure Detection Method**
   ```
   File: C:\Program Files\WFH Agent\WFH Agent.exe
   Version: >= 0.1.8
   ```

3. **Deploy to Collection**
   ```
   Required deployment to "All Workstations"
   Deadline: Immediate
   ```

4. **Run Configuration Script**
   ```
   Post-install script: deploy-client.ps1
   Parameters from Intune custom attributes
   ```

---

## 🔐 Security Considerations

### API Key Management

**Do NOT hardcode API key in installer!**

Options for secure distribution:

1. **Environment Variable (Current Method)**
   - Set via GPO/script
   - Stored in system environment
   - Accessible to all users on machine

2. **Azure Key Vault (Enterprise)**
   ```powershell
   $secret = Get-AzKeyVaultSecret -VaultName "company-keyvault" -Name "wfh-api-key"
   [System.Environment]::SetEnvironmentVariable("WFH_AGENT_API_KEY", $secret.SecretValueText, "Machine")
   ```

3. **Registry Encryption**
   ```powershell
   $encrypted = ConvertTo-SecureString $apiKey -AsPlainText -Force | ConvertFrom-SecureString
   Set-ItemProperty -Path "HKLM:\SOFTWARE\WFHAgent" -Name "ApiKey" -Value $encrypted
   ```

---

## 📊 Verification Steps

### 1. Check Application Running
```powershell
Get-Process | Where-Object {$_.ProcessName -like "*wfh*"}
# Should show: WFH Agent.exe, emp_monitor.exe
```

### 2. Verify Environment Variable
```powershell
[System.Environment]::GetEnvironmentVariable("WFH_AGENT_API_KEY", "Machine")
# Should output: b1jWosNKA3wA...
```

### 3. Test Server Connectivity
```powershell
Invoke-RestMethod -Uri "http://20.197.8.101:5050/health"
# Should return: {"status": "healthy", ...}
```

### 4. Check Data Syncing
```bash
# On server
sudo -u postgres psql -d employee_monitor -c "SELECT COUNT(*) FROM employee_monitor.heartbeat WHERE emp_id=18698;"
# Should show increasing count
```

### 5. Monitor Logs
```bash
# On server
sudo journalctl -u wfh-ingestion -f
# Should show: "Inserted X/X heartbeat records from emp_id=18698"
```

---

## 🐛 Troubleshooting

### Issue: App not syncing data

**Solution 1: Check API key**
```powershell
echo %WFH_AGENT_API_KEY%
# If empty, set it again
```

**Solution 2: Check config.json**
```json
{
  "ingestion": {
    "enabled": true,
    "mode": "api"
  }
}
```

**Solution 3: Restart app**
```powershell
Get-Process *wfh*, emp_monitor | Stop-Process -Force
Start-Process "C:\Program Files\WFH Agent\WFH Agent.exe"
```

### Issue: Cannot reach server

**Solution: Check firewall**
```powershell
Test-NetConnection -ComputerName 20.197.8.101 -Port 5050
```

**Solution: Add firewall rule**
```powershell
New-NetFirewallRule -DisplayName "WFH Agent" -Direction Outbound -Action Allow -RemoteAddress 20.197.8.101 -Protocol TCP -RemotePort 5050
```

### Issue: Employee ID not set

**Solution: Update config manually**
```json
{
  "emp_id": 18698,
  "emp_name": "Employee Name",
  "department": "Engineering"
}
```

---

## 📦 Uninstallation

### Remove Application
```
Control Panel → Programs → Uninstall WFH Agent
```

### Clean Environment Variable
```powershell
[System.Environment]::SetEnvironmentVariable("WFH_AGENT_API_KEY", $null, "Machine")
```

### Remove Data Files
```powershell
Remove-Item -Recurse -Force "C:\Users\*\AppData\Local\WFHAgent"
```

---

## 📞 Support

**IT Support Team**
- Email: it-support@fidelisgroup.in
- Documentation: https://github.com/chetan-fidelis/wfh-agent

**Server Admin**
- Server logs: `sudo journalctl -u wfh-ingestion -f`
- Database: `psql -d employee_monitor`
- API health: http://20.197.8.101:5050/health

---

## 🔄 Update Procedure

1. **Stop running application**
2. **Run new installer** (overwrites old version)
3. **Restart application**
4. **Verify version**: About → Version 0.1.8

Auto-update coming in v0.2.0!

