# 一键发布：自检 → 建远端 → 推送 → 打源码包（不含小说/密钥）
# 用法:
#   pwsh -NoProfile -File scripts\_publish.ps1 -RemoteUrl https://github.com/<你>/novelapp
#   需要凭证时: -Token <PAT>（只在本次命令里用，推完会把 remote 改回无 token 的 URL）
param(
    [Parameter(Mandatory = $true)][string]$RemoteUrl,
    [string]$Token = '',
    [string]$Branch = 'main'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$fail = 0
function Chk($name, $ok, $detail) { if ($ok) { "PASS  $name  | $detail" } else { "FAIL  $name  | $detail"; $script:fail++ } }

# ---------- 1. 工作区必须干净（只允许已提交内容）----------
$dirty = @(git status --porcelain)
Chk 'git:clean' ($dirty.Count -eq 0) "未提交改动 $($dirty.Count) 个（有就先 commit，避免带上未审内容）"

# ---------- 2. 提交里不许有小说 / 密钥 / 禁区 ----------
$novel = @(git grep -I -n -E '<书名>|沈砚|刘家庄|具状人' HEAD -- . 2>$null)
Chk 'commit:no-novel' ($novel.Count -eq 0) "小说相关命中 $($novel.Count) 行"
$keys = @(git grep -I -n -E 'sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}' HEAD -- . 2>$null)
Chk 'commit:no-secret' ($keys.Count -eq 0) "密钥形态命中 $($keys.Count) 行"
$forbid = @(git ls-tree -r --name-only HEAD | Select-String '^(projects/|docs/plan/|_tmp/|发布|dsh-src/|.*\.db$|.*\.bak-)' )
Chk 'commit:no-forbidden-path' ($forbid.Count -eq 0) "禁区路径 $($forbid.Count) 条"

# ---------- 3. 体积预算 ----------
$n = (git ls-tree -r --name-only HEAD | Measure-Object -Line).Lines
Chk 'repo:file-count' ($n -le 1500) "tracked=$n"

if ($fail -gt 0) { ''; "SUMMARY FAIL ($fail) —— 不推"; exit 1 }

# ---------- 4. 远端 ----------
$pushUrl = $RemoteUrl
if ($Token) {
    $pushUrl = $RemoteUrl -replace '^https://', ("https://" + $Token + "@")
}
$existing = @(git remote)
if ($existing -contains 'origin') { git remote set-url origin $pushUrl } else { git remote add origin $pushUrl }

git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { "FAIL  push 失败（检查仓库是否为空、分支名、PAT 权限）"; git remote set-url origin $RemoteUrl; exit 1 }
Chk 'push' $true "$RemoteUrl ($Branch)"

if ($Token) { git remote set-url origin $RemoteUrl; Chk 'remote:token-removed' $true 'origin 已改回无 token 的 URL' }

# ---------- 5. 源码包（只含提交内容）----------
New-Item -ItemType Directory -Force -Path (Join-Path $root 'dist') | Out-Null
$zip = Join-Path $root ('dist\novelapp-1.0.0-src.zip')
if (Test-Path $zip) { Remove-Item $zip -Force }
git archive --format=zip --prefix=novelapp-1.0.0/ -o $zip HEAD
$zi = Get-Item $zip
Chk 'archive' ($zi.Length -gt 0) ("{0} ({1:N0} KB)" -f $zi.Name, ($zi.Length / 1KB))
''
'SUMMARY PASS'
exit 0
