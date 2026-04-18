$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path .venv)) {
    python -m venv .venv
}

$python = Join-Path $root '.venv\Scripts\python.exe'
$pip = Join-Path $root '.venv\Scripts\pip.exe'

& $python -m pip install --upgrade pip
& $pip install -r requirements.txt
& $python -m playwright install chromium

Write-Host 'Starting Jobapplyer dashboard at http://127.0.0.1:8000'
& $python -m jobapplyer.main
