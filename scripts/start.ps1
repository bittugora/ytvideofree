param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    # Use python from PATH or common install locations
    $python = (Get-Command "python" -ErrorAction SilentlyContinue).Source
    if (-not $python) { $python = "${env:LOCALAPPDATA}\Programs\Python\Python312\python.exe" }
    if (-not $python) { $python = "C:\Python312\python.exe" }
    if (-not (Test-Path $python)) { throw "Python not found. Install Python 3.12+ and ensure it is on your PATH." }
    & $python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:$Port
