# -*- coding: utf-8 -*-
# scripts\_smoke_billing.ps1 —— 付费闸冒烟（task-5）
#
# 跑法：pwsh -File D:\NovelApp\scripts\_smoke_billing.ps1
# 退出码 0 = 全绿；非 0 = 至少一条断言失败（日志/账本路径会在结尾打印）
#
# 独立账本：每次跑生成 data\billing\_smoke\ledger-<ts>.jsonl，不碰生产账本，
# 也不删历史（append-only 连测试账本一起守）。
#
# 第 3/4 章用 mode=append 打「空章节」这条路径：闸门放行后会撞上
# 「append 模式要求该章已有正文」→ HTTP 400。因此「放行」的证据是
# 非 402 + append 提示，全程不调用模型、不写任何章节文件。

$ErrorActionPreference = 'Stop'
$Root    = 'D:\NovelApp'
$Port    = 8785
$Book    = '端到端测试'
$Ts      = Get-Date -Format 'yyyyMMdd-HHmmss'
$Dir     = Join-Path $Root 'data\billing\_smoke'
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$Ledger  = Join-Path $Dir "ledger-$Ts.jsonl"
$Log     = Join-Path $Dir "smoke-$Ts.log"
$env:NOVELAPP_BILLING_LEDGER = $Ledger
$Base    = "http://127.0.0.1:$Port"
$script:fail = 0

function Say($m) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $m
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding utf8
}
function Assert($cond, $name, $detail) {
    if ($cond) { Say ("PASS  " + $name) }
    else { $script:fail++; Say ("FAIL  " + $name + "  << " + $detail) }
}
function PortOpen($p) {
    $c = New-Object System.Net.Sockets.TcpClient
    try { $c.Connect('127.0.0.1', $p); return $true } catch { return $false } finally { $c.Dispose() }
}
function Req($Method, $Path, $Body) {
    $h = @{ Uri = "$Base$Path"; Method = $Method; SkipHttpErrorCheck = $true; TimeoutSec = 60 }
    if ($null -ne $Body) {
        $h['ContentType'] = 'application/json; charset=utf-8'
        $h['Body'] = ($Body | ConvertTo-Json -Depth 8 -Compress)
    }
    $r = Invoke-WebRequest @h
    $j = $null
    try { $j = $r.Content | ConvertFrom-Json } catch { }
    [pscustomobject]@{ Code = [int]$r.StatusCode; Text = $r.Content; Json = $j }
}
function LedgerRows {
    if (-not (Test-Path $Ledger)) { return @() }
    return @(Get-Content $Ledger -Encoding utf8 | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_ | ConvertFrom-Json })
}
function LedgerCount { return @(LedgerRows).Count }

$proc = $null
try {
    Say "ledger = $Ledger"
    Say "book   = $Book   port = $Port"

    # ---------- 0. 语法 / 编码 ----------
    python -m py_compile (Join-Path $Root 'core\paid_gate.py') (Join-Path $Root 'core\server.py')
    Assert ($LASTEXITCODE -eq 0) 'py_compile 0' "exit=$LASTEXITCODE"

    foreach ($f in @('core\paid_gate.py', 'core\server.py', 'scripts\_smoke_billing.ps1')) {
        $p = Join-Path $Root $f
        if (-not (Test-Path $p)) { Assert $false "存在：$f" 'missing'; continue }
        $b = [System.IO.File]::ReadAllBytes($p)
        $bom = ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)
        Assert (-not $bom) "UTF-8 无 BOM：$f" 'BOM found'
    }

    # ---------- 1. 起壳 ----------
    if (PortOpen $Port) { throw "端口 $Port 已被占用，先释放再跑（不猜是谁的进程）" }
    $so = Join-Path $Dir "srv-$Ts.out"
    $se = Join-Path $Dir "srv-$Ts.err"
    $proc = Start-Process -FilePath 'python' `
        -ArgumentList @((Join-Path $Root 'core\server.py'), "$Port", '--no-browser') `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput $so -RedirectStandardError $se
    $up = $false
    for ($i = 0; $i -lt 80; $i++) { if (PortOpen $Port) { $up = $true; break }; Start-Sleep -Milliseconds 400 }
    Assert $up '起壳：8785 监听' "pid=$($proc.Id) err=$(Get-Content $se -Raw -ErrorAction SilentlyContinue)"
    if (-not $up) { throw '服务没起来，后面的断言无意义' }
    Start-Sleep -Milliseconds 600

    # ---------- 2. status ----------
    $st = Req 'GET' '/api/billing/status' $null
    Assert ($st.Code -eq 200) 'GET /api/billing/status 200' "code=$($st.Code) body=$($st.Text)"
    $names = @($st.Json.PSObject.Properties.Name)
    foreach ($k in @('free_chapters', 'tier', 'balance', 'summary')) {
        Assert ($names -contains $k) "status 含 $k" "keys=$($names -join ',')"
    }
    Assert ($st.Json.free_chapters -eq 3) 'free_chapters=3' "got=$($st.Json.free_chapters)"
    Assert ([double]$st.Json.balance -eq 0) '初始 balance=0' "got=$($st.Json.balance)"
    Assert ($st.Json.audit.ok -eq $true) 'status.audit 一致' "audit=$($st.Json.audit | ConvertTo-Json -Compress)"
    Say "status 原文: $($st.Text)"

    # ---------- 3. 第 3 章放行 / 第 4 章 402 ----------
    $b3 = @{ book = $Book; chapter = '第3章'; mode = 'append'; prompt = 'smoke-billing-3' }
    $r3 = Req 'POST' '/api/write' $b3
    Assert ($r3.Code -ne 402) '第 3 章：闸门放行（非 402）' "code=$($r3.Code) body=$($r3.Text)"
    Assert ($r3.Code -eq 400 -and "$($r3.Json.error)" -like '*append*') '第 3 章：走到 append 校验' "body=$($r3.Text)"
    Say "第3章响应: $($r3.Code) $($r3.Text)"

    $b4 = @{ book = $Book; chapter = '第4章'; mode = 'append'; prompt = 'smoke-billing-4' }
    $r4 = Req 'POST' '/api/write' $b4
    Assert ($r4.Code -eq 402) '第 4 章：HTTP 402' "code=$($r4.Code) body=$($r4.Text)"
    Assert ("$($r4.Json.error)" -eq 'payment_required') '第 4 章：payment_required' "body=$($r4.Text)"
    Say "402 原文: $($r4.Text)"

    # ---------- 4. topup ----------
    $tp = Req 'POST' '/api/billing/topup' @{ tier = 'month'; amount = 49; ref = 'smoke-1' }
    Assert ($tp.Code -eq 200 -and $tp.Json.ok -eq $true) 'topup month 49 / smoke-1' "body=$($tp.Text)"
    Assert ($tp.Json.duplicate -eq $false) 'topup 首次 duplicate=false' "body=$($tp.Text)"
    Assert ([double]$tp.Json.balance -eq 49) 'topup 后 balance=49' "got=$($tp.Json.balance)"
    $lines1 = LedgerCount
    Assert ($lines1 -eq 1) '账本 1 行' "lines=$lines1"
    Say "topup 原文: $($tp.Text)"

    # ---------- 5. topup 后第 4 章放行 ----------
    $r4b = Req 'POST' '/api/write' $b4
    Assert ($r4b.Code -ne 402) 'topup 后第 4 章：放行（非 402）' "code=$($r4b.Code) body=$($r4b.Text)"
    Assert ($r4b.Code -eq 400 -and "$($r4b.Json.error)" -like '*append*') 'topup 后第 4 章：走到 append 校验' "body=$($r4b.Text)"
    Say "topup 后第4章响应: $($r4b.Code) $($r4b.Text)"

    # ---------- 6. 幂等：同 ref 重放 ----------
    $dup = Req 'POST' '/api/billing/topup' @{ tier = 'month'; amount = 49; ref = 'smoke-1' }
    Assert ($dup.Json.duplicate -eq $true) '同 ref 重放 duplicate=true' "body=$($dup.Text)"
    Assert ([double]$dup.Json.balance -eq 49) '重复充值不加账（balance 仍 49）' "got=$($dup.Json.balance)"
    $lines2 = LedgerCount
    Assert ($lines2 -eq $lines1) '同 ref 重放账本行数不变' "before=$lines1 after=$lines2"
    Say "duplicate 原文: $($dup.Text)"

    # ---------- 7. usage 回退 local_ledger（R22） ----------
    $u = Req 'GET' '/api/account/usage?limit=5' $null
    Assert ($u.Code -eq 200) 'GET /api/account/usage 200' "code=$($u.Code) body=$($u.Text)"
    Assert ("$($u.Json.source)" -eq 'local_ledger') 'usage.source=local_ledger' "body=$($u.Text)"
    Say "usage 原文: $($u.Text)"

    # ---------- 8. consume + refund（真实 API，同一账本） ----------
    $py = @'
import sys, json
sys.path.insert(0, r'D:\NovelApp\core')
import paid_gate as PG
c = PG.consume(1, chapter='004', ref='write:smoke:004', model='deepseek-flash',
               usage={'prompt_tokens': 1820, 'completion_tokens': 456})
f = PG.refund(14.8, ref='smoke-refund-1')
d = PG.consume(1, chapter='004', ref='write:smoke:004', model='deepseek-flash')
print(json.dumps({'consume': {k: v for k, v in c.items() if k != 'row'},
                  'refund': {k: v for k, v in f.items() if k != 'row'},
                  'consume_dup': {k: v for k, v in d.items() if k != 'row'},
                  'balance': PG.balance(), 'quota': PG.quota(),
                  'used': PG.consumed_chapters()}, ensure_ascii=False))
'@
    $pyOut = $py | python -
    Assert ($LASTEXITCODE -eq 0) 'python 侧 consume/refund 执行' "out=$pyOut"
    $pj = $pyOut | ConvertFrom-Json
    Add-Content -Path $Log -Value ("consume/refund 原文: " + $pyOut) -Encoding utf8
    Say "consume/refund 原文: $pyOut"
    Assert ($pj.consume.ok -eq $true -and $pj.consume.duplicate -eq $false) 'consume 落账' "$pyOut"
    Assert ($pj.consume_dup.duplicate -eq $true) 'consume 同 ref 重放 duplicate=true' "$pyOut"
    Assert ($pj.refund.ok -eq $true -and [double]$pj.refund.amount -eq -14.8) 'refund 落负数分录' "$pyOut"
    Assert ([double]$pj.balance -eq 34.2) 'PG.balance()=34.2' "got=$($pj.balance)"
    Assert ([double]$pj.quota -eq 59) 'PG.quota()=59' "got=$($pj.quota)"

    # ---------- 9. 账本 3 行 + 手算对照 ----------
    $rows = LedgerRows
    Assert (@($rows).Count -eq 3) '账本 3 行（topup / consume / refund）' "lines=$(@($rows).Count)"
    $topupAmt  = (@($rows | Where-Object { $_.kind -eq 'topup' })  | Measure-Object -Property amount -Sum).Sum
    $refundAmt = (@($rows | Where-Object { $_.kind -eq 'refund' }) | Measure-Object -Property amount -Sum).Sum
    $boughtCh  = (@($rows | Where-Object { $_.kind -eq 'topup' })  | Measure-Object -Property chapters -Sum).Sum
    $usedCh    = (@($rows | Where-Object { $_.kind -eq 'consume' }) | Measure-Object -Property chapters -Sum).Sum
    $handBalance = [math]::Round([double]$topupAmt + [double]$refundAmt, 4)
    $handQuota   = [math]::Round([double]$boughtCh - [double]$usedCh, 4)
    Say ("手算：balance = {0} + ({1}) = {2} ；quota = {3} - {4} = {5}" -f $topupAmt, $refundAmt, $handBalance, $boughtCh, $usedCh, $handQuota)
    $st2 = Req 'GET' '/api/billing/status' $null
    Assert ([double]$st2.Json.balance -eq $handBalance) 'status.balance == 手算' "status=$($st2.Json.balance) hand=$handBalance"
    Assert ([double]$st2.Json.remaining -eq $handQuota) 'status.remaining == 手算' "status=$($st2.Json.remaining) hand=$handQuota"
    Assert ($st2.Json.audit.ok -eq $true) '最后一行 balance_after 与重算一致' "audit=$($st2.Json.audit | ConvertTo-Json -Compress)"

    Say '---- 账本原文（append-only）----'
    foreach ($l in (Get-Content $Ledger -Encoding utf8 | Where-Object { $_.Trim() -ne '' })) { Say $l }
    Say ("summary: " + ($st2.Json.summary | ConvertTo-Json -Compress))
}
catch {
    $script:fail++
    Say ("EXCEPTION: " + $_.Exception.Message)
}
finally {
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*core\server.py*8785*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 800
    $still = PortOpen $Port
    Assert (-not $still) '端口 8785 已释放' "still open"
    $tnc = (Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
    Say "Test-NetConnection 127.0.0.1 -Port $Port -> TcpTestSucceeded=$tnc"
    Say "ledger = $Ledger"
    Say "log    = $Log"
    if ($script:fail -gt 0) { Say ("RESULT: FAIL  ({0} 条断言失败)" -f $script:fail); exit 1 }
    Say 'RESULT: ALL GREEN'
    exit 0
}
