# Comobot Installer for Windows
# Usage: irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO = "musenming/comobot"
$INSTALL_DIR = "$env:LOCALAPPDATA\comobot"

function Write-Info { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Green }
function Write-Err  { param($msg) Write-Host "[comobot] ERROR: $msg" -ForegroundColor Red; exit 1 }

# ── Fetch latest release ─────────────────────────────────────────────────────
Write-Info "Comobot Installer"
Write-Host ""

Write-Info "Fetching latest release info..."
try {
    $release = Invoke-RestMethod "https://api.github.com/repos/$REPO/releases/latest"
} catch {
    Write-Err "Failed to fetch release info. Check your network connection."
}

$asset = $release.assets | Where-Object { $_.name -like "*windows-x64*" } | Select-Object -First 1
if (-not $asset) {
    Write-Err "No Windows x64 release found."
}

$version = $release.tag_name -replace '^v', ''
$url = $asset.browser_download_url
Write-Info "Found comobot v$version for windows-x64"

# ── Download and extract ─────────────────────────────────────────────────────
$tmpDir = Join-Path $env:TEMP "comobot-install-$(Get-Random)"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$archive = Join-Path $tmpDir "comobot.tar.gz"

Write-Info "Downloading $($asset.name)..."
try {
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
} catch {
    Write-Err "Download failed: $_"
}

Write-Info "Extracting..."
tar -xzf $archive -C $tmpDir
if (-not $?) {
    Write-Err "Extraction failed."
}

# ── Install binary ───────────────────────────────────────────────────────────
if (-not (Test-Path $INSTALL_DIR)) {
    New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
}

$binarySrc = Join-Path $tmpDir "comobot\comobot.exe"
if (-not (Test-Path $binarySrc)) {
    Write-Err "Unexpected archive structure. Expected comobot\comobot.exe inside the tarball."
}

Copy-Item $binarySrc (Join-Path $INSTALL_DIR "comobot.exe") -Force
Write-Info "Installed to $INSTALL_DIR\comobot.exe"

# Clean up temp
Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue

# ── Add to user PATH ─────────────────────────────────────────────────────────
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$INSTALL_DIR*") {
    [Environment]::SetEnvironmentVariable("Path", "$INSTALL_DIR;$userPath", "User")
    Write-Info "Added $INSTALL_DIR to user PATH"
}

# ── Verify ────────────────────────────────────────────────────────────────────
$env:Path = "$INSTALL_DIR;$env:Path"
try {
    $ver = & (Join-Path $INSTALL_DIR "comobot.exe") --version 2>&1
    Write-OK "Comobot installed successfully! Version: $ver"
} catch {
    Write-OK "Comobot installed successfully! Version: $version"
}

Write-Host "  Run 'comobot --help' to get started."
Write-Host "  Please restart your terminal for PATH changes to take effect."
