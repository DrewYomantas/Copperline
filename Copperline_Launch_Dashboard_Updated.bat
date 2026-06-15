@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Copperline - Lead Operations

echo.
echo  =========================================
echo   Copperline - Lead Operations
echo  =========================================
echo.

set "ROOT_DIR=%~dp0"
set "LEAD_ENGINE_DIR=%ROOT_DIR%lead_engine"

if not exist "%LEAD_ENGINE_DIR%\dashboard_server.py" (
    echo ERROR: Could not find dashboard_server.py in:
    echo   %LEAD_ENGINE_DIR%
    echo.
    echo Make sure this launcher lives next to the Copperline project folder.
    pause
    exit /b 1
)

cd /d "%LEAD_ENGINE_DIR%"

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "..\venv\Scripts\activate.bat" (
    call ..\venv\Scripts\activate.bat
) else (
    echo No .venv found. Using system Python.
)

REM Install Flask if missing
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing Flask...
    pip install flask -q
)

REM Load credentials from .env
if exist "%ROOT_DIR%.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT_DIR%.env") do (
        if not "%%A"=="" set %%A=%%B
    )
) else (
    echo WARNING: .env file not found. Credentials not loaded.
)

REM Prevent stale dual-server issue: kill anything already listening on port 5000
set "FOUND5000="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":5000 .*LISTENING"') do (
    if not "%%P"=="0" (
        set "FOUND5000=1"
        echo Stopping old process on port 5000 ^(PID %%P^)...
        taskkill /F /PID %%P >nul 2>&1
    )
)

if defined FOUND5000 (
    timeout /t 1 /nobreak >nul
)

echo  Starting dashboard server...
echo  Browser will open automatically at http://localhost:5000
echo.
echo  Press Ctrl+C to stop the server.
echo.

start "Copperline Browser" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"
python dashboard_server.py

pause
