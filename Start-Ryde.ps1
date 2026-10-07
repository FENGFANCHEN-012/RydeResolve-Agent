param([int]$Port = 8000, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& python -c "import fastapi, uvicorn, psycopg; import src.api.main"
if ($LASTEXITCODE -ne 0) {
    throw 'Required packages are missing. Run: python -m pip install -r requirements.txt'
}
$taskListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($taskListener) {
    throw "Port $Port is already in use. Stop the old server or run this script with -Port 8001."
}
Write-Host "RYDE: http://127.0.0.1:$Port"
Write-Host 'Keep this window open. Press Ctrl+C to stop the server.'
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
& python -m uvicorn src.api.main:app --host 127.0.0.1 --port $Port
