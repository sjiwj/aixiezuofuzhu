# -*- coding: utf-8 -*-
<#
  M0 冒烟：自研外壳 9 入口路由表 + 缺失入口占位
  -------------------------------------------------------------
  做什么：
    1) 起 python core\desktop.py --dev（NOVELAPP_PORT=8781）
    2) 轮询 /api/health（≤20s）
    3) 取 /api/entries：断言 9 条、key 集合完全一致、状态自洽
       - wired / ui_only  → evidence_route 必须非空（后端真有 handler）
       - missing         → GET+POST 该 route 必须 501 + X-Entry-State: missing + not_implemented
    4) 断言 server_source_bytes / shipped_bytes 都 > 0（源码 vs 发布包 4 倍差是核心事实）
    5) 杀自己起的进程，Test-NetConnection 127.0.0.1 -Port 8781 必须 False
  退出码：0 = 全 PASS；1 = 有 FAIL

  幂等：脚本本身不写盘（只读 API + 启停进程），连跑两遍结果一致。
#>
$ErrorActionPreference = 'Stop'
$Root = 'D:\NovelApp'
$Port = 8781
$Base = "http://127.0.0.1:$Port"
$ExpectedKeys = @('shelf', 'startbook', 'write', 'outline', 'settings', 'breakdown', 'qc', 'style', 'billing')

$script:Fails = 0
$script:Proc = $null

function Check {
    param([string]$Name, [bool]$Ok, [string]$Detail = '')
    if ($Ok) {
        Write-Host ("PASS  {0}{1}" -f $Name, $(if ($Detail) { "  | $Detail" } else { '' }))
    } else {
        $script:Fails++
        Write-Host ("FAIL  {0}{1}" -f $Name, $(if ($Detail) { "  | $Detail" } else { '' }))
    }
}

function Stop-Owned {
    if ($script:Proc -and -not $script:Proc.HasExited) {
        Stop-Process -Id $script:Proc.Id -Force -ErrorAction SilentlyContinue
        try { $script:Proc.WaitForExit(5000) | Out-Null } catch { }
    }
    # 兜底：只杀仍占着本脚本端口、且确实是我们起的那个 PID
    $ownPid = if ($script:Proc) { $script:Proc.Id } else { 0 }
    for ($i = 0; $i -lt 20; $i++) {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if (-not $conn) { break }
        foreach ($c in $conn) {
            if ($ownPid -and $c.OwningProcess -eq $ownPid) {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Milliseconds 250
    }
}

try {
    # ---------- 0. 端口先干净，否则拒绝跑（不碰别人的进程） ----------
    $pre = Test-NetConnection 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
    Check "pre:port-$Port-free" (-not $pre) "Test-NetConnection -> $pre"
    if ($pre) { throw "端口 $Port 已被占用，拒绝起服务（避免误杀别人进程）" }

    # ---------- 1. 起外壳 ----------
    $env:NOVELAPP_PORT = "$Port"
    $env:NOVELAPP_ROOT = $Root
    Remove-Item Env:NOVELAPP_BACKEND_TOKEN -ErrorAction SilentlyContinue   # 本地调试：不开 token 校验
    $py = (Get-Command python).Source
    $script:Proc = Start-Process -FilePath $py `
        -ArgumentList @('core\desktop.py', '--dev') `
        -WorkingDirectory $Root -PassThru -WindowStyle Minimized
    Check "start:desktop.py" ($null -ne $script:Proc -and $script:Proc.Id -gt 0) ("pid=" + $script:Proc.Id + " python=" + $py)

    # ---------- 2. 等 /api/health ----------
    $ready = $false
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 20) {
        try {
            $h = Invoke-WebRequest -Uri "$Base/api/health" -TimeoutSec 3 -SkipHttpErrorCheck -UseBasicParsing
            if ($h.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 300
    }
    $elapsed = [math]::Round(((Get-Date) - $t0).TotalSeconds, 2)
    Check "health:200" $ready ("waited=${elapsed}s")
    if (-not $ready) { throw "20s 内 /api/health 没起来" }
    $health = $h.Content | ConvertFrom-Json
    Check "health:ok-true" ([bool]$health.ok) ("root=" + $health.root)

    # ---------- 3. /api/entries ----------
    $r = Invoke-WebRequest -Uri "$Base/api/entries" -TimeoutSec 10 -SkipHttpErrorCheck -UseBasicParsing
    Check "entries:http-200" ($r.StatusCode -eq 200) ("status=" + $r.StatusCode)
    $doc = $r.Content | ConvertFrom-Json
    Check "entries:ok-true" ([bool]$doc.ok)
    $entries = @($doc.entries)
    Check "entries:count-9" ($entries.Count -eq 9) ("count=" + $entries.Count)

    $got = @($entries | ForEach-Object { $_.key })
    $missingKeys = @($ExpectedKeys | Where-Object { $got -notcontains $_ })
    $extraKeys = @($got | Where-Object { $ExpectedKeys -notcontains $_ })
    Check "entries:key-set" (($missingKeys.Count -eq 0) -and ($extraKeys.Count -eq 0) -and ($got.Count -eq $ExpectedKeys.Count)) `
        ("got=[" + ($got -join ',') + "] missing=[" + ($missingKeys -join ',') + "] extra=[" + ($extraKeys -join ',') + "]")

    Check "entries:counts-sum-9" ((@($doc.counts.wired, $doc.counts.ui_only, $doc.counts.missing) | Measure-Object -Sum).Sum -eq 9) `
        ("wired=" + $doc.counts.wired + " ui_only=" + $doc.counts.ui_only + " missing=" + $doc.counts.missing)

    foreach ($e in $entries) {
        $st = [string]$e.state
        $ev = [string]$e.evidence_route
        switch ($st) {
            { $_ -in 'wired', 'ui_only' } {
                Check ("entry:" + $e.key + ":evidence-route") ([bool]$ev) ("state=$st evidence_route=$ev route=" + $e.route)
                # 有真实 handler 的路径绝不能是 501
                $p = Invoke-WebRequest -Uri ($Base + $ev) -TimeoutSec 5 -SkipHttpErrorCheck -UseBasicParsing -Method Get -ErrorAction SilentlyContinue
                Check ("entry:" + $e.key + ":not-501") ($p.StatusCode -ne 501) ("GET " + $ev + " -> " + $p.StatusCode)
            }
            'missing' {
                Check ("entry:" + $e.key + ":evidence-route-empty") (-not [bool]$ev) ("state=missing evidence_route='" + $ev + "' route=" + $e.route)
                $g = Invoke-WebRequest -Uri ($Base + [string]$e.route) -TimeoutSec 5 -SkipHttpErrorCheck -UseBasicParsing -Method Get
                $gb = $g.Content | ConvertFrom-Json
                Check ("entry:" + $e.key + ":GET-501") ($g.StatusCode -eq 501) ("GET " + $e.route + " -> " + $g.StatusCode)
                Check ("entry:" + $e.key + ":GET-header") ([string]$g.Headers['X-Entry-State'] -eq 'missing') ("X-Entry-State=" + [string]$g.Headers['X-Entry-State'])
                Check ("entry:" + $e.key + ":GET-body") (($gb.ok -eq $false) -and ($gb.error -eq 'not_implemented') -and ($gb.entry -eq $e.key)) `
                    ("body=" + ($gb | ConvertTo-Json -Compress))
                $po = Invoke-WebRequest -Uri ($Base + [string]$e.route) -TimeoutSec 5 -SkipHttpErrorCheck -UseBasicParsing -Method Post `
                    -ContentType 'application/json' -Body '{}'
                Check ("entry:" + $e.key + ":POST-501") ($po.StatusCode -eq 501) ("POST " + $e.route + " -> " + $po.StatusCode)
            }
            default {
                Check ("entry:" + $e.key + ":state-valid") $false ("state=" + $st)
            }
        }
    }

    # ---------- 4. 源码 vs 发布包字节数 ----------
    Check "bytes:server_source>0" ([int]$doc.server_source_bytes -gt 0) ("server_source_bytes=" + $doc.server_source_bytes + " path=" + $doc.server_source)
    Check "bytes:shipped>0" ([int]$doc.shipped_bytes -gt 0) ("shipped_bytes=" + $doc.shipped_bytes + " present=" + $doc.shipped_present + " path=" + $doc.shipped_path)
    $ratio = if ([int]$doc.shipped_bytes -gt 0) { [math]::Round([double]$doc.server_source_bytes / [double]$doc.shipped_bytes, 2) } else { 0 }
    Check "bytes:source-gt-shipped" ($ratio -gt 1) ("ratio=source/shipped=" + $ratio + "x")
}
catch {
    $script:Fails++
    Write-Host ("FAIL  exception  | " + $_.Exception.Message)
}
finally {
    # ---------- 5. 清理 + 端口证明 ----------
    Stop-Owned
    $listen = Test-NetConnection 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
    Check "cleanup:port-$Port-released" (-not $listen) ("Test-NetConnection 127.0.0.1 -Port $Port -> " + $listen)
    $left = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    Check "cleanup:no-listener" ($left.Count -eq 0) ("listeners=" + $left.Count)
    if ($script:Proc) {
        Check "cleanup:proc-exited" ([bool]$script:Proc.HasExited) ("pid=" + $script:Proc.Id + " hasExited=" + $script:Proc.HasExited)
    }
}

Write-Host ""
if ($script:Fails -eq 0) {
    Write-Host "SUMMARY PASS  (0 fail)"
    exit 0
} else {
    Write-Host ("SUMMARY FAIL  (" + $script:Fails + " fail)")
    exit 1
}
