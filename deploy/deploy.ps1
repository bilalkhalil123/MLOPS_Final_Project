# PowerShell helper for local build/test deploy (GitHub Actions uses deploy/deploy.sh).
param(
    [switch]$SkipPush,
    [switch]$SkipDeploy,
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

$user = $env:DOCKER_USERNAME
$imageName = if ($env:DOCKER_IMAGE_NAME) { $env:DOCKER_IMAGE_NAME } else { "mlops-project" }
$tag = if ($env:DOCKER_IMAGE_TAG) { $env:DOCKER_IMAGE_TAG } else { "latest" }

if (-not $user) {
    Write-Error "Set DOCKER_USERNAME in .env"
}

$image = "${user}/${imageName}:${tag}"
Write-Host "Building $image"
docker build -f Dockerfile -t $image .

if ($BuildOnly) { exit 0 }

if (-not $SkipPush) {
    if (-not $env:DOCKER_PASSWORD) { Write-Error "Set DOCKER_PASSWORD in .env" }
    $env:DOCKER_PASSWORD | docker login -u $user --password-stdin
    docker push $image
}

if ($SkipDeploy) { exit 0 }

if (-not $env:EC2_HOST) {
    Write-Warning "EC2_HOST not set — skipping remote deploy."
    exit 0
}

$bash = Get-Command bash -ErrorAction SilentlyContinue
if ($bash) {
    if ($SkipPush) { $env:SKIP_PUSH = "1" }
    if ($SkipDeploy) { $env:SKIP_DEPLOY = "1" }
    & bash ./deploy/deploy.sh
} else {
    Write-Error "Install Git Bash/WSL to run deploy/deploy.sh, or deploy manually via SSH."
}
