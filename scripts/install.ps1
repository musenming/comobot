# Comobot One-Click Installer for Windows
# Usage: irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO      = "musenming/comobot"
$PORT      = 18790
$INSTALL   = "$env:APPDATA\comobot"
$DATA      = "$env:USERPROFILE\.comobot"
$VENV      = "$INSTALL\.venv"

function Write-Info  { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Cyan   }
function Write-OK    { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Green  }
function Write-Warn  { param($msg) Write-Host "[comobot] $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "[comobot] ERROR: $msg" -ForegroundColor Red; exit 1 }

# ── OS version check ──────────────────────────────────────────────────────────
function Check-Windows {
    $build = [System.Environment]::OSVersion.Version.Build
    if ($build -lt 18362) {
        Write-Err "Windows 10 version 1903 (build 18362) or later is required. Current build: $build"
    }
    Write-Info "Windows build $build OK"
}

# ── winget helper ─────────────────────────────────────────────────────────────
function Install-Via-Winget {
    param($Id, $Name)
    $installed = winget list --id $Id 2>$null | Select-String $Id
    if ($installed) {
        Write-OK "$Name already installed"
        return
    }
    Write-Info "Installing $Name via winget..."
    winget install --id $Id --silent --accept-package-agreements --accept-source-agreements
}

# ── Python ────────────────────────────────────────────────────────────────────
function Ensure-Python {
    $python = $null
    foreach ($cmd in @("python3.12", "python3.11", "python3", "python")) {
        try {
            $ver = & $cmd -c "import sys; print(sys.version_info[:2])" 2>$null
            if ($ver -match "\(3, (1[1-9]|[2-9]\d)") {
                $python = $cmd; break
            }
        } catch {}
    }
    if (-not $python) {
        Install-Via-Winget "Python.Python.3.11" "Python 3.11"
        $python = "python"
    }
    Write-OK "Python: $(& $python --version)"
    return $python
}

# ── Node.js ───────────────────────────────────────────────────────────────────
function Ensure-Node {
    $ok = $false
    try {
        $ver = & node -e "console.log(parseInt(process.version.slice(1)))" 2>$null
        if ([int]$ver -ge 18) { $ok = $true }
    } catch {}
    if (-not $ok) {
        Install-Via-Winget "OpenJS.NodeJS.LTS" "Node.js LTS"
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    Write-OK "Node.js: $(node --version)"
}

# ── Download release ──────────────────────────────────────────────────────────
function Download-Release {
    Write-Info "Fetching latest release..."
    try {
        $rel = Invoke-RestMethod "https://api.github.com/repos/$REPO/releases/latest"
        $zipUrl = $rel.zipball_url
    } catch {
        $zipUrl = "https://github.com/$REPO/archive/refs/heads/main.zip"
        Write-Warn "No release found, using main branch"
    }
    $tmp = [System.IO.Path]::GetTempFileName() -replace "\.tmp$", ".zip"
    Write-Info "Downloading $zipUrl ..."
    Invoke-WebRequest $zipUrl -OutFile $tmp
    return $tmp
}

# ── Install ───────────────────────────────────────────────────────────────────
function Install-Comobot {
    param($ZipPath, $Python)
    Write-Info "Installing to $INSTALL ..."
    New-Item -ItemType Directory -Path $INSTALL -Force | Out-Null

    $tmp = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.IO.Path]::GetRandomFileName())
    Expand-Archive $ZipPath $tmp -Force
    $extracted = Get-ChildItem $tmp | Select-Object -First 1
    Copy-Item "$($extracted.FullName)\*" $INSTALL -Recurse -Force
    Remove-Item $tmp -Recurse -Force
    Remove-Item $ZipPath -Force

    Write-Info "Creating virtual environment..."
    & $Python -m venv $VENV
    & "$VENV\Scripts\pip" install --upgrade pip setuptools wheel -q
    & "$VENV\Scripts\pip" install -e $INSTALL -q
    Write-OK "Python dependencies installed"

    if (Test-Path "$INSTALL\web") {
        Write-Info "Building frontend..."
        Push-Location "$INSTALL\web"
        npm ci --silent
        npm run build --silent
        Pop-Location
        Write-OK "Frontend built"
    }

    New-Item -ItemType Directory -Path "$DATA\workspace" -Force | Out-Null
    Write-OK "Data directory: $DATA"
}

# ── Autostart registry ────────────────────────────────────────────────────────
function Setup-Autostart {
    $key = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    $cmd = "`"$VENV\Scripts\comobot.exe`" gateway"
    Set-ItemProperty -Path $key -Name "Comobot" -Value $cmd
    Write-OK "Autostart registered"
}

# ── Desktop shortcut ──────────────────────────────────────────────────────────
function Create-Shortcut {
    $desktop = [System.Environment]::GetFolderPath("Desktop")
    $lnk = "$desktop\Comobot.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $s = $wsh.CreateShortcut($lnk)
    $s.TargetPath = "http://localhost:$PORT"
    $s.Description = "Open Comobot"
    $s.Save()
    Write-OK "Desktop shortcut: $lnk"
}

# ── Start service ─────────────────────────────────────────────────────────────
function Start-Comobot {
    Write-Info "Starting Comobot gateway..."
    $logDir = $DATA
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    Start-Process -FilePath "$VENV\Scripts\comobot.exe" `
        -ArgumentList "gateway" `
        -RedirectStandardOutput "$logDir\gateway.log" `
        -RedirectStandardError "$logDir\gateway-error.log" `
        -NoNewWindow -PassThru | Out-Null
    Start-Sleep 2
    Write-OK "Gateway started"
}

# ── Main ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔═══════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Comobot Installer v1.0      ║" -ForegroundColor Cyan
Write-Host "  ╚═══════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

Check-Windows
$python = Ensure-Python
Ensure-Node
$zip = Download-Release
Install-Comobot $zip $python
Setup-Autostart
Create-Shortcut
Start-Comobot

Start-Process "http://localhost:$PORT"

Write-Host ""
Write-OK "Installation complete!"
Write-Host "  → Open http://localhost:$PORT to configure Comobot" -ForegroundColor Green
Write-Host "  → Data stored in $DATA" -ForegroundColor Green
Write-Host ""
