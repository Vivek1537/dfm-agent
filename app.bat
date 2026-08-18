@echo off
REM Double-click this file to start the project on Windows.
REM It runs app.ps1 with an execution-policy bypass scoped to this one process,
REM so the machine's global PowerShell policy is not changed.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app.ps1"
