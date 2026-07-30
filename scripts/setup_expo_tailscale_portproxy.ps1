param(
    [Parameter(Mandatory = $true)]
    [string]$TailscaleIp,
    [string]$WslIp = "",
    [int]$Port = 8081
)

$ErrorActionPreference = "Stop"

if (-not $WslIp) {
    throw "Pass WSL IP explicitly: -WslIp 172.x.x.x"
}

Write-Host "Tailscale IP: $TailscaleIp"
Write-Host "WSL IP:       $WslIp"
Write-Host "Port:         $Port"

netsh interface portproxy delete v4tov4 listenaddress=$TailscaleIp listenport=$Port 2>$null

netsh interface portproxy add v4tov4 `
    listenaddress=$TailscaleIp `
    listenport=$Port `
    connectaddress=$WslIp `
    connectport=$Port

$ruleName = "Expo Metro $Port Tailscale"

$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if (-not $existingRule) {
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $Port `
        -RemoteAddress 100.64.0.0/10 | Out-Null
}

Write-Host "OK: portproxy configured."
Write-Host "Check from phone: http://$TailscaleIp`:$Port/status"
