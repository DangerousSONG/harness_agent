# scripts/package_chart.ps1
#
# Packages the Helm chart at .\chart into a .tgz the 书安 OS Helm
# Marketplace API can ingest. Output lands in .\artifacts.
#
# Usage:
#   .\scripts\package_chart.ps1
#
# Optional override:
#   .\scripts\package_chart.ps1 -ChartDir .\chart -OutDir .\artifacts

[CmdletBinding()]
param(
    [string]$ChartDir = "chart",
    [string]$OutDir   = "artifacts"
)

$ErrorActionPreference = "Stop"

# -- prerequisites ---------------------------------------------------

if (-not (Test-Path -LiteralPath (Join-Path $ChartDir "Chart.yaml"))) {
    Write-Error "Chart.yaml not found under '$ChartDir'. Run this script from the repo root."
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $ChartDir "values.yaml"))) {
    Write-Error "values.yaml not found under '$ChartDir'. Run this script from the repo root."
    exit 1
}

# Cheap Chart.yaml sanity check: must declare ``name`` and ``version``
# (the platform's import job rejects packages where either is empty).
$chartYaml = Get-Content -LiteralPath (Join-Path $ChartDir "Chart.yaml") -Raw
if ($chartYaml -notmatch "(?m)^\s*name\s*:\s*\S") {
    Write-Error "Chart.yaml is missing a non-empty 'name:' field."
    exit 1
}
if ($chartYaml -notmatch "(?m)^\s*version\s*:\s*\S") {
    Write-Error "Chart.yaml is missing a non-empty 'version:' field."
    exit 1
}

# Helm is mandatory. Don't silently shell out and hope for the best.
$helm = Get-Command helm -ErrorAction SilentlyContinue
if ($null -eq $helm) {
    Write-Error "未检测到 helm，请先安装 Helm，或在有 Helm 的机器上执行。"
    exit 1
}

# -- package ---------------------------------------------------------

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir | Out-Null
}

Write-Host "Packaging $ChartDir → $OutDir …" -ForegroundColor Cyan
$result = & helm package $ChartDir -d $OutDir 2>&1
$exit   = $LASTEXITCODE
$result | ForEach-Object { Write-Host $_ }

if ($exit -ne 0) {
    Write-Error "helm package 失败 (exit $exit). 见上方输出。"
    exit $exit
}

# Find the .tgz helm just emitted so we can echo it cleanly. helm
# names the file ``<name>-<version>.tgz`` so the most-recent .tgz in
# the out dir is the one we just produced.
$tgz = Get-ChildItem -LiteralPath $OutDir -Filter "*.tgz" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

if ($null -eq $tgz) {
    Write-Error "helm package returned 0 but no .tgz appeared in $OutDir."
    exit 1
}

Write-Host ""
Write-Host "✓ Chart packaged:" -ForegroundColor Green
Write-Host "  $($tgz.FullName)" -ForegroundColor Green
Write-Host ""
Write-Host "Next: upload + deploy with" -ForegroundColor Yellow
Write-Host "  `$env:SHUAN_OS_TOKEN=`"…`"" -ForegroundColor Yellow
Write-Host "  .\scripts\deploy_to_shuan_os.ps1" -ForegroundColor Yellow
