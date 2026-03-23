param(
    [int]$Port = 5001,
    [string]$AppPath = "app.py"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvActivate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    throw "Virtual environment activation script not found: $venvActivate"
}

# Ensure Streamlit config exists and matches the selected port.
$streamlitDir = Join-Path $PSScriptRoot ".streamlit"
$configPath = Join-Path $streamlitDir "config.toml"
if (-not (Test-Path $streamlitDir)) {
    New-Item -ItemType Directory -Path $streamlitDir | Out-Null
}

@"
[server]
headless = true
address = "0.0.0.0"
port = $Port
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
"@ | Set-Content -Path $configPath -Encoding UTF8

. $venvActivate

Write-Host "Starting Timing tool on port $Port ..." -ForegroundColor Cyan
Write-Host "Project root: $PSScriptRoot" -ForegroundColor DarkGray
Write-Host "Config file : $configPath" -ForegroundColor DarkGray

streamlit run $AppPath --server.address 0.0.0.0 --server.port $Port
