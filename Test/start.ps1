# Запуск HTTPS-копии сайта для теста с телефона
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.\run\app.py')) {
    Write-Host "First run: copying project to run\ ..."
    & "$PSScriptRoot\setup.ps1"
}

# IP хот-спота для сертификата
$hotspotIp = '192.168.137.1'
try {
    $adapt = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -like '192.168.137.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -First 1
    if ($adapt) { $hotspotIp = $adapt.IPAddress }
} catch { }

Write-Host "Cert SAN IP: $hotspotIp (+ localhost)"
python -c "import cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
    pip install cryptography -q
}
python .\generate_dev_https.py $hotspotIp 127.0.0.1 localhost
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Docker up (HTTPS :5443 only; main site may use :5000) ..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "PC:     https://127.0.0.1:5443"
Write-Host "Phone:  https://${hotspotIp}:5443"
Write-Host ""
Write-Host "DB first time:"
Write-Host "  docker compose exec app python database/init_db.py"
Write-Host "  docker compose exec app python database/migrate_guard_qr.py"
