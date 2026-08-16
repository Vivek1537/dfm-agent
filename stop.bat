@echo off
REM Double-click this file to stop the servers started by app.bat.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
pause
