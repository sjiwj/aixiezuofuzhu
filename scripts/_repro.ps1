# 复现器：按用例起壳 → 打接口 → 判定 → 写 repro 报告
# 用法: pwsh -NoProfile -File scripts\_repro.ps1 -Case polish [-Root D:\NovelApp] [-Port 8797]
param(
    [Parameter(Mandatory = $true)][ValidateSet('polish', 'entries', 'billing')][string]$Case,
    [string]$Root = 'D:\NovelApp',
    [int]$Port = 8797
)
$ErrorActionPreference = 'Continue'
$reproDir = Join-Path $Root 'repro'
New-Item -ItemType Directory -Force -Path $reproDir | Out-Null
$report = Join-Path $reproDir ("$Case.md")
$lines = @()
function Say($m) { $script:lines += $m; Write-Output $m }

Say "# repro: $Case"
Say ""
Say "- root: $Root"
Say "- port: $Port"
Say "- time: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')"

if (Test-NetConnection 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue) {
    Say "- FAIL 端口 $Port 已被占用，换 -Port"; $lines -join "`n" | Set-Content -Path $report -Encoding UTF8; exit 2
}

$srv = Join-Path $Root 'core\server.py'
if (-not (Test-Path $srv)) { Say "- FAIL 缺 $srv"; $lines -join "`n" | Set-Content $report -Encoding UTF8; exit 3 }

$p = Start-Process python -ArgumentList @($srv, "$Port", '--no-browser') -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $reproDir "$Case.out.txt") -RedirectStandardError (Join-Path $reproDir "$Case.err.txt")
Say "- pid: $($p.Id)"

$base = "http://127.0.0.1:$Port"
$up = $false
for ($i = 1; $i -le 25; $i++) {
    Start-Sleep -Milliseconds 400
    try { $h = Invoke-WebRequest "$base/api/health" -TimeoutSec 2 -UseBasicParsing; if ($h.StatusCode -eq 200) { $up = $true; Say "- health: 200 (${i}00ms x4)"; break } } catch {}
}
if (-not $up) {
    Say "- FAIL 服务未起来（看 $Case.err.txt）"
    if (Test-Path (Join-Path $reproDir "$Case.err.txt")) { Get-Content (Join-Path $reproDir "$Case.err.txt") -Tail 8 | ForEach-Object { Say "  $_" } }
}

$verdict = 'FAIL'
$detail = ''
try {
    switch ($Case) {
        'polish' {
            $body = '{"book":"","chapter":"","scope":"selection","text":"天没亮，桥头的市已经开了。","instruction":"更短","model":"deepseek-flash"}'
            $tmp = Join-Path $env:TEMP ("rep_" + [guid]::NewGuid().ToString('N') + ".txt")
            $code = & curl.exe -s -o $tmp -w "%{http_code}" -X POST "$base/api/polish" -H 'Content-Type: application/json' --data $body --max-time 90
            $raw = Get-Content $tmp -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            Remove-Item $tmp -Force -ErrorAction SilentlyContinue
            $delta = ([regex]::Matches($raw, '"type": "delta"')).Count
            $err = ([regex]::Matches($raw, '"type": "error"')).Count
            $done = ([regex]::Matches($raw, '"type": "done"')).Count
            $detail = "http=$code delta=$delta error=$err done=$done"
            if ($code -eq '200' -and $delta -gt 0 -and $err -eq 0 -and $done -eq 1) { $verdict = 'PASS' }
            if ($err -gt 0) { ([regex]::Matches($raw, '"message": "[^"]{0,120}') | ForEach-Object { Say ("  err: " + $_.Value) }) }
        }
        'entries' {
            $r = Invoke-WebRequest "$base/api/entries" -TimeoutSec 8 -UseBasicParsing
            $j = $r.Content | ConvertFrom-Json
            $n = @($j.entries).Count
            $detail = "http=$($r.StatusCode) entries=$n counts=$(($j.counts | ConvertTo-Json -Compress))"
            if ($r.StatusCode -eq 200 -and $n -eq 9) { $verdict = 'PASS' }
        }
        'billing' {
            $r = Invoke-WebRequest "$base/api/billing/status" -TimeoutSec 8 -UseBasicParsing
            $j = $r.Content | ConvertFrom-Json
            $detail = "http=$($r.StatusCode) mode=$($j.mode) billing=$($j.billing)"
            if ($r.StatusCode -eq 200 -and $j.mode -eq 'free') { $verdict = 'PASS' }
        }
    }
} catch {
    $detail = "exception: $($_.Exception.Message)"
}

Say ""
Say "## 判定"
Say ""
Say "- $verdict  $Case"
Say "- $detail"
Say ""
Say "## 复现命令"
Say '```powershell'
Say "pwsh -NoProfile -File scripts\_repro.ps1 -Case $Case -Root $Root -Port $Port"
Say '```'

try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Milliseconds 400
$left = Test-NetConnection 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
Say ""
Say "- cleanup: port $Port " + $(if ($left) { 'STILL-UP（FAIL）' } else { 'released' })
if ($left) { $verdict = 'FAIL' }

$lines -join "`n" | Set-Content -Path $report -Encoding UTF8
Write-Output "REPORT=$report"
if ($verdict -eq 'PASS') { exit 0 } else { exit 1 }
