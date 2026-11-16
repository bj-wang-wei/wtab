$ErrorActionPreference = 'SilentlyContinue'
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen
foreach ($c in $conns) {
    Write-Host "Killing PID $($c.OwningProcess)"
    Stop-Process -Id $c.OwningProcess -Force
}
