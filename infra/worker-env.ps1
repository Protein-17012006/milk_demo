<#
.SYNOPSIS
  Writes worker.env for a counting worker on a GPU machine, from the stack outputs and SSM. The file holds
  secrets: send it privately and never commit it. It writes every key the worker uses, so a regenerated file
  keeps sampled counting (MILK_SAMPLE_*), the pinned hub certificate (MILK_STREAM_*), the Slide weights and the
  model version.

.EXAMPLE
  .\infra\worker-env.ps1 -OutFile $env:USERPROFILE\Desktop\worker.env

.EXAMPLE
  # HUYHOANG (Windows), as it runs since 23/11/2026
  .\infra\worker-env.ps1 -OutFile C:\temp\worker.env -AwsProfile default -Pipeline long+slide -WorkerName huyhoang-gpu `
      -LongDir C:/Users/huyho/Datagent/carton_recognition `
      -SlideWeights C:/Users/huyho/Datagent/slide_pilot/runs_v3/best.pt `
      -PersonModel C:/Users/huyho/Datagent/yolo/yolo26s.pt `
      -Yunet C:/Users/huyho/Datagent/ingest_bench/data/models/face_detection_yunet_2023mar.onnx `
      -ModelVersion long-2026-10-13+slide-v3 -StreamCaFile C:/Users/huyho/Datagent/hub-ingest.crt
#>
param(
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$CameraPath = "cam-s01-a",
    [string]$Pipeline = "null",
    [string]$LongDir = "",
    [string]$SlideWeights = "",
    [string]$ModelVersion = "",
    [string]$PersonModel = "./models/yolo26s.pt",
    [string]$Yunet = "./models/face_detection_yunet_2023mar.onnx",
    [string]$Device = "cuda",
    [string]$Decode = "keyframes",
    [string]$WorkerName = "gpu-worker",
    # The hub's self-signed RTSPS certificate, for workers whose ffmpeg checks it (ffmpeg 9 on Windows)
    [string]$StreamCaFile = "",
    [string]$StreamTlsName = "milk-demo-ingest",
    # Read the stream for SampleForSeconds every SampleEverySeconds; 0 counts continuously (demo days)
    [int]$SampleEverySeconds = 300,
    [int]$SampleForSeconds = 30,
    [string]$AwsProfile = "milk",
    [string]$Region = "ap-southeast-1",
    [string]$Project = "milk-demo"
)

. "$PSScriptRoot\common.ps1"
$script:AwsProfile = $AwsProfile
$script:Region = $Region

function Get-Secret([string]$Name) {
    return Invoke-Aws ssm get-parameter --name "/$Project/$Name" --with-decryption --query Parameter.Value --output text
}

$ip = Get-StackOutput "$Project-server" "IngestIp"
$hub = Get-StackOutput "$Project-server" "DashboardUrl"
$lines = @(
    "# Counting worker settings. Holds secrets: keep private, never commit.",
    "MILK_STREAM_URL=rtsps://$(Get-Secret 'stream/worker_user'):$(Get-Secret 'stream/worker_pass')@${ip}:8322/$CameraPath",
    "MILK_HUB_URL=$hub",
    "MILK_INTERNAL_TOKEN=$(Get-Secret 'web/internal_token')",
    "MILK_STORE_ID=DEMO-S01",
    "MILK_STORE_CODE=S01",
    "MILK_CAMERA_ID=CAM-S01-A",
    "MILK_CAPTURE_SOURCE=CCTV",
    "MILK_PIPELINE=$Pipeline",
    "MILK_LONG_DIR=$LongDir",
    "MILK_SLIDE_WEIGHTS=$SlideWeights",
    "MILK_MODEL_VERSION=$ModelVersion",
    "MILK_YUNET=$Yunet",
    "MILK_PERSON_MODEL=$PersonModel",
    "MILK_DEVICE=$Device",
    "MILK_DECODE=$Decode",
    "MILK_MAX_FPS=4",
    "MILK_PUBLISH_FPS=3",
    "MILK_DISPLAY_MAX_W=1280",
    "MILK_PERSIST_EVERY_S=10",
    "MILK_WORKER_NAME=$WorkerName",
    "MILK_STREAM_CA_FILE=$StreamCaFile",
    "MILK_STREAM_TLS_NAME=$StreamTlsName",
    "MILK_SAMPLE_EVERY_S=$SampleEverySeconds",
    "MILK_SAMPLE_FOR_S=$SampleForSeconds"
)
$lines | Out-File -FilePath $OutFile -Encoding ascii
Write-Host "wrote $OutFile (contains secrets)"
