param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$TestReportStart = "2026-06-23"
$TestReportEnd = "2026-07-13"
$TestRankingDate = "2026-07-12"

$CurrentReportStart = "2026-07-14"
$CurrentReportEnd = "2026-07-27"
$CurrentRankingDate = "2026-07-26"

$ConfigPath = Join-Path $ProjectRoot "config\settings.json"
$OutputDir = Join-Path $ProjectRoot "data\output"
$RawDir = Join-Path $ProjectRoot "data\raw"
$ExtractionMetadataPath = Join-Path $ProjectRoot "data\local_app\extraction_metadata.json"
$WatchlistPath = Join-Path $ProjectRoot "data\local_app\watchlist.csv"
$FinalCsvPath = Join-Path $OutputDir "final_sg_market_scan_current_workflow.csv"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot "backups\controlled_live_test_$Timestamp"
$Results = [ordered]@{
    TokenAvailable = $false
    BackupCreated = $false
    TestPeriodSet = $false
    LiveWorkflowCompleted = $false
    ConfigRestored = $false
    FinalCsvExists = $false
    StarSailorsAppears = $false
    Sea6MetricsPresent = $false
    ExtractionMetadataUpdated = $false
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Copy-IfPresent {
    param(
        [string]$Source,
        [string]$Destination
    )
    if (Test-Path -LiteralPath $Source) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    }
}

function Read-JsonFile {
    param([string]$Path)
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Write-JsonFile {
    param(
        [string]$Path,
        [object]$Payload
    )
    $Payload | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Set-ReportPeriod {
    param(
        [string]$ReportStart,
        [string]$ReportEnd,
        [string]$RankingDate
    )
    $config = Read-JsonFile -Path $ConfigPath
    $config.report_start_date = $ReportStart
    $config.report_end_date = $ReportEnd
    $config.ranking_date = $RankingDate
    Write-JsonFile -Path $ConfigPath -Payload $config
}

function Get-MetadataRefreshValue {
    if (-not (Test-Path -LiteralPath $ExtractionMetadataPath)) {
        return ""
    }
    $metadata = Read-JsonFile -Path $ExtractionMetadataPath
    return [string]$metadata.last_successful_sensor_tower_refresh_at
}

function Get-CsvValue {
    param(
        [object]$Row,
        [string]$Field
    )
    $property = $Row.PSObject.Properties[$Field]
    if ($null -eq $property) {
        return ""
    }
    return [string]$property.Value
}

function Has-NonZeroValue {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    $cleaned = $Value.Trim().Replace(",", "").Replace("$", "")
    $number = 0.0
    if ([double]::TryParse($cleaned, [ref]$number)) {
        return $number -ne 0
    }
    return $true
}

function Test-FinalCsvContent {
    if (-not (Test-Path -LiteralPath $FinalCsvPath)) {
        return
    }

    $Results.FinalCsvExists = $true
    $rows = Import-Csv -LiteralPath $FinalCsvPath
    $starRows = @($rows | Where-Object {
        ((Get-CsvValue -Row $_ -Field "Game Title") -match "Star Sailors") -or
        ((Get-CsvValue -Row $_ -Field "English Display Title") -match "Star Sailors") -or
        ((Get-CsvValue -Row $_ -Field "Original Title") -match "Star Sailors")
    })

    if ($starRows.Count -gt 0) {
        $Results.StarSailorsAppears = $true
    }

    foreach ($row in $starRows) {
        $sgRevenue = Get-CsvValue -Row $row -Field "SG Gross Revenue"
        $topMarkets = Get-CsvValue -Row $row -Field "Top 3 Markets"

        if (Has-NonZeroValue -Value $sgRevenue) {
            $Results.Sea6MetricsPresent = $true
            return
        }

        if ($topMarkets -match "\$[\d,]+(\.\d+)?" -and $topMarkets -match "\d[\d,]*\s+DL") {
            $Results.Sea6MetricsPresent = $true
            return
        }
    }
}

function Print-Summary {
    Write-Host ""
    if ($ValidateOnly) {
        Write-Host "Existing output validation summary"
    }
    else {
        Write-Host "Controlled live Sensor Tower test summary"
        Write-Host "Backup folder: $BackupRoot"
    }
    Write-Host ""

    if ($ValidateOnly) {
        foreach ($key in @("FinalCsvExists", "StarSailorsAppears", "Sea6MetricsPresent", "ExtractionMetadataUpdated")) {
            $status = if ($Results[$key]) { "PASS" } else { "FAIL" }
            Write-Host ("{0}: {1}" -f $key, $status)
        }
    }
    else {
        foreach ($item in $Results.GetEnumerator()) {
            $status = if ($item.Value) { "PASS" } else { "FAIL" }
            Write-Host ("{0}: {1}" -f $item.Key, $status)
        }
    }

    Write-Host ""
    if ($Results.LiveWorkflowCompleted -and $Results.FinalCsvExists -and $Results.StarSailorsAppears -and $Results.Sea6MetricsPresent -and $Results.ExtractionMetadataUpdated) {
        Write-Host "Live workflow result: PASS - final CSV contains Star Sailors with SEA6 metrics."
    }
    elseif ($ValidateOnly -and $Results.FinalCsvExists -and $Results.StarSailorsAppears -and $Results.Sea6MetricsPresent) {
        Write-Host "Existing output validation: PASS - final CSV contains Star Sailors with SEA6 metrics."
    }
    else {
        Write-Host "Live workflow result: FAIL or incomplete - review failed checks above."
    }
    Write-Host "Token value was not printed."
}

if ($ValidateOnly) {
    Push-Location $ProjectRoot
    try {
        Write-Step "Validating existing outputs only"
        Test-FinalCsvContent
        $refreshAt = Get-MetadataRefreshValue
        if (-not [string]::IsNullOrWhiteSpace($refreshAt)) {
            $Results.ExtractionMetadataUpdated = $true
        }
        Print-Summary
    }
    finally {
        Pop-Location
    }

    if ($Results.FinalCsvExists -and $Results.StarSailorsAppears -and $Results.Sea6MetricsPresent -and $Results.ExtractionMetadataUpdated) {
        exit 0
    }
    exit 1
}

Push-Location $ProjectRoot
try {
    Write-Step "Checking token"
    if ([string]::IsNullOrWhiteSpace($env:SENSORTOWER_AUTH_TOKEN)) {
        Write-Host "FAIL: SENSORTOWER_AUTH_TOKEN is not set in this PowerShell session."
        Print-Summary
        exit 1
    }
    $Results.TokenAvailable = $true
    Write-Host "PASS: SENSORTOWER_AUTH_TOKEN is set."

    Write-Step "Creating backup"
    New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
    Copy-IfPresent -Source $ConfigPath -Destination (Join-Path $BackupRoot "config\settings.json")
    Copy-IfPresent -Source $OutputDir -Destination (Join-Path $BackupRoot "data\output")
    Copy-IfPresent -Source $RawDir -Destination (Join-Path $BackupRoot "data\raw")
    Copy-IfPresent -Source $ExtractionMetadataPath -Destination (Join-Path $BackupRoot "data\local_app\extraction_metadata.json")
    Copy-IfPresent -Source $WatchlistPath -Destination (Join-Path $BackupRoot "data\local_app\watchlist.csv")
    $Results.BackupCreated = $true
    Write-Host "PASS: Backup created."

    $BeforeRefreshAt = Get-MetadataRefreshValue

    Write-Step "Setting temporary previous report period"
    Set-ReportPeriod -ReportStart $TestReportStart -ReportEnd $TestReportEnd -RankingDate $TestRankingDate
    $Results.TestPeriodSet = $true
    Write-Host "PASS: Temporary period set to $TestReportStart to $TestReportEnd, ranking date $TestRankingDate."

    Write-Step "Running live meeting-date final report"
    Write-Host "Expected Sensor Tower API calls: 5 total (4 rank refresh + 1 SEA6 sales extraction)."
    python scripts\meeting_date_final_report.py
    if ($LASTEXITCODE -ne 0) {
        throw "meeting_date_final_report.py failed with exit code $LASTEXITCODE."
    }
    $Results.LiveWorkflowCompleted = $true
    Write-Host "PASS: Live workflow completed."
}
catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)"
}
finally {
    Write-Step "Restoring current operating config"
    try {
        Set-ReportPeriod -ReportStart $CurrentReportStart -ReportEnd $CurrentReportEnd -RankingDate $CurrentRankingDate
        $Results.ConfigRestored = $true
        Write-Host "PASS: Config restored to $CurrentReportStart to $CurrentReportEnd, ranking date $CurrentRankingDate."
    }
    catch {
        Write-Host "FAIL: Could not restore config automatically: $($_.Exception.Message)"
    }

    if ($Results.LiveWorkflowCompleted) {
        Write-Step "Checking outputs"
        Test-FinalCsvContent
        $AfterRefreshAt = Get-MetadataRefreshValue
        if (-not [string]::IsNullOrWhiteSpace($AfterRefreshAt) -and $AfterRefreshAt -ne $BeforeRefreshAt) {
            $Results.ExtractionMetadataUpdated = $true
        }
        Print-Summary
    }
    else {
        Print-Summary
    }

    Pop-Location
}

if ($Results.LiveWorkflowCompleted -and
    $Results.ConfigRestored -and
    $Results.FinalCsvExists -and
    $Results.StarSailorsAppears -and
    $Results.Sea6MetricsPresent -and
    $Results.ExtractionMetadataUpdated) {
    exit 0
}

exit 1
