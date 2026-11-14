@echo off
title Install Rose
setlocal
echo This installs Rose, the version from github.com/iimKoala/Rose, for your Windows user.
echo It needs Python 3.11 or newer. If you have none, Python 3.13 is installed with winget.
echo.
set "PY="
py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
if not defined PY py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
if defined PY goto have_python
echo Installing Python 3.13...
winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PYEXE%" goto no_python
set PY="%PYEXE%"
:have_python
set "SCRIPT=%TEMP%\rose_update.py"
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/iimKoala/Rose/release/scripts/rose_update.py' -OutFile $env:SCRIPT"
if errorlevel 1 goto no_download
rem Anything given to this file goes on to the installer: a folder to install into, --no-shortcut for a trial
%PY% "%SCRIPT%" --install %*
if errorlevel 1 goto failed
echo.
echo Also needed: League of Legends, and LTK Manager (the mod tool Rose drives; Rose says so when it is missing).
echo If the original Rose is installed too, uninstall it or switch off its start with Windows:
echo the two must not run at once.
pause
exit /b 0

:no_python
echo Python could not be installed automatically.
echo Install Python 3.13 from python.org, then run this file again.
pause
exit /b 1

:no_download
echo The installer could not be downloaded. Check your internet connection and run this file again.
pause
exit /b 1

:failed
echo.
echo Rose was not installed. The reason is above.
pause
exit /b 1
