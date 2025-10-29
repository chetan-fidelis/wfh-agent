# Generate latest.yml for GitHub release
# This file is required for electron-updater to detect new versions

param(
    [string]$Version = "0.1.17",
    [string]$DistFolder = "dist"
)

Write-Host "Generating latest.yml for version $Version..." -ForegroundColor Cyan
Write-Host ""

$exeFile = Join-Path $DistFolder "WFH-Agent-Setup-$Version.exe"
$blockmapFile = "$exeFile.blockmap"

# Check if installer exists
if (-not (Test-Path $exeFile)) {
    Write-Error "Installer not found: $exeFile"
    Write-Host ""
    Write-Host "Please build the installer first:" -ForegroundColor Yellow
    Write-Host "  npm run build:electron" -ForegroundColor White
    exit 1
}

# Check if blockmap exists
if (-not (Test-Path $blockmapFile)) {
    Write-Warning "Blockmap file not found: $blockmapFile"
    Write-Host "Delta updates may not work without this file." -ForegroundColor Yellow
}

Write-Host "[OK] Found installer: $exeFile" -ForegroundColor Green

# Get SHA512 hash
Write-Host "Calculating SHA512 hash..." -ForegroundColor Cyan
$hash = (Get-FileHash -Path $exeFile -Algorithm SHA512).Hash.ToLower()
Write-Host "[OK] SHA512: $hash" -ForegroundColor Green

# Get file size
$size = (Get-Item $exeFile).Length
$sizeMB = [math]::Round($size/1MB, 2)
Write-Host "[OK] Size: $size bytes ($sizeMB MB)" -ForegroundColor Green

# Get current date in ISO format
$releaseDate = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
Write-Host "[OK] Release date: $releaseDate" -ForegroundColor Green

Write-Host ""
Write-Host "Generating latest.yml..." -ForegroundColor Cyan

# Generate latest.yml content
$yaml = @"
version: $Version
files:
  - url: WFH-Agent-Setup-$Version.exe
    sha512: $hash
    size: $size
path: WFH-Agent-Setup-$Version.exe
sha512: $hash
releaseDate: '$releaseDate'
"@

# Save to file
$outputFile = Join-Path $DistFolder "latest.yml"
$yaml | Out-File -FilePath $outputFile -Encoding UTF8 -NoNewline

Write-Host "[OK] Generated: $outputFile" -ForegroundColor Green
Write-Host ""

# Display the content
Write-Host "Content of latest.yml:" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor DarkGray
Write-Host $yaml -ForegroundColor White
Write-Host "----------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# Next steps
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Go to: https://github.com/chetan-fidelis/wfh-agent/releases/tag/v$Version" -ForegroundColor White
Write-Host "2. Click 'Edit release'" -ForegroundColor White
Write-Host "3. Drag and drop '$outputFile' to the assets section" -ForegroundColor White
Write-Host "4. Click 'Update release'" -ForegroundColor White
Write-Host ""
Write-Host "After uploading, verify the file is accessible at:" -ForegroundColor Yellow
Write-Host "https://github.com/chetan-fidelis/wfh-agent/releases/download/v$Version/latest.yml" -ForegroundColor White
Write-Host ""

# Verify blockmap
if (Test-Path $blockmapFile) {
    Write-Host "[OK] Blockmap file found - delta updates will work" -ForegroundColor Green
    Write-Host "  Also upload: $(Split-Path $blockmapFile -Leaf)" -ForegroundColor White
} else {
    Write-Host "[WARNING] Blockmap file missing - users will download full installer" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done! [OK]" -ForegroundColor Green
