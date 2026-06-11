# scripts/deploy_to_shuan_os.ps1
#
# End-to-end deploy through the 书安 OS Helm Marketplace API:
#
#   1. POST /api/v1/helm-marketplace/custom-charts/upload   (multipart .tgz)
#   2. GET  /api/v1/helm-marketplace/import-jobs/{id}       (poll until done)
#   3. POST /api/v1/helm-marketplace/releases/dry-run        (smoke test)
#   4. POST /api/v1/helm-marketplace/releases/install        (real apply)
#   5. GET  /api/v1/helm-marketplace/releases               (status + endpoints)
#
# The access token is read from $env:SHUAN_OS_TOKEN — never bake it
# into a script or commit.
#
# Usage examples:
#   $env:SHUAN_OS_TOKEN = "<accessToken>"
#   .\scripts\deploy_to_shuan_os.ps1
#   .\scripts\deploy_to_shuan_os.ps1 -ValuesYamlFile .\deploy-values.yaml
#   .\scripts\deploy_to_shuan_os.ps1 -ReleaseName harness-agent-staging -Namespace staging

[CmdletBinding()]
param(
    [string]$BaseUrl        = "http://10.12.111.133:49164",
    [string]$Token          = $env:SHUAN_OS_TOKEN,
    [string]$ChartTgz       = "artifacts\harness-agent-0.1.0.tgz",
    [string]$ReleaseName    = "harness-agent",
    [string]$Namespace      = "default",

    # Inline YAML body for ``valuesYaml`` (left empty by default).
    [string]$ValuesYaml     = "",

    # Convenience: point at a file and the script reads its content
    # into ``valuesYaml`` for you.
    [string]$ValuesYamlFile = "",

    [int]   $TimeoutSeconds = 300,
    [int]   $PollEvery      = 3
)

$ErrorActionPreference = "Stop"

# -- preflight -------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Error "请先设置 `$env:SHUAN_OS_TOKEN，再运行本脚本。"
    Write-Host "  例: `$env:SHUAN_OS_TOKEN = '<你的 accessToken>'" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path -LiteralPath $ChartTgz)) {
    Write-Error "Chart 包 '$ChartTgz' 不存在。先跑 .\scripts\package_chart.ps1。"
    exit 1
}

if ($ValuesYamlFile -and -not [string]::IsNullOrWhiteSpace($ValuesYamlFile)) {
    if (-not (Test-Path -LiteralPath $ValuesYamlFile)) {
        Write-Error "ValuesYamlFile '$ValuesYamlFile' 不存在。"
        exit 1
    }
    $ValuesYaml = Get-Content -LiteralPath $ValuesYamlFile -Raw
}

$BaseUrl = $BaseUrl.TrimEnd('/')
$headers = @{ "Authorization" = "Bearer $Token" }

# Helpers ------------------------------------------------------------

function Invoke-ShuanApi {
    param(
        [Parameter(Mandatory)] [string] $Method,
        [Parameter(Mandatory)] [string] $Path,
        [object] $Body,
        [string] $ContentType = "application/json"
    )
    $uri = "$BaseUrl$Path"
    $args = @{
        Uri         = $uri
        Method      = $Method
        Headers     = $headers
        ErrorAction = "Stop"
    }
    if ($null -ne $Body) {
        $args.Body        = if ($Body -is [string]) { $Body } else { ($Body | ConvertTo-Json -Depth 12) }
        $args.ContentType = $ContentType
    }
    try {
        return Invoke-RestMethod @args
    } catch {
        $msg = $_.Exception.Message
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $msg = "$msg`n  body: $($_.ErrorDetails.Message)"
        }
        Write-Error "$Method $uri 失败: $msg"
        throw
    }
}

function Upload-Chart {
    param([string] $TgzPath)

    # PowerShell 7+ has -Form; PS 5.1 does not, so we build the
    # multipart envelope by hand to keep this script portable.
    $major = $PSVersionTable.PSVersion.Major
    $uri   = "$BaseUrl/api/v1/helm-marketplace/custom-charts/upload"

    if ($major -ge 7) {
        $form = @{ file = Get-Item -LiteralPath $TgzPath }
        return Invoke-RestMethod -Uri $uri -Method Post -Headers $headers `
                                 -Form $form -ErrorAction Stop
    }

    # PS 5.1 fallback — build the multipart body manually.
    $boundary = "----PSFormBoundary{0:N}" -f [System.Guid]::NewGuid()
    $fileBytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $TgzPath))
    $fileName  = Split-Path -Leaf $TgzPath
    $LF        = "`r`n"

    $bodyLines = [System.Collections.ArrayList]@()
    [void] $bodyLines.Add("--$boundary")
    [void] $bodyLines.Add("Content-Disposition: form-data; name=`"file`"; filename=`"$fileName`"")
    [void] $bodyLines.Add("Content-Type: application/gzip")
    [void] $bodyLines.Add("")
    $head = ($bodyLines -join $LF) + $LF
    $tail = $LF + "--$boundary--" + $LF
    $headBytes = [System.Text.Encoding]::UTF8.GetBytes($head)
    $tailBytes = [System.Text.Encoding]::UTF8.GetBytes($tail)

    $stream = New-Object System.IO.MemoryStream
    $stream.Write($headBytes, 0, $headBytes.Length)
    $stream.Write($fileBytes, 0, $fileBytes.Length)
    $stream.Write($tailBytes, 0, $tailBytes.Length)
    $bodyBytes = $stream.ToArray()
    $stream.Dispose()

    return Invoke-RestMethod -Uri $uri -Method Post `
                             -Headers $headers `
                             -ContentType "multipart/form-data; boundary=$boundary" `
                             -Body $bodyBytes `
                             -ErrorAction Stop
}

function Get-FirstNonNull {
    param([object] $Object, [string[]] $Keys)
    foreach ($key in $Keys) {
        if ($null -ne $Object -and $null -ne $Object.$key -and "$($Object.$key)".Trim() -ne "") {
            return $Object.$key
        }
    }
    return $null
}

# -- 1) upload -------------------------------------------------------

Write-Host "→ 上传 Chart 包 …" -ForegroundColor Cyan
Write-Host "  $ChartTgz" -ForegroundColor DarkGray

$uploadResp = Upload-Chart -TgzPath $ChartTgz
$uploadJson = $uploadResp | ConvertTo-Json -Depth 8
Write-Host "  ← $uploadJson" -ForegroundColor DarkGray

$jobId = Get-FirstNonNull -Object $uploadResp -Keys @(
    "importJobId", "jobId", "id"
)
if ($null -eq $jobId -and $uploadResp.data) {
    $jobId = Get-FirstNonNull -Object $uploadResp.data -Keys @(
        "importJobId", "jobId", "id"
    )
}
if ([string]::IsNullOrWhiteSpace($jobId)) {
    Write-Error "Upload 返回里没找到 import job id。原始响应见上。"
    exit 1
}
Write-Host "  importJobId = $jobId" -ForegroundColor Green

# -- 2) poll ---------------------------------------------------------

Write-Host ""
Write-Host "→ 轮询导入任务 …" -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$importResult = $null

while ((Get-Date) -lt $deadline) {
    $job = Invoke-ShuanApi -Method "Get" `
                            -Path "/api/v1/helm-marketplace/import-jobs/$jobId"
    $status = Get-FirstNonNull -Object $job -Keys @("status", "state", "phase")
    if (-not $status -and $job.data) {
        $status = Get-FirstNonNull -Object $job.data -Keys @("status", "state", "phase")
    }
    Write-Host ("  status = {0}" -f $status) -ForegroundColor DarkGray

    if ($status -in @("completed", "succeeded", "success", "done")) {
        $importResult = if ($job.data) { $job.data } else { $job }
        break
    }
    if ($status -in @("failed", "error", "errored")) {
        Write-Error "import job $jobId 失败: $($job | ConvertTo-Json -Depth 6)"
        exit 1
    }

    Start-Sleep -Seconds $PollEvery
}

if ($null -eq $importResult) {
    Write-Error "import job $jobId 在 ${TimeoutSeconds}s 内未完成。"
    exit 1
}

# Extract repo + chart info. Real platform schemas often nest these
# under .repository / .chart objects; tolerate both flat and nested.
$repositoryName = Get-FirstNonNull -Object $importResult -Keys @("repositoryName", "repoName")
$repositoryUrl  = Get-FirstNonNull -Object $importResult -Keys @("repositoryUrl", "repoUrl")
$repositoryType = Get-FirstNonNull -Object $importResult -Keys @("repositoryType", "repoType")
$chartName      = Get-FirstNonNull -Object $importResult -Keys @("chartName", "name")
$chartVersion   = Get-FirstNonNull -Object $importResult -Keys @("version", "chartVersion")

if ($importResult.repository) {
    if (-not $repositoryName) { $repositoryName = $importResult.repository.name }
    if (-not $repositoryUrl)  { $repositoryUrl  = $importResult.repository.url }
    if (-not $repositoryType) { $repositoryType = $importResult.repository.type }
}
if ($importResult.chart) {
    if (-not $chartName)    { $chartName    = $importResult.chart.name }
    if (-not $chartVersion) { $chartVersion = $importResult.chart.version }
}

if (-not $repositoryType) { $repositoryType = "oci" }

Write-Host ""
Write-Host "✓ 导入完成" -ForegroundColor Green
Write-Host "  repositoryName = $repositoryName" -ForegroundColor Green
Write-Host "  repositoryUrl  = $repositoryUrl"  -ForegroundColor Green
Write-Host "  repositoryType = $repositoryType" -ForegroundColor Green
Write-Host "  chartName      = $chartName"      -ForegroundColor Green
Write-Host "  version        = $chartVersion"   -ForegroundColor Green

# -- 3) dry-run + install --------------------------------------------

$releasePayload = [ordered]@{
    repositoryName  = $repositoryName
    repositoryUrl   = $repositoryUrl
    repositoryType  = $repositoryType
    chartName       = $chartName
    version         = $chartVersion
    releaseName     = $ReleaseName
    namespace       = $Namespace
    valuesYaml      = $ValuesYaml
    timeoutSeconds  = $TimeoutSeconds
    force           = $true
}

Write-Host ""
Write-Host "→ Dry-run …" -ForegroundColor Cyan
$dryRun = Invoke-ShuanApi -Method "Post" `
                           -Path "/api/v1/helm-marketplace/releases/dry-run" `
                           -Body $releasePayload
Write-Host "  ← $($dryRun | ConvertTo-Json -Depth 6)" -ForegroundColor DarkGray
Write-Host "✓ Dry-run 通过" -ForegroundColor Green

Write-Host ""
Write-Host "→ Install …" -ForegroundColor Cyan
$installResp = Invoke-ShuanApi -Method "Post" `
                                -Path "/api/v1/helm-marketplace/releases/install" `
                                -Body $releasePayload
Write-Host "  ← $($installResp | ConvertTo-Json -Depth 6)" -ForegroundColor DarkGray
Write-Host "✓ Install 已提交" -ForegroundColor Green

# -- 4) list ---------------------------------------------------------

Write-Host ""
Write-Host "→ 当前 release 列表 …" -ForegroundColor Cyan
$releases = Invoke-ShuanApi -Method "Get" -Path "/api/v1/helm-marketplace/releases"

$entries = if ($releases -is [System.Collections.IEnumerable] -and $releases -isnot [string]) {
    @($releases)
} elseif ($releases.data) {
    @($releases.data)
} elseif ($releases.items) {
    @($releases.items)
} else {
    @($releases)
}

foreach ($r in $entries) {
    $name      = Get-FirstNonNull -Object $r -Keys @("releaseName", "name")
    $ns        = Get-FirstNonNull -Object $r -Keys @("namespace", "ns")
    $status    = Get-FirstNonNull -Object $r -Keys @("status", "phase", "state")
    $endpoint  = Get-FirstNonNull -Object $r -Keys @("endpoint", "endpoints", "accessUrl", "url")
    if (-not $name) { continue }
    Write-Host ("  - {0,-32} {1,-12} {2,-12} {3}" -f $name, $ns, $status, $endpoint)
}

Write-Host ""
Write-Host "✓ 部署完成。请在书安 OS 上查看 release '$ReleaseName' 的访问入口。" -ForegroundColor Green
