@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  call Setup-Windows.cmd
  if errorlevel 1 goto failed
)
if not exist "vendor\presentmon" (
  ".venv\Scripts\python.exe" tools\fetch_presentmon.py
  if errorlevel 1 goto failed
)
start "" ".venv\Scripts\pythonw.exe" main.py %*
exit /b 0
:failed
echo Prism Monitor could not start. Read the error above.
pause
exit /b 1
