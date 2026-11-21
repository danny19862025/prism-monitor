@echo off
rem Start Prism Monitor from source (standard user; no administrator rights needed).
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe call Setup-Windows.cmd
if errorlevel 1 exit /b 1
start "" .venv\Scripts\pythonw.exe monitor_main.py %*
