@echo off
title Rose
rem Starts this copy of Rose from its source, after bringing it up to date from GitHub (scripts\rose_update.py).
rem Rose needs administrator rights: it switches the League client's plugin loader on.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
tasklist /FI "IMAGENAME eq Rose.exe" /NH | find /I "Rose.exe" >nul
if not errorlevel 1 (
    echo Closing the other Rose ^(Rose.exe^): the two must not run at once...
    taskkill /IM Rose.exe /F >nul
)
".venv\Scripts\python.exe" scripts\rose_update.py
echo Starting Rose. Keep this window open; close it to stop Rose.
".venv\Scripts\python.exe" main.py
:ended
rem Everything above this line must stay byte for byte as it is: an update replaces this file while it runs,
rem and cmd reads on from where it was. New lines go below.
rem Rose asked to be started again (an update downloaded while it ran, main\self_update.py): the update is
rem installed and Rose starts again in this window.
if exist ".rose-restart" goto again
pause
exit /b
:again
del ".rose-restart" >nul 2>&1
".venv\Scripts\python.exe" scripts\rose_update.py
echo Starting Rose. Keep this window open; close it to stop Rose.
".venv\Scripts\python.exe" main.py
goto ended
