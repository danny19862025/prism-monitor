@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto missing_python
set "PM_PYTHON="
for %%V in (3.12 3.13 3.14) do (
  if not defined PM_PYTHON (
    py -%%V -c "import struct; assert struct.calcsize('P') == 8" >nul 2>nul
    if not errorlevel 1 set "PM_PYTHON=-%%V"
  )
)
if not defined PM_PYTHON goto missing_python
if not exist ".venv\Scripts\python.exe" (
  py %PM_PYTHON% -m venv .venv
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\fetch_presentmon.py
if errorlevel 1 exit /b 1
echo Setup complete.
exit /b 0
:missing_python
echo Install 64-bit Python 3.12, 3.13 or 3.14 from https://www.python.org/downloads/windows/
echo Include the Python launcher, then run this file again.
exit /b 1
