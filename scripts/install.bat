@echo off
:: Comobot Installer - Windows Batch Entry Point
:: Double-click or run as Administrator for best results
echo.
echo   Comobot Installer
echo   =================
echo.

:: Check if PowerShell is available
where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: PowerShell is required but not found.
    echo Please install PowerShell 5.1+ and try again.
    pause
    exit /b 1
)

:: Run the PowerShell installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& { $s = '%~dp0install.ps1'; if (Test-Path $s) { & $s } else { irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex } }"

if errorlevel 1 (
    echo.
    echo Installation failed. Please check the error messages above.
    pause
    exit /b 1
)

pause
