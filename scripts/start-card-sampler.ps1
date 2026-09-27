$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AutoFgoSamplerConsoleWindow {
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr window);
}
'@

$consoleWindow = [AutoFgoSamplerConsoleWindow]::GetConsoleWindow()
try {
    Set-Location -LiteralPath $projectRoot
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Python virtual environment is missing. Follow the setup instructions in README.md.'
    }
    if ($consoleWindow -ne [IntPtr]::Zero) {
        [AutoFgoSamplerConsoleWindow]::ShowWindow($consoleWindow, 6) | Out-Null
    }

    & $python -m autofgo.sampler_main
    if ($LASTEXITCODE -ne 0) {
        throw "Card sampler exited with code $LASTEXITCODE."
    }
    exit 0
} catch {
    if ($consoleWindow -ne [IntPtr]::Zero) {
        [AutoFgoSamplerConsoleWindow]::ShowWindow($consoleWindow, 9) | Out-Null
        [AutoFgoSamplerConsoleWindow]::SetForegroundWindow($consoleWindow) | Out-Null
    }
    Write-Host "Startup or runtime error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
