# -*- coding: utf-8 -*-
# 发布前自检：仓库密钥扫描 + 网关连通 + 渠道 key 前缀核对（不打印完整密钥）
# 用法: pwsh -NoProfile -File scripts\_check_keys.ps1 [-Repo D:\NovelApp] [-Gateway http://127.0.0.1:3000]
param(
    [string]$Repo = 'D:\NovelApp',
    [string]$Gateway = 'http://127.0.0.1:3000'
)
$ErrorActionPreference = 'Continue'
$fail = 0
function Chk($name, $ok, $detail) {
    if ($ok) { "PASS  $name  | $detail" } else { "FAIL  $name  | $detail"; $script:fail++ }
}

# ---------- 1. 仓库密钥扫描 ----------
$scanDirs = @('core', 'web', 'config', 'docs', 'scripts', 'data', '发布', '发布桌面版', 'prompts') |
    ForEach-Object { Join-Path $Repo $_ } | Where-Object { Test-Path $_ }
$pat = 'sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}'
$hits = @()
foreach ($d in $scanDirs) {
    $hits += Get-ChildItem $d -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -lt 3MB -and $_.FullName -notmatch '\.bak-secret-' -and $_.Extension -match '^\.(json|py|ps1|js|md|txt|yml|yaml|html|cmd|bat|ini|toml)$' } |
        Select-String -Pattern $pat -ErrorAction SilentlyContinue
}
if ($hits.Count -eq 0) {
    Chk 'repo:no-live-secret' $true "扫描 $($scanDirs.Count) 个目录，命中 0"
} else {
    $hits | Select-Object -First 10 | ForEach-Object {
        $m = [regex]::Match($_.Line, $pat).Value
        "      $($_.Path):$($_.LineNumber)  ->  $($m.Substring(0, [Math]::Min(7, $m.Length)))…"
    }
    Chk 'repo:no-live-secret' $false "命中 $($hits.Count) 处（见上）"
}

# ---------- 2. 所有 key 类字段必须为空 ----------
$scanner = Join-Path $Repo 'scripts\_scan_key_fields.py'
if (Test-Path $scanner) {
    $out = & python -X utf8 $scanner 2>&1
    $ok = ($LASTEXITCODE -eq 0)
    Chk 'repo:key-fields-empty' $ok (($out | Select-Object -First 1) -join '')
    if (-not $ok) { $out | Select-Object -Skip 1 -First 6 | ForEach-Object { "      $_" } }
} else {
    Chk 'repo:key-fields-empty' $false '缺少 scripts\_scan_key_fields.py'
}

# ---------- 3. 网关连通（用应用自己的令牌，不打印）----------
$tokFile = Join-Path $env:APPDATA 'novelapp-desktop\data\config\user_token.json'
if (Test-Path $tokFile) {
    $tok = (Get-Content $tokFile -Raw -Encoding UTF8 | ConvertFrom-Json)
    $key = $tok.key; if (-not $key) { $key = $tok.token }
    if ($key) {
        try {
            $r = Invoke-WebRequest "$Gateway/v1/models" -Headers @{ Authorization = "Bearer $key" } -TimeoutSec 8 -UseBasicParsing
            $n = (($r.Content | ConvertFrom-Json).data | Measure-Object).Count
            Chk 'gateway:models-200' ($r.StatusCode -eq 200) "HTTP $($r.StatusCode)，模型 $n 个（令牌前缀 $($key.Substring(0,[Math]::Min(7,$key.Length)))…）"
        } catch {
            Chk 'gateway:models-200' $false "探测失败：$($_.Exception.Message)"
        }
    } else {
        Chk 'gateway:models-200' $false '令牌文件里没有 key/token 字段'
    }
} else {
    Chk 'gateway:models-200' $false "找不到令牌文件：$tokFile（先在应用里登录）"
}

# ---------- 3b. 真调用探针（/v1/models 200 不等于上游 key 活着）----------
if ($key) {
    $body = '{"model":"deepseek-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":8}'
    $tmpf = Join-Path $env:TEMP ('chat_' + [guid]::NewGuid().ToString('N') + '.json')
    Set-Content -Path $tmpf -Value $body -Encoding UTF8
    $code = & curl.exe -s -o NUL -w "%{http_code}" -X POST "$Gateway/v1/chat/completions" -H "Content-Type: application/json" -H "Authorization: Bearer $key" --data-binary "@$tmpf" --max-time 25
    Remove-Item $tmpf -Force -ErrorAction SilentlyContinue
    Chk 'gateway:chat-probe' ("$code" -eq '200') "真调用 HTTP $code（401/403 = 上游 key 失效；/v1/models 200 不代表能写）"
}
# ---------- 4. 渠道表核对（前缀 + 长度，不打印完整 key）----------
$db = 'D:\relay\data\new-api.db'
if (Test-Path $db) {
    $py = @'
import sqlite3, sys
p = r"D:\relay\data\new-api.db"
con = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
cur = con.cursor()
try:
    cur.execute("select id,name,substr(key,1,7),length(key),status from channels order by id")
    for r in cur.fetchall():
        print("%s|%s|%s|%s|%s" % r)
except Exception as e:
    print("ERR|%s" % e)
con.close()
'@
    $tmp = Join-Path $env:TEMP ('chk_' + [guid]::NewGuid().ToString('N') + '.py')
    Set-Content -Path $tmp -Value $py -Encoding UTF8
    $out = & python -X utf8 $tmp 2>&1
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    $bad = @($out | Where-Object { $_ -match '^ERR\|' })
    if ($bad.Count) {
        Chk 'gateway:channels' $false ("读取失败：" + ($bad -join '; '))
    } else {
        $enabled = @($out | Where-Object { ($_ -split '\|')[4] -eq '1' })
        "      channels: " + (($out | ForEach-Object { $p2 = $_ -split '\|'; "id=$($p2[0]) $($p2[1]) key=$($p2[2])… len=$($p2[3]) status=$($p2[4])" }) -join ' ; ')
        Chk 'gateway:channels' ($enabled.Count -gt 0) "启用渠道 $($enabled.Count) 个"
    }
} else {
    Chk 'gateway:channels' $true '无本地网关 DB，跳过'
}

''
'SUMMARY ' + $(if ($fail -eq 0) { 'PASS' } else { "FAIL ($fail)" })
exit $(if ($fail -eq 0) { 0 } else { 1 })
