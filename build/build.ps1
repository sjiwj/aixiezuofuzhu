# ============================================================
#  NovelApp 打包脚本
#  用法:  powershell -ExecutionPolicy Bypass -File build\build.ps1
#         powershell -File build\build.ps1 -OutDir "D:\NovelApp\发布" -SkipBuild
#  产物:  <OutDir>\  —— NovelApp.exe / 启动.bat / 使用说明.txt / web / config / scripts / projects
# ============================================================
param(
    [string]$OutDir = (Join-Path (Split-Path -Parent $PSScriptRoot) '发布'),
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$CRLF     = [string]::Concat([char]13, [char]10)
$root     = Split-Path -Parent $PSScriptRoot        # D:\NovelApp
$py       = 'C:\Python315\python.exe'
$buildDir = Join-Path $root 'build'
$distDir  = Join-Path $buildDir 'dist'
$workDir  = Join-Path $buildDir 'work'
$specDir  = Join-Path $buildDir 'spec'
$appDir   = Join-Path $distDir 'NovelApp'

Write-Host "[1/6] 环境检查" -ForegroundColor Cyan
if (-not (Test-Path $py)) { throw "找不到 Python: $py" }
& $py -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 不可用（$py -m PyInstaller --version 失败）" }

# ---------- 1. PyInstaller ----------
if (-not $SkipBuild) {
    Write-Host "[2/6] PyInstaller --onedir 打包" -ForegroundColor Cyan
    foreach ($d in @($distDir, $workDir, $specDir)) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force }
    }
    $pyArgs = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir', '--console', '--name', 'NovelApp',
        '--distpath', $distDir, '--workpath', $workDir, '--specpath', $specDir,
        (Join-Path $root 'core\server.py')
    )
    & $py @pyArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败，退出码 $LASTEXITCODE" }
    if (-not (Test-Path (Join-Path $appDir 'NovelApp.exe'))) { throw "没生成 NovelApp.exe" }
} else {
    Write-Host "[2/6] 跳过 PyInstaller（-SkipBuild）" -ForegroundColor Yellow
    if (-not (Test-Path (Join-Path $appDir 'NovelApp.exe'))) { throw "dist 里没有产物，不能 -SkipBuild" }
}

# ---------- 2. 数据目录（exe 旁边） ----------
Write-Host "[3/6] 复制数据目录 web/config/scripts" -ForegroundColor Cyan
foreach ($sub in @('web', 'config', 'scripts')) {
    $src = Join-Path $root $sub
    if (-not (Test-Path $src)) { throw "缺少数据目录: $sub" }
    $dst = Join-Path $appDir $sub
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Copy-Item $src $dst -Recurse -Force
}
# ---------- 不该发布的文件 ----------
#   web/index.html.bak*  前端备份
#   config/map_bad.json  测试用的错误地图
#   scripts/fixtures/    质检测试素材（脚本不 import）
#   __pycache__          字节码缓存
foreach ($x in @((Join-Path $appDir 'scripts\fixtures'), (Join-Path $appDir 'config\map_bad.json'))) {
    if (Test-Path $x) { Remove-Item $x -Recurse -Force }
}
# scripts/ 只发两个质检脚本，其余（测试脚本、fixtures）不进包
$keepScripts = @('l1_l2_check.py', 'l3_l4_check.py')
Get-ChildItem (Join-Path $appDir 'scripts') -File -ErrorAction SilentlyContinue |
    Where-Object { $keepScripts -notcontains $_.Name } | Remove-Item -Force
# 目录形式的备份（.bak-xxx / .bak-stats-round2）光删文件不够，整棵删
Get-ChildItem $appDir -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '.bak*' -or $_.Name -eq '__pycache__' } |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
Get-ChildItem (Join-Path $appDir 'web') -File -Filter '*.bak*' -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem (Join-Path $appDir 'config') -File -Filter '*.bak*' -ErrorAction SilentlyContinue | Remove-Item -Force
# config 只发三个文件；user_token.json 是客户登录后本机生成的，绝不能进包
$keepConfig = @('coordinator.json', 'map.json', 'qc_rules.json')
Get-ChildItem (Join-Path $appDir 'config') -File -ErrorAction SilentlyContinue |
    Where-Object { $keepConfig -notcontains $_.Name } | Remove-Item -Force

# 发布版必须清空 api_key：客户首次启动要走配置向导（否则带着开发者的 key 出厂，
# 既是泄露也绕过 configured=false 判断）
$relCfg = Join-Path $appDir 'config\coordinator.json'
if (Test-Path $relCfg) {
    $rc = Get-Content $relCfg -Raw -Encoding UTF8 | ConvertFrom-Json
    $rc.coordinator.api_key = ''
    foreach ($w in $rc.workers.PSObject.Properties) { $w.Value.api_key = '' }
    [System.IO.File]::WriteAllText($relCfg, ($rc | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  已清空发布版 coordinator.json 的 api_key（首次启动走配置向导）" -ForegroundColor Yellow
}
Get-ChildItem $appDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ---------- 许可证与版权声明必须随包分发 ----------
#   PolyForm Noncommercial Notices 段、Apache-2.0 §4(a) 都要求：拿到副本的人同时拿到条款。
#   之前发布包漏了这三个文件，属合规缺口。
foreach ($f in @('LICENSE', 'NOTICE', 'VERSION')) {
    $src = Join-Path $root $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $appDir $f) -Force }
    else { Write-Host "  警告：缺 $f" -ForegroundColor Yellow }
}
$tpn = Join-Path $root 'docs\legal\third-party-notices-v0.md'
if (Test-Path $tpn) { Copy-Item $tpn (Join-Path $appDir 'THIRD-PARTY-NOTICES.md') -Force }

$projDst = Join-Path $appDir 'projects'
if (Test-Path $projDst) { Remove-Item $projDst -Recurse -Force }
New-Item -ItemType Directory -Path $projDst | Out-Null

# ---------- 3. 输出到发布目录 ----------
Write-Host "[4/6] 同步到 $OutDir" -ForegroundColor Cyan
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
robocopy $appDir $OutDir /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy 失败，退出码 $LASTEXITCODE" }
$global:LASTEXITCODE = 0

# ---------- 4. 启动.bat ----------
Write-Host "[5/6] 生成 启动.bat" -ForegroundColor Cyan
$batLines = @(
    '@echo off',
    'setlocal',
    'chcp 65001 >nul',
    'cd /d "%~dp0"',
    'set "NOVELAPP_ROOT=%~dp0"',
    'if not exist "NovelApp.exe" (',
    '  echo [ERROR] NovelApp.exe not found next to this bat.',
    '  pause',
    '  exit /b 1',
    ')',
    'echo Starting NovelApp on http://127.0.0.1:8770 ...',
    'start "" "NovelApp.exe" 8770',
    'endlocal'
)
$batPath = Join-Path $OutDir '启动.bat'
[System.IO.File]::WriteAllText($batPath, ($batLines -join $CRLF) + $CRLF, [System.Text.Encoding]::GetEncoding(936))

# ---------- 5. 使用说明 ----------
$readme = @(
    'NovelApp 小说创作工作台 —— 使用说明',
    '',
    '1) 双击「启动.bat」。',
    '2) 服务在 http://127.0.0.1:8770 起来，浏览器会自动打开；没打开就手动访问。',
    '3) 关闭：关掉那个黑色命令行窗口，或任务管理器结束 NovelApp.exe。',
    '',
    '目录说明：',
    '  NovelApp.exe   主程序（已内置 Python 运行环境，无需安装 Python）',
    '  启动.bat       启动入口',
    '  web\           界面文件',
    '  config\        配置（coordinator.json 填模型 API，qc_rules.json 是质检阈值）',
    '  scripts\       质检脚本，可自行修改',
    '  projects\      小说项目都存这里，备份就复制这个目录',
    '',
    '换端口：编辑 启动.bat，把 8770 改成你要的端口。',
    '模型配置：config\coordinator.json 里填 endpoint / api_key / model。',
    ''
)
$readmePath = Join-Path $OutDir '使用说明.txt'
[System.IO.File]::WriteAllText($readmePath, ($readme -join $CRLF) + $CRLF, (New-Object System.Text.UTF8Encoding($true)))

# ---------- 6. 报告 ----------
Write-Host "[6/6] 完成" -ForegroundColor Green
$exe = Join-Path $OutDir 'NovelApp.exe'
$sizeMB = [math]::Round(((Get-Item $exe).Length / 1MB), 1)
Write-Host ("  exe      : {0} ({1} MB)" -f $exe, $sizeMB)
Write-Host ("  发布体积 : {0} MB" -f [math]::Round(((Get-ChildItem $OutDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1))
Write-Host ("  文件数   : {0}" -f (Get-ChildItem $OutDir -Recurse -File | Measure-Object).Count)
Write-Host "  发布内容（不含 _internal）:"
Get-ChildItem $OutDir -Recurse -File | Where-Object { $_.FullName -notlike '*_internal*' } |
    ForEach-Object { Write-Host ("    " + $_.FullName.Substring($OutDir.Length + 1) + "  " + $_.Length) }
foreach ($bad in @('web\index.html.bak', 'web\index.html.bak2', 'web\index.html.bak3', 'config\map_bad.json', 'scripts\fixtures')) {
    if (Test-Path (Join-Path $OutDir $bad)) { throw "发布目录混进了不该发的 $bad" }
}
foreach ($need in @('NovelApp.exe', '启动.bat', '使用说明.txt', 'web\index.html', 'config\coordinator.json', 'config\qc_rules.json', 'scripts\l1_l2_check.py', 'scripts\l3_l4_check.py', 'projects')) {
    $ok = Test-Path (Join-Path $OutDir $need)
    Write-Host ("  {0,-30} {1}" -f $need, $(if ($ok) { 'OK' } else { 'MISSING' })) -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })
    if (-not $ok) { throw "发布目录缺少 $need" }
}
