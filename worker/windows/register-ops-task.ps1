<#
.SYNOPSIS
  Registers the scheduled task "milk-ops" that runs run-ops.ps1 at boot as SYSTEM. Run once, elevated.

.DESCRIPTION
  The job runner must be able to stop and start the task "milk-worker", which runs as SYSTEM, so it runs as SYSTEM
  too. Only one instance runs at a time (IgnoreNew). -Start also starts it now.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File worker\windows\register-ops-task.ps1 -Root C:\Users\huyho\Datagent -Start
#>
param(
    [string]$Root = "C:\Users\huyho\Datagent",
    [switch]$Start
)
$ErrorActionPreference = "Stop"
$script = Join-Path $Root "milk_demo\worker\windows\run-ops.ps1"
if (-not (Test-Path $script)) { throw "not found: $script" }
if (-not (Test-Path (Join-Path $Root ".venv-ops\Scripts\python.exe"))) { throw "not found: $Root\.venv-ops (python -m venv, then pip install boto3)" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Root `"$Root`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "milk-ops" -Action $action -Trigger $trigger -Principal $principal `
    -Settings $settings -Force | Out-Null
if ($Start) { Start-ScheduledTask -TaskName "milk-ops" }
Get-ScheduledTask -TaskName "milk-ops" | Select-Object TaskName, State
