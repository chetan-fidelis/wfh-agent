@echo off
REM WFH Agent - Simple Employee Setup
REM Run as Administrator

echo ========================================
echo WFH Agent Employee Setup
echo ========================================
echo.

REM Prompt for employee details
set /p EMP_ID="Enter Employee ID: "
set /p EMP_NAME="Enter Employee Name: "
set /p DEPARTMENT="Enter Department: "

REM Set API Key (same for all employees)
set API_KEY=b1jWosNKA3wAWrxYSRGmkpDoEaVH0bwKFarLBleL4Oo
set SERVER_URL=http://20.197.8.101:5050

echo.
echo Configuring WFH Agent for:
echo   Employee: %EMP_NAME% (ID: %EMP_ID%)
echo   Department: %DEPARTMENT%
echo   Server: %SERVER_URL%
echo.

REM Run PowerShell deployment script
powershell.exe -ExecutionPolicy Bypass -File "%~dp0deploy-client.ps1" ^
    -EmployeeId %EMP_ID% ^
    -EmployeeName "%EMP_NAME%" ^
    -Department "%DEPARTMENT%" ^
    -ApiKey "%API_KEY%" ^
    -ServerUrl "%SERVER_URL%"

pause
