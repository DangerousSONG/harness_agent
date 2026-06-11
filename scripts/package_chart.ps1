param(
    [string]$ChartDir = ".\chart",
    [string]$OutputDir = ".\artifacts"
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

Write-Host "Packaging Helm chart..." -ForegroundColor Cyan

$helm = Get-Command helm -ErrorAction SilentlyContinue
if ($null -eq $helm) {
    Fail "Helm not found. Please install Helm first."
}

if (-not (Test-Path $ChartDir)) {
    Fail "Chart directory not found: $ChartDir"
}

$chartYaml = Join-Path $ChartDir "Chart.yaml"
$valuesYaml = Join-Path $ChartDir "values.yaml"

if (-not (Test-Path $chartYaml)) {
    Fail "Chart.yaml not found: $chartYaml"
}

if (-not (Test-Path $valuesYaml)) {
    Fail "values.yaml not found: $valuesYaml"
}

$chartLines = Get-Content $chartYaml

$nameLine = $chartLines | Where-Object { $_ -match "^\s*name\s*:" } | Select-Object -First 1
$versionLine = $chartLines | Where-Object { $_ -match "^\s*version\s*:" } | Select-Object -First 1

if ([string]::IsNullOrWhiteSpace($nameLine)) {
    Fail "Chart.yaml missing name field."
}

if ([string]::IsNullOrWhiteSpace($versionLine)) {
    Fail "Chart.yaml missing version field."
}

$chartName = ($nameLine -replace "^\s*name\s*:\s*", "").Trim().Trim('"').Trim("'")
$chartVersion = ($versionLine -replace "^\s*version\s*:\s*", "").Trim().Trim('"').Trim("'")

if ([string]::IsNullOrWhiteSpace($chartName)) {
    Fail "Chart name is empty."
}

if ([string]::IsNullOrWhiteSpace($chartVersion)) {
    Fail "Chart version is empty."
}

Write-Host "Chart name: $chartName"
Write-Host "Chart version: $chartVersion"

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

helm package $ChartDir -d $OutputDir

if ($LASTEXITCODE -ne 0) {
    Fail "helm package failed. Exit code: $LASTEXITCODE"
}

$packagePath = Join-Path $OutputDir "$chartName-$chartVersion.tgz"

if (-not (Test-Path $packagePath)) {
    Fail "Chart package not found: $packagePath"
}

Write-Host "Chart package created successfully:" -ForegroundColor Green
Write-Host $packagePath -ForegroundColor Green
