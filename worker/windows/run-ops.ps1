<#
.SYNOPSIS
  Keeps the job runner (python -m ops.runner) running on the counting machine, beside the worker.

.DESCRIPTION
  Started at boot by the scheduled task "milk-ops" (account SYSTEM). The runner carries out what a team admin asks
  on the website's Model page: it rewrites releases\live.json and restarts the task "milk-worker". When it exits,
  it is started again after RestartSeconds. Its output goes to logs\ops-yyyy-MM-dd.log (one file per day).

  SYSTEM has no AWS profile of its own, so the script points the AWS SDK at the profile files of the machine's
  user. The runner uses its own Python environment (.venv-ops: boto3 only); it never touches the worker's .venv.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File worker\windows\run-ops.ps1 -Root C:\Users\huyho\Datagent
#>
param(
    [string]$Root = "C:\Users\huyho\Datagent",
    [string]$Camera = "CAM-S01-A",
    [string]$StoreCode = "S01",
    [string]$AwsHome = "C:\Users\huyho\.aws",
    [string]$AwsProfile = "milk",
    [int]$RestartSeconds = 30,
    [int]$KeepLogDays = 30
)

$ErrorActionPreference = "Continue"   # the runner logs to stderr; Stop would end the loop on its first line
$python = Join-Path $Root ".venv-ops\Scripts\python.exe"
$repo = Join-Path $Root "milk_demo"
$logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $logs | Out-Null

$env:AWS_SHARED_CREDENTIALS_FILE = Join-Path $AwsHome "credentials"
$env:AWS_CONFIG_FILE = Join-Path $AwsHome "config"
$env:AWS_PROFILE = $AwsProfile
$env:PYTHONUNBUFFERED = "1"

$script:day = ""
function Write-OpsLog([string]$line) {
    $today = "{0:yyyy-MM-dd}" -f (Get-Date)
    if ($today -ne $script:day) {
        $script:day = $today
        Get-ChildItem $logs -Filter "ops-*.log" |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepLogDays) } |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
    Add-Content -LiteralPath (Join-Path $logs "ops-$today.log") -Value $line -Encoding UTF8
}

Set-Location $repo
while ($true) {
    Write-OpsLog ("{0:yyyy-MM-dd HH:mm:ss} [supervisor] starting the job runner for {1}" -f (Get-Date), $Camera)
    # 2>&1 inside cmd keeps stderr out of PowerShell's error stream
    cmd /c "`"$python`" -m ops.runner --root `"$Root`" --camera $Camera --store-code $StoreCode 2>&1" |
        ForEach-Object { Write-OpsLog "$_" }
    Write-OpsLog ("{0:yyyy-MM-dd HH:mm:ss} [supervisor] job runner exited with code {1}; restarting in {2} s" -f (Get-Date), $LASTEXITCODE, $RestartSeconds)
    Start-Sleep -Seconds $RestartSeconds
}
