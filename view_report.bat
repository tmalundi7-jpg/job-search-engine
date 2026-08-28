@echo off
title Swarm Job Matches - Live Report
color 0B

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python view_reports.py

pause
