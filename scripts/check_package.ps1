<#
  check_package.ps1 —— NovelApp 打包产物完整性核对（只读脚本，不改任何文件）

  核对范围（win-unpacked\resources 下）：
    1) core\  必含页面 novel.html / rank.html / workflow.html / tools.html（工作台 app.html 已分离，不进包）
              并且含源码 core\*.py 里的全部 .py（按文件名逐一对照 D:\NovelApp\core）
    2) config\ 必含 lianzi_models.json / lianzi_wizard.json / pua_map.json / coordinator.json
    3) preset-data\ 下必须存在 novelapp-plugin\lib\index.js

  退出码：
    0 = 齐全
    1 = 有缺失（缺失项逐条列出）

  用法：
    pwsh -File D:\NovelApp\scripts\check_package.ps1
    pwsh -File D:\NovelApp\scripts\check_package.ps1 -Unpacked "D:\NovelApp\dist\win-unpacked"
    pwsh -File D:\NovelApp\scripts\check_package.ps1 -Json
#>

[CmdletBinding()]
param(
    # win-unpacked 目录；不传则自动探测（build.ps1 的 $OUT 优先）
    [string]$Unpacked = '',
    # 输出机器可读 JSON（便于接到 build.ps1 之后的步骤里）
    [switch]$Json
)

$ErrorActionPreference = 'Continue'

# 工程根 = 本脚本上一级（脚本固定放在 <工程>\scripts\ 下）
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# 硬性必含清单
$RequiredHtml   = @('novel.html', 'rank.html', 'workflow.html', 'tools.html')
$RequiredConfig = @('lianzi_models.json', 'lianzi_wizard.json', 'pua_map.json', 'coordinator.json')

$missing = New-Object System.Collections.ArrayList
$notes   = New-Object System.Collections.ArrayList

function Add-Missing {
    param(
        [string]$Category,
        [string]$Item,
        [string]$Path,
        [string]$Hint = ''
    )
    [void]$missing.Add([pscustomobject]@{
        Category = $Category
        Item     = $Item
        Path     = $Path
        Hint     = $Hint
    })
}

function Add-Note {
    param([string]$Text)
    [void]$notes.Add($Text)
}

# ---------- 1. 定位 win-unpacked ----------

# build.ps1 里的产物位置排第一，其余是常见 electron-builder 输出位
$candidates = @(
    (Join-Path $ProjectRoot 'dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked'),
    (Join-Path $ProjectRoot 'dist\win-unpacked'),
    (Join-Path $ProjectRoot 'win-unpacked'),
    (Join-Path $ProjectRoot '发布\win-unpacked'),
    (Join-Path $ProjectRoot '发布桌面版\win-unpacked')
)

$target = ''
if ($Unpacked -ne '') {
    $target = $Unpacked
}
else {
    # 先找 resources 齐的那种，避免命中残留空壳目录
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c 'resources')) { $target = $c; break }
    }
    if ($target -eq '') {
        foreach ($c in $candidates) {
            if (Test-Path $c) { $target = $c; break }
        }
    }
    if ($target -eq '') {
        # 兜底：只在少数已知父目录里浅层搜，避免扫全盘拖慢
        $searchRoots = @(
            (Join-Path $ProjectRoot 'dsh-src\apps\desktop\.desktop-build'),
            (Join-Path $ProjectRoot 'dist'),
            (Join-Path $ProjectRoot '发布'),
            (Join-Path $ProjectRoot '发布桌面版'),
            (Join-Path $ProjectRoot '_cache'),
            (Join-Path $ProjectRoot '_tmp')
        )
        foreach ($root in $searchRoots) {
            if (-not (Test-Path $root)) { continue }
            $hit = Get-ChildItem -Path $root -Directory -Recurse -Depth 3 -Filter 'win-unpacked' -ErrorAction SilentlyContinue |
                Where-Object { Test-Path (Join-Path $_.FullName 'resources') } |
                Select-Object -First 1
            if ($hit) { $target = $hit.FullName; break }
        }
    }
}

if ($target -eq '' -or -not (Test-Path $target)) {
    Add-Missing -Category '产物' -Item 'win-unpacked' -Path $target -Hint ('先跑 build.ps1；候选路径: ' + ($candidates -join ' | '))
}

$resources = ''
if ($target -ne '') { $resources = Join-Path $target 'resources' }

if ($target -ne '' -and -not (Test-Path $resources)) {
    Add-Missing -Category '产物' -Item 'resources' -Path $resources -Hint 'win-unpacked 存在但缺 resources 目录'
}

# ---------- 2. core 页面 + 全部 py ----------

$coreDir    = Join-Path $resources 'core'
$coreOk     = $false
$htmlFound  = 0
$pyFound    = 0
$pyTotal    = 0

if ($resources -ne '' -and (Test-Path $coreDir)) {
    $coreOk = $true

    foreach ($f in $RequiredHtml) {
        $p = Join-Path $coreDir $f
        if (Test-Path $p) {
            $htmlFound++
        }
        else {
            Add-Missing -Category 'core' -Item $f -Path $p -Hint '18771 页面，缺了客户机会 404'
        }
    }

    # 源码侧 py 名单作为基线：打进去的必须是全集
    $srcCore = Join-Path $ProjectRoot 'core'
    $srcPy = @()
    if (Test-Path $srcCore) {
        # 交付包不含开发自测脚本（test_*.py / selftest.py），基线同步排除
        $srcPy = @(Get-ChildItem -Path $srcCore -Filter '*.py' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike 'test_*' -and $_.Name -ne 'selftest.py' } |
            Select-Object -ExpandProperty Name)
    }

    $pkgPy = @(Get-ChildItem -Path $coreDir -Filter '*.py' -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    $pyFound = $pkgPy.Count

    if ($srcPy.Count -gt 0) {
        $pyTotal = $srcPy.Count
        foreach ($name in $srcPy) {
            $p = Join-Path $coreDir $name
            if (-not (Test-Path $p)) {
                Add-Missing -Category 'core' -Item $name -Path $p -Hint '源码 core 里有，包里没打进去'
            }
        }
        # 包里有、源码没有的，不算缺失，只提示
        foreach ($name in $pkgPy) {
            if ($srcPy -notcontains $name) {
                Add-Note ('core 里多出源码没有的 py: ' + $name)
            }
        }
    }
    else {
        # 没有源码基线可对照时，至少要有 py，否则 18771 服务起不来
        if ($pkgPy.Count -eq 0) {
            Add-Missing -Category 'core' -Item '*.py' -Path $coreDir -Hint 'core 下一个 py 都没有'
        }
        Add-Note ('未找到源码基线 ' + $srcCore + '，*.py 只做了「非空」判定')
    }
}
elseif ($resources -ne '') {
    Add-Missing -Category 'core' -Item 'core 目录' -Path $coreDir -Hint 'resources 下缺 core 目录'
}

# ---------- 3. config 四个 json ----------

$cfgDir    = Join-Path $resources 'config'
$cfgFound  = 0

if ($resources -ne '' -and (Test-Path $cfgDir)) {
    foreach ($f in $RequiredConfig) {
        $p = Join-Path $cfgDir $f
        if (Test-Path $p) {
            $cfgFound++
        }
        else {
            Add-Missing -Category 'config' -Item $f -Path $p -Hint 'coordinator.json 缺了本地网关起不来'
        }
    }
}
elseif ($resources -ne '') {
    Add-Missing -Category 'config' -Item 'config 目录' -Path $cfgDir -Hint 'resources 下缺 config 目录'
}

# ---------- 4. preset-data 里的插件入口 ----------

$presetDir = Join-Path $resources 'preset-data'
$pluginRel = 'profiles\desktop\node_modules\novelapp-plugin\lib\index.js'
$pluginHit = ''

if ($resources -ne '' -and (Test-Path $presetDir)) {
    $canonical = Join-Path $presetDir $pluginRel
    if (Test-Path $canonical) {
        $pluginHit = $canonical
    }
    else {
        # 规范路径不在时，退一步在 preset-data 下按 plugin\lib\index.js 结构找
        $found = Get-ChildItem -Path $presetDir -Filter 'index.js' -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match 'novelapp-plugin[\\/]+lib[\\/]+index\.js$' } |
            Select-Object -First 1
        if ($found) {
            $pluginHit = $found.FullName
            Add-Note ('插件入口不在规范路径，实到: ' + $found.FullName)
        }
        else {
            Add-Missing -Category 'preset-data' -Item 'novelapp-plugin\lib\index.js' -Path $canonical -Hint '插件没进包，助手侧功能会缺'
        }
    }
}
elseif ($resources -ne '') {
    Add-Missing -Category 'preset-data' -Item 'preset-data 目录' -Path $presetDir -Hint 'resources 下缺 preset-data 目录'
}

# ---------- 5. 输出 ----------

$ok = ($missing.Count -eq 0)

if ($Json) {
    $out = [pscustomobject]@{
        ok         = $ok
        unpacked   = $target
        resources  = $resources
        coreHtml   = ('{0}/{1}' -f $htmlFound, $RequiredHtml.Count)
        corePy     = ('{0}/{1}' -f $pyFound, $pyTotal)
        config     = ('{0}/{1}' -f $cfgFound, $RequiredConfig.Count)
        plugin     = $pluginHit
        missing    = @($missing)
        notes      = @($notes)
    }
    $out | ConvertTo-Json -Depth 5
}
else {
    Write-Host ''
    Write-Host 'NovelApp 打包完整性核对' -ForegroundColor Cyan
    Write-Host ('  产物: ' + $target)
    Write-Host ''

    if ($resources -ne '' -and (Test-Path $resources)) {
        Write-Host ('  resources: 存在  ' + $resources)
    }

    if ($coreOk) {
        Write-Host ('  core 页面: {0}/{1}' -f $htmlFound, $RequiredHtml.Count)
        if ($pyTotal -gt 0) {
            Write-Host ('  core py  : {0}/{1}' -f $pyFound, $pyTotal)
        }
        else {
            Write-Host ('  core py  : {0} 个（未取到源码基线）' -f $pyFound)
        }
    }

    if (Test-Path $cfgDir) {
        Write-Host ('  config   : {0}/{1}' -f $cfgFound, $RequiredConfig.Count)
    }

    if ($pluginHit -ne '') {
        Write-Host ('  插件入口 : 存在  ' + $pluginHit)
    }

    foreach ($n in $notes) {
        Write-Host ('  提示: ' + $n) -ForegroundColor DarkYellow
    }

    Write-Host ''
    if ($ok) {
        Write-Host '结果: OK  必含文件齐全' -ForegroundColor Green
    }
    else {
        Write-Host ('结果: FAIL  缺 {0} 项' -f $missing.Count) -ForegroundColor Red
        foreach ($m in $missing) {
            Write-Host ('  [缺] {0}  {1}' -f $m.Category, $m.Item) -ForegroundColor Red
            Write-Host ('       路径: ' + $m.Path) -ForegroundColor DarkGray
            if ($m.Hint -ne '') {
                Write-Host ('       说明: ' + $m.Hint) -ForegroundColor DarkGray
            }
        }
    }
    Write-Host ''
}

if ($ok) { exit 0 } else { exit 1 }