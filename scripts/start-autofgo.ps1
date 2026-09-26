$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendIndex = Join-Path $projectRoot 'frontend\dist\index.html'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AutoFgoConsoleWindow {
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr window);
}
'@

$consoleWindow = [AutoFgoConsoleWindow]::GetConsoleWindow()
try {
    Set-Location -LiteralPath $projectRoot
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Python virtual environment is missing. Follow the setup instructions in README.md.'
    }
    if (-not (Test-Path -LiteralPath $frontendIndex -PathType Leaf)) {
        throw 'Built frontend is missing. Run npm --prefix frontend run build.'
    }

    $env:AUTOFGO_STATIC_DIRECTORY = Join-Path $projectRoot 'frontend\dist'
    if (-not $env:AUTOFGO_PORT) { $env:AUTOFGO_PORT = '8000' }
    $env:AUTOFGO_CHROME_APP_URL = "http://127.0.0.1:$env:AUTOFGO_PORT"
    if ($consoleWindow -ne [IntPtr]::Zero) {
        [AutoFgoConsoleWindow]::ShowWindow($consoleWindow, 6) | Out-Null
    }

    & $python -m autofgo
    if ($LASTEXITCODE -ne 0) {
        throw "Backend exited with code $LASTEXITCODE. See .autofgo/logs/autofgo.log."
    }
    exit 0
} catch {
    if ($consoleWindow -ne [IntPtr]::Zero) {
        [AutoFgoConsoleWindow]::ShowWindow($consoleWindow, 9) | Out-Null
        [AutoFgoConsoleWindow]::SetForegroundWindow($consoleWindow) | Out-Null
    }
    Write-Host "Startup or runtime error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
