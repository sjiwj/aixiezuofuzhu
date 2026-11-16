# 书/章数快照：用于「点确定前 / 点确定后」对比，防止 K1 串书写坏别的书
# 用法: pwsh -File scripts/book_counts.ps1            # 打印当前快照
#       pwsh -File scripts/book_counts.ps1 -Since 5   # 额外列出最近 5 分钟内被改动的章节文件
param([int]$Since = 0)
$root = Join-Path $env:APPDATA 'novelapp-desktop\data\projects'
$api = 'http://127.0.0.1:18760/novelapp/projects'
$snap = @()
try {
  $p = Invoke-RestMethod $api -TimeoutSec 5
  foreach ($b in $p.books) { $snap += [pscustomobject]@{ book = $b.name; chapters = $b.chapters } }
} catch {
  Write-Host ('API_FAIL ' + $_.Exception.Message)
}
$snap | Sort-Object book | ForEach-Object { Write-Host ('BOOK ' + $_.book + ' chapters=' + $_.chapters) }
Write-Host ('TOTAL_BOOKS=' + $snap.Count)
if ($Since -gt 0 -and (Test-Path $root)) {
  $cut = (Get-Date).AddMinutes(-$Since)
  $recent = Get-ChildItem $root -Recurse -File -Filter '*.md' -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -gt $cut -and $_.FullName -notmatch '\.bak' }
  foreach ($f in $recent) { Write-Host ('RECENT ' + $f.FullName.Replace($root, '') + ' ' + $f.Length + 'B ' + $f.LastWriteTime.ToString('HH:mm:ss')) }
}
