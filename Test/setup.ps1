# Копирует проект из родительской папки в Test\run\
$ErrorActionPreference = 'Stop'
$TestRoot = $PSScriptRoot
$Source = Split-Path $TestRoot -Parent
$Dest = Join-Path $TestRoot 'run'

if (-not (Test-Path $Source)) {
    Write-Error "Source not found: $Source"
}

Write-Host "Copy: $Source -> $Dest"

$excludeDirs = @(
    'Test', '.git', '.venv', 'venv', 'env', '__pycache__',
    'dev_certs', 'node_modules', '.cursor'
)
$excludeFiles = @('*.pyc', '*.log', '*.db', '*.sqlite', '*.sqlite3')

if (Test-Path $Dest) {
    Write-Host "Updating run\ ..."
} else {
    New-Item -ItemType Directory -Path $Dest | Out-Null
}

$robocopyArgs = @(
    $Source, $Dest,
    '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/nc', '/ns', '/np',
    '/XD'
) + $excludeDirs + @('/XF') + $excludeFiles

& robocopy @robocopyArgs | Out-Null
# robocopy: 0-7 = success
if ($LASTEXITCODE -ge 8) {
    Write-Error "robocopy failed: $LASTEXITCODE"
}

Write-Host "Done: $Dest"
Write-Host "Next: .\start.ps1"
