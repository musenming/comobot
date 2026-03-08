@echo off
:: Comobot - Windows Docker Launcher
:: Double-click to start Comobot
cd /d "%~dp0\.."

set PORT=18790

:: Check Docker
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop is not running.
    echo Please start Docker Desktop and try again.
    echo.
    echo Opening Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe" 2>nul || echo Could not open Docker Desktop automatically.
    echo Waiting for Docker to start...
    :wait_docker
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if errorlevel 1 goto wait_docker
)

echo Starting Comobot...
docker compose up -d

echo Waiting for Comobot to be ready...
:wait_ready
timeout /t 2 /nobreak >nul
curl -sf http://localhost:%PORT%/api/health >nul 2>&1
if errorlevel 1 goto wait_ready

echo.
echo Comobot is running! Opening browser...
start "" "http://localhost:%PORT%"
