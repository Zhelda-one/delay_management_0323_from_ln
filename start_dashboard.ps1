param(
    [int]$DashboardPort = 5000,
    [int]$TimingPort = 5001,
    [string]$TimingHost = "",
    [string]$SecretKey = "change-this-secret",
    [string]$AppPath = "app_unified.py"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvActivate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    throw "Virtual environment activation script not found: $venvActivate"
}

function Get-BestIPv4Address {
    $candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notmatch '^127\.' -and
            $_.IPAddress -notmatch '^169\.254\.' -and
            $_.PrefixOrigin -ne 'WellKnown'
        }

    if (-not $candidates) {
        return '127.0.0.1'
    }

    # Prefer private LAN ranges commonly used on enterprise/home networks.
    $preferred = $candidates | Where-Object {
        $_.IPAddress -match '^192\.168\.' -or
        $_.IPAddress -match '^10\.' -or
        $_.IPAddress -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.'
    } | Select-Object -First 1

    if ($preferred) {
        return $preferred.IPAddress
    }

    return ($candidates | Select-Object -First 1).IPAddress
}

if ([string]::IsNullOrWhiteSpace($TimingHost)) {
    $TimingHost = Get-BestIPv4Address
}

$env:FLASK_SECRET_KEY = $SecretKey
$env:TIMING_APP_URL = "http://${TimingHost}:$TimingPort"
$env:FLASK_RUN_PORT = "$DashboardPort"

. $venvActivate

Write-Host "Starting Dashboard ..." -ForegroundColor Cyan
Write-Host "Dashboard port : $DashboardPort" -ForegroundColor DarkGray
Write-Host "Timing app URL : $env:TIMING_APP_URL" -ForegroundColor Green
Write-Host "Project root    : $PSScriptRoot" -ForegroundColor DarkGray

python $AppPath
