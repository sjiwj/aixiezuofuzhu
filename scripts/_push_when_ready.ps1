# 等仓库出现 → 自动推送 → 建 Release v1.0.0 → 复检
# 用法: 你点完 GitHub 的「Create repository」，本脚本自动接手（无需再确认）
$ErrorActionPreference = 'Continue'
$repo = 'D:\NovelApp'
$owner = 'sjiwj'
$name = 'novelapp'
$api = "https://api.github.com/repos/$owner/$name"
$logDir = Join-Path $repo 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("publish-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
function Say($m) { $line = "{0} {1}" -f (Get-Date -Format 'HH:mm:ss'), $m; Write-Output $line; Add-Content -LiteralPath $log -Value $line -Encoding UTF8 }

# 取凭据（不进日志）
$raw = "protocol=https`nhost=github.com`n" | git credential fill 2>$null
$tok = ($raw | Select-String '^password=' | ForEach-Object { $_.Line -replace '^password=', '' })
if (-not $tok) { Say 'FAIL no-credential'; exit 2 }
$hdr = @{ Authorization = "token $tok"; 'User-Agent' = 'novelapp-publish'; Accept = 'application/vnd.github+json' }
Say "START watching $owner/$name (token len=$($tok.Length))"

$exists = $false
for ($i = 1; $i -le 180; $i++) {
    try { $r = Invoke-WebRequest -Uri $api -Headers $hdr -TimeoutSec 10 -UseBasicParsing; if ($r.StatusCode -eq 200) { $exists = $true; break } } catch {}
    if ($i % 12 -eq 0) { Say "waiting... $([int]($i*5))s" }
    Start-Sleep -Seconds 5
}
if (-not $exists) { Say 'FAIL repo-not-created-in-15min'; exit 3 }
Say 'REPO_FOUND'

Set-Location $repo
$env:GIT_TERMINAL_PROMPT = '0'

# 1) 自检（与 _publish.ps1 同口径）
$novel = @(git grep -I -n -E '<书名>|沈砚|刘家庄|具状人' HEAD -- . ':(exclude)scripts/_publish.ps1' 2>$null).Count
$secret = @(git grep -I -n -E 'sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}' HEAD -- . 2>$null).Count
$forbid = @(git ls-tree -r --name-only HEAD | Select-String '^(projects/|docs/plan/|_tmp/|发布|dsh-src/|.*\.db$|.*\.bak-)').Count
Say "CHECK novel=$novel secret=$secret forbidden=$forbid"
if ($novel -or $secret -or $forbid) { Say 'FAIL self-check'; exit 4 }

# 2) push
if ((git remote) -notcontains 'origin') { git remote add origin "https://github.com/$owner/$name.git" }
git push -u origin main 2>&1 | ForEach-Object { Say "  git: $_" }
if ($LASTEXITCODE -ne 0) { Say 'FAIL push'; exit 5 }
Say 'PUSHED'

# 3) 复检远端
$head = git rev-parse --short HEAD
$remote = (git ls-remote origin main) -split "`t" | Select-Object -First 1
Say "REMOTE_HEAD=$($remote.Substring(0,7)) LOCAL_HEAD=$head"

# 4) Release + 资产
$zip = Join-Path $repo 'dist\novelapp-1.0.0-src.zip'
$notesFile = Join-Path $repo '_tmp\release-notes-v1.0.0.md'
$body = if (Test-Path $notesFile) { Get-Content $notesFile -Raw -Encoding UTF8 } else { 'v1.0.0' }
$payload = @{ tag_name = 'v1.0.0'; name = 'v1.0.0'; body = $body; draft = $false; prerelease = $false } | ConvertTo-Json -Depth 4
$hf = Join-Path $env:TEMP ('ghhdr_' + [guid]::NewGuid().ToString('N') + '.txt')
Set-Content -Path $hf -Value ("Authorization: token {0}" -f $tok) -Encoding ASCII
try {
    $resp = Invoke-WebRequest -Uri "$api/releases" -Method Post -Headers $hdr -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 30 -UseBasicParsing
    $rel = $resp.Content | ConvertFrom-Json
    Say "RELEASE_CREATED=$($rel.html_url)"
    if (Test-Path $zip) {
        $up = "https://uploads.github.com/repos/$owner/$name/releases/$($rel.id)/assets?name=$([IO.Path]::GetFileName($zip))"
        curl.exe -s -X POST -H "@$hf" -H "Content-Type: application/zip" --data-binary "@$zip" $up | Out-Null
        Say "ASSET_UPLOADED=$([IO.Path]::GetFileName($zip))"
    }
} catch {
    Say "RELEASE_FAIL $($_.Exception.Message)"
} finally {
    Remove-Item $hf -Force -ErrorAction SilentlyContinue
}
Say 'DONE'
