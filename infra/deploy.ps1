<#
.SYNOPSIS
  Deploys the milk demo: secrets in SSM, storage stack, app release, server stack, morning start.

.EXAMPLE
  .\infra\deploy.ps1
  Hub only (t3.small): ingest, dashboard and storage. Counting runs on a GPU worker elsewhere.

.EXAMPLE
  .\infra\deploy.ps1 -InstanceType c7i.xlarge
  Bigger hub that can also count on its own CPU (set counter/local=on in SSM).

.EXAMPLE
  .\infra\deploy.ps1 -InstanceType g4dn.xlarge -RootVolumeGiB 100 `
    -ImageParam /aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-24.04/latest/ami-id
  GPU hub, once the G-instance quota is approved. Changing the image replaces the instance;
  the Elastic IP, CloudFront URL and data stay the same.
#>
param(
    [string]$AwsProfile = "milk",
    [string]$Region = "ap-southeast-1",
    [string]$Project = "milk-demo",
    [string]$InstanceType = "t3.small",
    [string]$ImageParam = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id",
    [int]$RootVolumeGiB = 60
)

. "$PSScriptRoot\common.ps1"
$script:AwsProfile = $AwsProfile
$script:Region = $Region
$root = Split-Path -Parent $PSScriptRoot

Write-Host "1/5 secrets in SSM Parameter Store (created once, never printed)"
$secrets = [ordered]@{
    "stream/publish_user"   = "pub" + (New-RandomHex 4)
    "stream/publish_pass"   = New-RandomHex 24
    "stream/worker_user"    = "wrk" + (New-RandomHex 4)
    "stream/worker_pass"    = New-RandomHex 24
    "stream/srt_passphrase" = New-RandomHex 16
    "web/password"          = New-RandomHex 8
    "web/secret"            = New-RandomHex 32
    "web/internal_token"    = New-RandomHex 32
    "web/origin_secret"     = New-RandomHex 32
}
foreach ($name in $secrets.Keys) {
    $full = "/$Project/$name"
    if (Test-AwsParameter $full) { continue }
    Invoke-Aws ssm put-parameter --name $full --type SecureString --value $secrets[$name] `
        --tags "Key=project,Value=$Project" | Out-Null
    Write-Host "   created $full"
}

Write-Host "2/5 storage stack"
Invoke-Aws cloudformation deploy --stack-name "$Project-base" --template-file "$root\infra\base.yaml" `
    --parameter-overrides "Project=$Project" --tags "project=$Project" --no-fail-on-empty-changeset | Out-Host
$bucket = Get-StackOutput "$Project-base" "BucketName"
$table = Get-StackOutput "$Project-base" "TableName"

Write-Host "3/5 app release to s3://$bucket/releases/"
& "$PSScriptRoot\release.ps1" -AwsProfile $AwsProfile -Region $Region -Project $Project -UploadOnly

Write-Host "4/5 server stack ($InstanceType)"
$prefixList = Invoke-Aws ec2 describe-managed-prefix-lists `
    --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" `
    --query "PrefixLists[0].PrefixListId" --output text
$originSecret = Invoke-Aws ssm get-parameter --name "/$Project/web/origin_secret" --with-decryption `
    --query Parameter.Value --output text
Invoke-Aws cloudformation deploy --stack-name "$Project-server" --template-file "$root\infra\server.yaml" `
    --capabilities CAPABILITY_IAM --tags "project=$Project" --no-fail-on-empty-changeset `
    --parameter-overrides "Project=$Project" "BucketName=$bucket" "TableName=$table" `
    "InstanceType=$InstanceType" "ImageId=$ImageParam" "RootVolumeGiB=$RootVolumeGiB" `
    "SsmPrefix=/$Project" "CloudFrontPrefixListId=$prefixList" "OriginSecret=$originSecret" | Out-Host

Write-Host "5/5 morning start (the server stack stops the hub at 23:00; this starts it at 05:45)"
$instance = Get-StackOutput "$Project-server" "InstanceId"
Invoke-Aws cloudformation deploy --stack-name "$Project-server-start" --template-file "$root\infra\server-start.yaml" `
    --capabilities CAPABILITY_IAM --tags "project=$Project" --no-fail-on-empty-changeset `
    --parameter-overrides "Project=$Project" "InstanceId=$instance" | Out-Host

Invoke-Aws cloudformation describe-stacks --stack-name "$Project-server" `
    --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table | Out-Host
Write-Host "First boot installs everything; allow about 10 minutes before the dashboard answers."
