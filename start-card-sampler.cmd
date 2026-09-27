@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-card-sampler.ps1"
if errorlevel 1 (
  echo.
  echo Card sampler did not exit normally. Press any key to close this window.
  pause >nul
)
