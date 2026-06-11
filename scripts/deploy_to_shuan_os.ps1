param(
    [string]$BaseUrl = "http://10.12.111.133:49164",
    [string]$ChartTgz = ".\artifacts\harness-agent-0.1.0.tgz",
    [string]$ReleaseName = "harness-agent",
    [string]$Namespace = "default",
    [int]$TimeoutSeconds = 300,
    [string]$ValuesYamlFile = ""
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Read-Utf8File($Path) {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

function Parse-JsonObject($Text, $Label) {
    if ([string]::IsNullOrWhiteSpace($Text)) {
        Fail "$Label response is empty."
    }

    $trimmed = $Text.Trim()
    $start = $trimmed.IndexOf("{")
    $end = $trimmed.LastIndexOf("}")

    if ($start -lt 0 -or $end -lt 0 -or $end -le $start) {
        Write-Host "Raw $Label response:" -ForegroundColor Yellow
        Write-Host $Text
        Fail "$Label response does not contain a JSON object."
    }

    $json = $trimmed.Substring($start, $end - $start + 1)

    try {
        return $json | ConvertFrom-Json
    } catch {
        Write-Host "Raw $Label response:" -ForegroundColor Yellow
        Write-Host $json
        Fail "$Label response is not valid JSON: $($_.Exception.Message)"
    }
}

function Get-Data($Response) {
    if ($null -ne $Response.data) {
        return $Response.data
    }
    return $Response
}

function Invoke-JsonGet($Uri, $Token) {
    $headers = @{
        Authorization = "Bearer $Token"
    }

    try {
        return Invoke-RestMethod -Uri $Uri -Method Get -Headers $headers
    } catch {
        Fail "GET failed: $Uri ; $($_.Exception.Message)"
    }
}

function Invoke-JsonPost($Uri, $Token, $Payload) {
    $headers = @{
        Authorization = "Bearer $Token"
        "Content-Type" = "application/json"
    }

    $body = $Payload | ConvertTo-Json -Depth 50

    try {
        return Invoke-RestMethod -Uri $Uri -Method Post -Headers $headers -Body $body
    } catch {
        Fail "POST failed: $Uri ; $($_.Exception.Message)"
    }
}

function Upload-Chart($Uri, $Token, $ChartPath) {
    $fullPath = (Resolve-Path -LiteralPath $ChartPath).Path
    $responseFile = [System.IO.Path]::GetTempFileName()

    Write-Host "Uploading chart package: $ChartPath"

    try {
        $httpCode = & curl.exe -sS -X POST `
            $Uri `
            -H "Authorization: Bearer $Token" `
            -F "file=@$fullPath" `
            -o $responseFile `
            -w "%{http_code}"

        $curlExit = $LASTEXITCODE

        $raw = Read-Utf8File $responseFile

        if ($curlExit -ne 0) {
            Write-Host $raw -ForegroundColor Yellow
            Fail "Chart upload failed by curl.exe. Exit code: $curlExit"
        }

        if ([string]::IsNullOrWhiteSpace($httpCode)) {
            Write-Host $raw -ForegroundColor Yellow
            Fail "Chart upload did not return HTTP status code."
        }

        $statusCode = [int]$httpCode

        if ($statusCode -lt 200 -or $statusCode -ge 300) {
            Write-Host "HTTP status: $statusCode" -ForegroundColor Yellow
            Write-Host $raw -ForegroundColor Yellow
            Fail "Chart upload failed."
        }

        return Parse-JsonObject $raw "upload"
    } finally {
        Remove-Item $responseFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Deploying chart to Shuan OS Helm Marketplace..." -ForegroundColor Cyan

$Token = $env:SHUAN_OS_TOKEN

if ([string]::IsNullOrWhiteSpace($Token)) {
    Fail "SHUAN_OS_TOKEN is empty. Please run: `$env:SHUAN_OS_TOKEN='your access token'"
}

if (-not (Test-Path -LiteralPath $ChartTgz)) {
    Fail "Chart package not found: $ChartTgz"
}

$ValuesYaml = ""

if (-not [string]::IsNullOrWhiteSpace($ValuesYamlFile)) {
    if (-not (Test-Path -LiteralPath $ValuesYamlFile)) {
        Fail "Values yaml file not found: $ValuesYamlFile"
    }
    $ValuesYaml = Get-Content -LiteralPath $ValuesYamlFile -Raw
}

$UploadUri = "$BaseUrl/api/v1/helm-marketplace/custom-charts/upload"
$UploadResponse = Upload-Chart $UploadUri $Token $ChartTgz
$UploadData = Get-Data $UploadResponse

$JobId = $null

if ($null -ne $UploadData.id) {
    $JobId = $UploadData.id
} elseif ($null -ne $UploadData.jobId) {
    $JobId = $UploadData.jobId
} elseif ($null -ne $UploadData.importJobId) {
    $JobId = $UploadData.importJobId
}

if ([string]::IsNullOrWhiteSpace($JobId)) {
    Write-Host "Upload response:" -ForegroundColor Yellow
    $UploadResponse | ConvertTo-Json -Depth 50
    Fail "Cannot find import job id in upload response."
}

Write-Host "Import job id: $JobId" -ForegroundColor Green

$ImportResult = $null
$StartTime = Get-Date

while ($true) {
    Start-Sleep -Seconds 3

    $Elapsed = ((Get-Date) - $StartTime).TotalSeconds

    if ($Elapsed -gt $TimeoutSeconds) {
        Fail "Timed out waiting for import job completion."
    }

    $JobUri = "$BaseUrl/api/v1/helm-marketplace/import-jobs/$JobId"
    $JobResponse = Invoke-JsonGet $JobUri $Token
    $JobData = Get-Data $JobResponse

    $Status = $JobData.status
    $Stage = $JobData.stage
    $Progress = $JobData.progress

    Write-Host "Import job status: $Status stage=$Stage progress=$Progress"

    if ($Status -eq "completed" -or $Status -eq "succeeded" -or $Status -eq "success") {
        $ImportResult = $JobData
        break
    }

    if ($Status -eq "failed" -or $Status -eq "error") {
        Write-Host "Import job response:" -ForegroundColor Yellow
        $JobResponse | ConvertTo-Json -Depth 50
        Fail "Import job failed."
    }
}

if ($null -eq $ImportResult) {
    Fail "Import result is empty."
}

$RepositoryName = $ImportResult.repositoryName
$RepositoryUrl = $ImportResult.repositoryUrl
$RepositoryType = $ImportResult.repositoryType
$ChartName = $ImportResult.chartName
$Version = $ImportResult.version

if ([string]::IsNullOrWhiteSpace($RepositoryName) -and $null -ne $ImportResult.chart) {
    $RepositoryName = $ImportResult.chart.repositoryName
}
if ([string]::IsNullOrWhiteSpace($RepositoryUrl) -and $null -ne $ImportResult.chart) {
    $RepositoryUrl = $ImportResult.chart.repositoryUrl
}
if ([string]::IsNullOrWhiteSpace($RepositoryType) -and $null -ne $ImportResult.chart) {
    $RepositoryType = $ImportResult.chart.repositoryType
}
if ([string]::IsNullOrWhiteSpace($ChartName) -and $null -ne $ImportResult.chart) {
    $ChartName = $ImportResult.chart.name
}
if ([string]::IsNullOrWhiteSpace($Version) -and $null -ne $ImportResult.chart) {
    $Version = $ImportResult.chart.version
}

if ([string]::IsNullOrWhiteSpace($RepositoryType)) {
    $RepositoryType = "oci"
}
if ([string]::IsNullOrWhiteSpace($ChartName)) {
    $ChartName = "harness-agent"
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = "0.1.0"
}

if ([string]::IsNullOrWhiteSpace($RepositoryName) -or [string]::IsNullOrWhiteSpace($RepositoryUrl)) {
    Write-Host "Import result:" -ForegroundColor Yellow
    $ImportResult | ConvertTo-Json -Depth 50
    Fail "Missing repositoryName or repositoryUrl from import result."
}

Write-Host "Chart imported successfully." -ForegroundColor Green
Write-Host "Repository: $RepositoryName"
Write-Host "Repository URL: $RepositoryUrl"
Write-Host "Repository Type: $RepositoryType"
Write-Host "Chart: $ChartName"
Write-Host "Version: $Version"

$Payload = @{
    repositoryName = $RepositoryName
    repositoryUrl = $RepositoryUrl
    repositoryType = $RepositoryType
    chartName = $ChartName
    version = $Version
    releaseName = $ReleaseName
    namespace = $Namespace
    valuesYaml = $ValuesYaml
    timeoutSeconds = $TimeoutSeconds
    force = $true
}

Write-Host "Running dry-run..."
$DryRunResponse = Invoke-JsonPost "$BaseUrl/api/v1/helm-marketplace/releases/dry-run" $Token $Payload
Write-Host "Dry-run completed." -ForegroundColor Green

Write-Host "Installing release..."
$InstallResponse = Invoke-JsonPost "$BaseUrl/api/v1/helm-marketplace/releases/install" $Token $Payload
Write-Host "Install request completed." -ForegroundColor Green
$InstallResponse | ConvertTo-Json -Depth 50

Write-Host "Querying releases..."
try {
    $ReleaseResponse = Invoke-JsonGet "$BaseUrl/api/v1/helm-marketplace/releases" $Token
    $ReleaseResponse | ConvertTo-Json -Depth 50
} catch {
    Write-Host "Failed to query release list: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host "Done." -ForegroundColor Green
