@echo off
title Swarm Job Search Engine - Launcher
color 0A

echo =======================================================
echo    🚀 SWARM JOB SEARCH ENGINE - 1-CLICK LAUNCHER
echo =======================================================
echo.

:: Navigate to the directory of this batch script
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

:: Check and install dependencies
echo [*] Checking dependencies...
pip install -r requirements.txt --quiet

:: Check for .env file
if not exist ".env" (
    echo [WARNING] No .env file found!
    echo Creating sample .env file...
    (
        echo # Add your API keys below (Optional: Engine will use Smart Heuristics if omitted^)
        echo GROQ_API_KEY=
        echo GEMINI_API_KEY=
        echo ENABLE_DASHBOARD=false
    ) > .env
)

echo.
echo =======================================================
echo  Starting Swarm Engine... (Press Ctrl+C to stop)
echo =======================================================
echo.

:: Run the engine
python main.py

echo.
echo Engine stopped.
pause
