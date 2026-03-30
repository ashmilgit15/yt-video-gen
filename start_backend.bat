@echo off
set "PATH=C:\Apps\Portable\ffmpeg\ffmpeg-8.0.1-essentials_build\bin;%PATH%"
echo Running from directory: %cd%
cd /d "%~dp0\backend"
echo Changed to directory: %cd%
echo Checking for Python executable in venv...
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment Python not found. Did the installation fail?
    pause
    exit /b 1
)
echo Starting Backend Server...
venv\Scripts\python.exe main.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] The backend failed to start.
)
pause
