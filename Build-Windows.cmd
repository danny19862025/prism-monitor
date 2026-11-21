@echo off
rem Test and build dist\PrismMonitor\, dist\PrismMonitor-windows.zip and, with Inno Setup 6,
rem dist\PrismMonitor-Setup-<version>.exe.
setlocal
cd /d "%~dp0"
call Setup-Windows.cmd
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
set QT_QPA_PLATFORM=offscreen
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
set QT_QPA_PLATFORM=
".venv\Scripts\python.exe" build.py
if errorlevel 1 goto failed
echo Built Prism Monitor. See the dist folder.
pause
exit /b 0
:failed
echo Build failed. Read the error above before trying again.
pause
exit /b 1
