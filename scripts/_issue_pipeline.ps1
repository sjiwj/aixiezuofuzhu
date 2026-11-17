# -*- coding: utf-8 -*-
<#
  issue 流水线（v1.0.1 第 4 项）
  -------------------------------------------------------------
  一条 issue 从分诊到 PR 描述，全程留痕：

    1) triage        python tools\triage.py           -> 类别 / 能否自动修
    2) 先红          _repro.ps1 -Case X -Assert Y     -> 必须 exit 1（问题真实存在）
    3) 改一个文件    -DoPatch 时调对应的修复脚本
    4) 转绿          _repro.ps1 同参数再来一遍        -> 必须 exit 0
    5) 自检          _check_keys + _smoke_entries     -> 必须 SUMMARY PASS
    6) PR 描述       写 repro\PR-<n>.md（不自动 push）

  用法：
    pwsh -NoProfile -File scripts\_issue_pipeline.ps1 -Issue repro\issue-0001-shipped-stale.md `
         -Case entries -Assert shipped-fresh [-DoPatch]

  退出码：0 全通；1 某步失败；2 参数/环境问题。
#>
param(
    [Parameter(Mandatory = $true)][string]$Issue,
    [Parameter(Mandatory = $true)][ValidateSet('polish', 'entries', 'billing')][string]$Case,
    [string[]]$Assert = @(),
    [switch]$DoPatch,
    [string]$FixScript = '',
    [int]$Port = 8797,
    [string]$Root = 'D:\NovelApp',
    [string]$PrNumber = '0001'
)

$ErrorActionPreference = 'Continue'
$script:Fails = 0
$script:Lines = @()

function Step([string]$Name, [bool]$Ok, [string]$Detail = '') {
    if ($Ok) {
        Write-Host ("PASS  {0}{1}" -f $Name, $(if ($Detail) { "  | $Detail" } else { '' }))
    } else {
        $script:Fails++
        Write-Host ("FAIL  {0}{1}" -f $Name, $(if ($Detail) { "  | $Detail" } else { '' })) -ForegroundColor Red
    }
    $script:Lines += "| $Name | $(if ($Ok) { 'PASS' } else { 'FAIL' }) | $Detail |"
    return $Ok
}

function Run-Repro([string]$Tag) {
    $args = @('-NoProfile', '-File', (Join-Path $Root 'scripts\_repro.ps1'),
              '-Case', $Case, '-Root', $Root, '-Port', "$Port")
    if ($Assert.Count -gt 0) { $args += @('-Assert') + $Assert }
    $out = & pwsh @args 2>&1
    $code = $LASTEXITCODE
    $verdict = ($out | Select-String -Pattern '^- (PASS|FAIL)\s' | Select-Object -First 1).Line
    Write-Host ("      [{0}] exit={1} {2}" -f $Tag, $code, ($verdict -replace '^-\s*', ''))
    return @{ code = $code; verdict = $verdict; out = $out }
}

# ---------- 0. 前置 ----------
if (-not (Test-Path $Issue)) { Write-Host "FAIL  找不到 issue：$Issue"; exit 2 }
$issueText = Get-Content $Issue -Raw -Encoding UTF8
Step 'pre:issue-exists' $true (Split-Path $Issue -Leaf)

# ---------- 1. triage ----------
$triageRaw = $issueText | python (Join-Path $Root 'tools\triage.py') 2>&1
$tri = $null
try { $tri = ($triageRaw -join "`n") | ConvertFrom-Json } catch { }
if (-not $tri) {
    Step 'triage:parse' $false (($triageRaw | Select-Object -First 3) -join ' ')
    exit 1
}
Step 'triage:classify' ([bool]$tri.category) ("category=$($tri.category) action=$($tri.action) repro_ready=$($tri.repro_ready)")
foreach ($m in @($tri.missing)) { if ($m) { Write-Host "      missing: $m" } }

if ($tri.action -ne 'auto-patch') {
    Write-Host "STOP  分诊结果 action=$($tri.action)，不在自动流水线上（quality/feature 走人工或提案）"
    exit 1
}

# ---------- 2. 先红 ----------
$red = Run-Repro 'red'
if (-not (Step 'repro:red' ($red.code -ne 0) ("exit=$($red.code) " + ($red.verdict -replace '^-\s*', '')))) {
    Write-Host 'STOP  先红失败：问题没复现出来（或断言不成立），不能往下改'
    exit 1
}

if (-not $DoPatch) {
    Write-Host ''
    Write-Host "DRY   已复现（红）。加 -DoPatch -FixScript scripts\_fix_xxx.py 才会改代码。"
    exit 1
}

# ---------- 3. 改一个文件 ----------
if (-not $FixScript) { Write-Host 'FAIL  需要 -FixScript'; exit 2 }
$fixPath = Join-Path $Root $FixScript
if (-not (Test-Path $fixPath)) { Write-Host "FAIL  找不到修复脚本：$fixPath"; exit 2 }
$fixOut = python $fixPath 2>&1
$fixCode = $LASTEXITCODE
Step 'patch:apply' ($fixCode -eq 0) ($fixScript + ' -> ' + (($fixOut | Select-Object -First 1) -join ''))
if ($fixCode -ne 0) { exit 1 }
$sync = python -c "import py_compile,os;py_compile.compile(os.path.join(r'$Root','core','server.py'),doraise=True);print('ok')" 2>&1
Step 'patch:syntax' ($LASTEXITCODE -eq 0) (($sync | Select-Object -First 1) -join '')
if ($LASTEXITCODE -ne 0) { exit 1 }

# ---------- 4. 转绿 ----------
$green = Run-Repro 'green'
if (-not (Step 'repro:green' ($green.code -eq 0) ("exit=$($green.code) " + ($green.verdict -replace '^-\s*', '')))) {
    Write-Host 'STOP  改完还是红的，回滚或继续查'
    exit 1
}

# ---------- 5. 自检 ----------
$ck = & pwsh -NoProfile -File (Join-Path $Root 'scripts\_check_keys.ps1') 2>&1
$ckOk = ($ck | Select-String -Pattern 'SUMMARY PASS').Count -gt 0
Step 'gate:check_keys' $ckOk (($ck | Select-String -Pattern 'SUMMARY').Line -join ' ')

$sm = & pwsh -NoProfile -File (Join-Path $Root 'scripts\_smoke_entries.ps1') 2>&1
$smOk = ($sm | Select-String -Pattern 'SUMMARY PASS').Count -gt 0
$smCounts = ($sm | Select-String -Pattern 'counts-sum-9').Line -join ' '
Step 'gate:smoke_entries' $smOk $smCounts

# ---------- 6. PR 描述 ----------
# 放 issues/ 而不是 repro/：repro/ 是可重生成的自测产物（.gitignore 忽略），
# issue 与 PR 描述是流程留痕，必须入库。
$issuesDir = Join-Path $Root 'issues'
New-Item -ItemType Directory -Force -Path $issuesDir | Out-Null
$prPath = Join-Path $issuesDir ("PR-{0}.md" -f $PrNumber)
$title = (($issueText -split "`n") | Where-Object { $_ -match '^#\s' } | Select-Object -First 1) -replace '^#\s*', ''
$pr = @()
$pr += "# PR $PrNumber — $title"
$pr += ''
$pr += "> 由 ``scripts\_issue_pipeline.ps1`` 生成；issue 原文：``$Issue``"
$pr += ''
$pr += '## 改了什么'
$pr += ''
$pr += "- 修复脚本：``$FixScript``（幂等，重复跑是 no-op；``--revert`` 可回滚）"
$pr += '- 触点：`core/server.py` 的 `entries_payload()`（本次只动 1 个文件）'
$pr += '- 新增返回字段：`shipped_stale`（布尔）、`shipped_note`（中文处置建议）'
$pr += ''
$pr += '## 先红后绿（同一断言）'
$pr += ''
$pr += '| 阶段 | 退出码 | 判定 |'
$pr += '|---|---:|---|'
$pr += "| 改前 | $($red.code) | $($red.verdict -replace '^-\s*', '') |"
$pr += "| 改后 | $($green.code) | $($green.verdict -replace '^-\s*', '') |"
$pr += ''
$pr += '## 改后行为（/api/entries 实测）'
$pr += ''
$ev = ($green.out | Select-String -Pattern 'shipped_stale=' | Select-Object -First 1).Line
$pr += '```text'
$pr += ($(if ($ev) { $ev.Trim() -replace '^-\s*', '' } else { '(未取到 shipped_stale 证据)' }))
$pr += '```'
$pr += ''
$pr += '## 复现命令'
$pr += ''
$pr += '```powershell'
$pr += "pwsh -NoProfile -File scripts\_repro.ps1 -Case $Case -Port $Port -Assert $($Assert -join ' ')"
$pr += '```'
$pr += ''
$pr += '## 交付门'
$pr += ''
$pr += '| 检查 | 结果 | 证据 |'
$pr += '|---|---|---|'
$pr += $script:Lines
$pr += ''
$pr += '## 审查提示'
$pr += ''
$pr += '- 只改了一个文件；没有顺手改别的。'
$pr += '- 断言写在 `_repro.ps1` 的 `-Assert` 里，不是口头承诺。'
$pr += '- 未 commit / 未 push（按仓库规矩，由人决定）。'
$pr -join "`n" | Set-Content -Path $prPath -Encoding UTF8
Step 'pr:written' (Test-Path $prPath) $prPath

Write-Host ''
if ($script:Fails -eq 0) {
    Write-Host 'SUMMARY PASS  (issue -> 红 -> 修 -> 绿 -> 自检 -> PR 描述)'
    Write-Host "PR: $prPath"
    exit 0
} else {
    Write-Host ("SUMMARY FAIL  (" + $script:Fails + " fail)")
    exit 1
}
