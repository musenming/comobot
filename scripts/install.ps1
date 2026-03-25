# Comobot Installer for Windows
# Usage: irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO = "musenming/comobot"
$INSTALL_DIR = "$env:LOCALAPPDATA\comobot\bin"
$DATA_DIR = "$env:USERPROFILE\.comobot"

function Write-Info { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "[comobot] ERROR: $msg" -ForegroundColor Red; exit 1 }

# ── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Info "Comobot Installer"
Write-Host ""

# ── Platform detection ───────────────────────────────────────────────────────
$arch = if ([Environment]::Is64BitOperatingSystem) {
    if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
} else {
    Write-Err "32-bit systems are not supported."
}
$TARGET = "windows-$arch"
Write-Info "Detected platform: $TARGET"

# ── Fetch latest release URL ────────────────────────────────────────────────
Write-Info "Fetching latest release info..."
$VERSION = $null

# Primary: resolve version via GitHub redirect (no API, no rate limit)
try {
    $response = Invoke-WebRequest -Uri "https://github.com/$REPO/releases/latest" `
        -MaximumRedirection 0 -ErrorAction SilentlyContinue -UseBasicParsing 2>$null
} catch {
    if ($_.Exception.Response.Headers.Location) {
        $redirectUrl = $_.Exception.Response.Headers.Location.ToString()
        if ($redirectUrl -match "/tag/v(.+)$") {
            $VERSION = $Matches[1]
        }
    }
}

# Fallback: use GitHub API
if (-not $VERSION) {
    try {
        $headers = @{}
        if ($env:GITHUB_TOKEN) {
            $headers["Authorization"] = "token $env:GITHUB_TOKEN"
        }
        $release = Invoke-RestMethod "https://api.github.com/repos/$REPO/releases/latest" -Headers $headers
        $VERSION = $release.tag_name -replace '^v', ''
    } catch {
        Write-Err "Failed to determine latest version. Visit https://github.com/$REPO/releases"
    }
}

if (-not $VERSION) {
    Write-Err "Failed to determine latest version. Visit https://github.com/$REPO/releases"
}

$ASSET_NAME = "comobot-$VERSION-$TARGET.tar.gz"
$DOWNLOAD_URL = "https://github.com/$REPO/releases/download/v$VERSION/$ASSET_NAME"
Write-Info "Found comobot v$VERSION for $TARGET"

# ── Download and extract ─────────────────────────────────────────────────────
$tmpDir = Join-Path $env:TEMP "comobot-install-$(Get-Random)"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$archive = Join-Path $tmpDir "comobot.tar.gz"

Write-Info "Downloading $ASSET_NAME..."
try {
    Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $archive -UseBasicParsing
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
$env:Path = "$INSTALL_DIR;$env:Path"

# ── Verify ───────────────────────────────────────────────────────────────────
$comobotExe = Join-Path $INSTALL_DIR "comobot.exe"
if (Test-Path $comobotExe) {
    try {
        $ver = & $comobotExe --version 2>&1
        Write-OK "Comobot installed successfully! Version: $ver"
    } catch {
        Write-OK "Comobot installed successfully! Version: $VERSION"
    }

    # Run onboard to generate config if not exists
    $configFile = Join-Path $DATA_DIR "config.json"
    if (-not (Test-Path $configFile)) {
        Write-Host ""
        Write-Info "Running initial setup (comobot onboard)..."
        try {
            & $comobotExe onboard
        } catch {
            Write-Warn "Onboard failed. You can run 'comobot onboard' manually later."
        }
    }

    Write-Host ""
    Write-Info "Run 'comobot gateway' to start the Web UI client"
    Write-Info "First-time users can configure Provider and Channel on the Setup page"
    Write-Host ""

    # Ask user whether to start comobot gateway now
    $answer = Read-Host "[comobot] Would you like to start comobot gateway now? (yes/no)"
    if ($answer -match "^[Yy]") {
        Write-Info "Starting comobot gateway..."
        & $comobotExe gateway
    } else {
        Write-OK "Installation complete! You can run 'comobot gateway' anytime to start the service."
    }
} else {
    Write-Warn "Installation completed but comobot.exe not found."
    Write-Host "  Please restart your terminal and try running: comobot --help"
}
