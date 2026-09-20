@echo off
REM Double-click entry point. Forwards to start.ps1 without changing your
REM PowerShell execution policy permanently.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
