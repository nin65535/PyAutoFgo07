$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendPackage = Join-Path $projectRoot 'frontend\package.json'
$viteProcess = $null
$consoleWindow = [IntPtr]::Zero

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

try {
    Set-Location -LiteralPath $projectRoot
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Python virtual environment is missing. Create .venv and install the backend first.'
    }
    if (-not (Test-Path -LiteralPath $frontendPackage -PathType Leaf)) {
        throw 'Frontend package.json is missing.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules') -PathType Container)) {
        throw 'Frontend dependencies are missing. Run npm --prefix frontend install first.'
    }
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $logDirectory = Join-Path $projectRoot '.autofgo\logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stdoutLog = Join-Path $logDirectory 'frontend-launch.out.log'
    $stderrLog = Join-Path $logDirectory 'frontend-launch.err.log'
    $consoleWindow = [AutoFgoConsoleWindow]::GetConsoleWindow()
    if ($consoleWindow -ne [IntPtr]::Zero) {
        [AutoFgoConsoleWindow]::ShowWindow($consoleWindow, 6) | Out-Null
    }
    $viteProcess = Start-Process -FilePath $npm -ArgumentList '--prefix', 'frontend', 'run', 'dev' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        if ($viteProcess.HasExited) {
            throw "Frontend exited during startup. See $stderrLog"
        }
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    if (-not $ready) {
        throw "Frontend did not become ready. See $stderrLog"
    }

    Write-Host 'Starting autoFgo. Close the dedicated Chrome window to exit.'
    & $python -m autofgo
    if ($LASTEXITCODE -ne 0) {
        throw "Backend exited with code $LASTEXITCODE."
    }
    exit 0
} catch {
    if ($consoleWindow -ne [IntPtr]::Zero) {
        [AutoFgoConsoleWindow]::ShowWindow($consoleWindow, 9) | Out-Null
        [AutoFgoConsoleWindow]::SetForegroundWindow($consoleWindow) | Out-Null
    }
    Write-Host "Startup or runtime error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($null -ne $viteProcess -and -not $viteProcess.HasExited) {
        try {
            & taskkill.exe /PID $viteProcess.Id /T /F 2>$null | Out-Null
        } catch {
            Write-Warning "Could not stop frontend process $($viteProcess.Id): $($_.Exception.Message)"
        }
    }
}
