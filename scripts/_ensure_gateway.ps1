# 网关保活（R3）：3000 不在就拉起来，已在就 no-op。
# 用法: pwsh -NoProfile -File scripts\_ensure_gateway.ps1 [-Quiet]
param([switch]$Quiet)
$ErrorActionPreference = 'Continue'

$port = 3000
$launcher = 'D:\relay\start-new-api.ps1'
$logDir = 'D:\NovelApp\logs'
$log = Join-Path $logDir ('gateway-keepalive-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))

function Say([string]$m) {
    if (-not $Quiet) { Write-Output $m }
    if (Test-Path $logDir) { Add-Content -LiteralPath $log -Value ('{0} {1}' -f (Get-Date -Format 's'), $m) -Encoding UTF8 }
}

if (-not (Test-Path -LiteralPath $launcher)) { Say "FAIL launcher-missing $launcher"; exit 2 }

$up = (Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)
if ($up) { Say "SKIP port-$port-already-up"; exit 0 }

Say "START gateway"
Start-Process -FilePath 'pwsh' -ArgumentList '-NoProfile', '-WindowStyle', 'Hidden', '-File', $launcher -WindowStyle Hidden | Out-Null

# 最多等 20s
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Milliseconds 1000
    if (Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) {
        Say "PASS port-$port-up after ${i}s"
        exit 0
    }
}
Say "FAIL port-$port-not-up-after-20s"
exit 1
