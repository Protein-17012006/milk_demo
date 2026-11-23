<#
.SYNOPSIS
  Keeps the counting worker running on a Windows GPU machine, as milk-worker.service does on Linux.

.DESCRIPTION
  Started at boot by the scheduled task "milk-worker" (account SYSTEM). The worker runs at below-normal
  priority (like nice 10). When it exits, it is started again after RestartSeconds. Its output goes to
  logs\worker-yyyy-MM-dd.log (one file per day). Log files older than KeepLogDays are removed.

  winget installs ffmpeg under the profile of the user who ran it, which is not on SYSTEM's PATH, so the
  script finds ffmpeg itself unless -FfmpegDir is given.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File worker\windows\run-worker.ps1 -Root C:\Users\huyho\Datagent
#>
param(
    [string]$Root = "C:\Users\huyho\Datagent",
    [string]$FfmpegDir = "",
    [int]$RestartSeconds = 5,
    [int]$KeepLogDays = 14
)

$ErrorActionPreference = "Continue"   # the worker logs to stderr; Stop would end the loop on its first line
$python = Join-Path $Root ".venv\Scripts\python.exe"
$envFile = Join-Path $Root "worker.env"
$server = Join-Path $Root "milk_demo\server"
$logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $logs | Out-Null

if (-not $FfmpegDir) {
    $found = Get-ChildItem "C:\Users\*\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe" `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $FfmpegDir = $found.DirectoryName }
}
if ($FfmpegDir) { $env:PATH = "$FfmpegDir;$env:PATH" }
$env:PYTHONUNBUFFERED = "1"

$script:day = ""
function Write-WorkerLog([string]$line) {
    $today = "{0:yyyy-MM-dd}" -f (Get-Date)
    if ($today -ne $script:day) {
        $script:day = $today
        Get-ChildItem $logs -Filter "worker-*.log" |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepLogDays) } |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
    Add-Content -LiteralPath (Join-Path $logs "worker-$today.log") -Value $line -Encoding UTF8
}

Set-Location $server
while ($true) {
    Write-WorkerLog ("{0:yyyy-MM-dd HH:mm:ss} [supervisor] starting the worker; ffmpeg from {1}" -f (Get-Date), $(if ($FfmpegDir) { $FfmpegDir } else { "PATH" }))
    # start /belownormal /wait keeps the priority low and waits; 2>&1 inside cmd keeps stderr out of PowerShell's error stream
    cmd /c "start `"`" /belownormal /b /wait `"$python`" -m milk.counter --env `"$envFile`" 2>&1" |
        ForEach-Object { Write-WorkerLog "$_" }
    Write-WorkerLog ("{0:yyyy-MM-dd HH:mm:ss} [supervisor] worker exited with code {1}; restarting in {2} s" -f (Get-Date), $LASTEXITCODE, $RestartSeconds)
    Start-Sleep -Seconds $RestartSeconds
}
