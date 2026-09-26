@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-autofgo.ps1"
if errorlevel 1 (
  echo.
  echo autoFgo did not exit normally. Press any key to close this window.
  pause >nul
)
