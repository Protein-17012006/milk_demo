<#
.SYNOPSIS
  Starts or stops the demo server. It also starts by itself every morning at 05:45 (stack
  milk-demo-server-start) and stops by itself every night at 23:00 (Asia/Ho_Chi_Minh).

.EXAMPLE
  .\infra\server-power.ps1 -Start
.EXAMPLE
  .\infra\server-power.ps1 -Stop
#>
param(
    [switch]$Start,
    [switch]$Stop,
    [string]$AwsProfile = "milk",
    [string]$Region = "ap-southeast-1",
    [string]$Project = "milk-demo"
)

. "$PSScriptRoot\common.ps1"
$script:AwsProfile = $AwsProfile
$script:Region = $Region

$instance = Get-StackOutput "$Project-server" "InstanceId"
if ($Start) {
    Invoke-Aws ec2 start-instances --instance-ids $instance | Out-Null
    Invoke-Aws ec2 wait instance-running --instance-ids $instance
    Write-Host "running; services are back in about a minute"
} elseif ($Stop) {
    Invoke-Aws ec2 stop-instances --instance-ids $instance | Out-Null
    Write-Host "stopping"
}
Invoke-Aws ec2 describe-instances --instance-ids $instance `
    --query "Reservations[0].Instances[0].[InstanceId,InstanceType,State.Name]" --output text | Out-Host
