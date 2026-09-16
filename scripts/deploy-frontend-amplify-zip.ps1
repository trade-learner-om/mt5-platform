param(
    [string]$AppId = $env:AMPLIFY_FOREX_APP_ID,
    [string]$Branch = $(if ($env:AMPLIFY_BRANCH) { $env:AMPLIFY_BRANCH } else { "main" }),
    [string]$Region = $env:AWS_REGION,
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendDir = Join-Path $repoRoot "apps\frontend-react"
$distDir = Join-Path $frontendDir "dist"
$zipPath = Join-Path $repoRoot "amplify-deploy.zip"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

Write-Step "Installing dependencies"
Push-Location $frontendDir
try {
    if (Test-Path "package-lock.json") {
        npm ci
    } else {
        npm install
    }

    Write-Step "Building production bundle"
    npm run build
} finally {
    Pop-Location
}

if (-not (Test-Path $distDir)) {
    throw "Build output not found: $distDir"
}

Write-Step "Creating deployment zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Push-Location $distDir
try {
    tar -a -c -f $zipPath *
} finally {
    Pop-Location
}

$zipSizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "Zip ready: $zipPath ($zipSizeMb MB)"

if ($BuildOnly) {
    Write-Host "Build-only mode. Upload this zip in Amplify Console (Deploy without Git -> drag and drop)." -ForegroundColor Yellow
    exit 0
}

if (-not $AppId) {
    Write-Host ""
    Write-Host "Set AMPLIFY_FOREX_APP_ID or pass -AppId to upload automatically." -ForegroundColor Yellow
    Write-Host "Manual upload: Amplify Console -> your app -> Deploy updates -> Drag and drop -> choose:" -ForegroundColor Yellow
    Write-Host "  $zipPath" -ForegroundColor White
    exit 0
}

$awsArgs = @("amplify", "create-deployment", "--app-id", $AppId, "--branch-name", $Branch, "--output", "json")
if ($Region) { $awsArgs += @("--region", $Region) }

Write-Step "Creating Amplify deployment job for app $AppId / branch $Branch"
$createJson = & aws @awsArgs
if ($LASTEXITCODE -ne 0) { throw "aws amplify create-deployment failed" }

$create = $createJson | ConvertFrom-Json
$jobId = $create.jobId
$uploadUrl = $create.zipUploadUrl
if (-not $jobId -or -not $uploadUrl) {
    throw "Unexpected create-deployment response: $createJson"
}

Write-Step "Uploading zip"
curl.exe -sS -X PUT -T $zipPath -H "Content-Type: application/zip" $uploadUrl
if ($LASTEXITCODE -ne 0) { throw "Zip upload failed" }

$startArgs = @("amplify", "start-deployment", "--app-id", $AppId, "--branch-name", $Branch, "--job-id", $jobId)
if ($Region) { $startArgs += @("--region", $Region) }

Write-Step "Starting deployment job $jobId"
& aws @startArgs
if ($LASTEXITCODE -ne 0) { throw "aws amplify start-deployment failed" }

Write-Host ""
Write-Host "Deployment started. Monitor in AWS Amplify console." -ForegroundColor Green
