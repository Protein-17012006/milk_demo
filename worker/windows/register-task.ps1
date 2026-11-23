<#
.SYNOPSIS
  Registers the scheduled task "milk-worker" that runs run-worker.ps1 at boot as SYSTEM. Run once, elevated.

.DESCRIPTION
  SYSTEM needs no stored password and runs before anyone signs in. Only one instance runs at a time
  (IgnoreNew), so the camera never gets two workers from this machine. -Start also starts it now: only do that
  after the worker on any other machine for the same camera has been stopped.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File worker\windows\register-task.ps1 -Root C:\Users\huyho\Datagent
#>
param(
    [string]$Root = "C:\Users\huyho\Datagent",
    [switch]$Start
)
$ErrorActionPreference = "Stop"
$script = Join-Path $Root "milk_demo\worker\windows\run-worker.ps1"
if (-not (Test-Path $script)) { throw "not found: $script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Root `"$Root`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "milk-worker" -Action $action -Trigger $trigger -Principal $principal `
    -Settings $settings -Force | Out-Null
if ($Start) { Start-ScheduledTask -TaskName "milk-worker" }
Get-ScheduledTask -TaskName "milk-worker" | Select-Object TaskName, State
