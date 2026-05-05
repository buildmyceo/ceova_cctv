$port = 1425
$process = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue

if ($process) {
    Stop-Process -Id $process.OwningProcess -Force
    Write-Output "Killed process on port $port"
} else {
    Write-Output "Port $port is free"
}
