$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 部署 ==="
Copy-Item "D:\NovelApp\core\server.py" "$out\resources\core\server.py" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Write-Host "  已部署 server.py + index.js"
Write-Host ""
Write-Host "=== 重启 ==="
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  8770 在听（" + ($i+1) + " 秒）"); break }
}

Write-Host ""
Write-Host "=== 测 setting-doc 拆书库（空 book）==="
foreach ($path in @("拆书库/推荐书单.md", "拆书库/README.md", "设定库/角色卡.md")) {
  try {
    $enc = [uri]::EscapeDataString($path)
    $r = Invoke-RestMethod "http://127.0.0.1:18760/novelapp/setting-doc?path=$enc" -TimeoutSec 10
    Write-Host ("  " + $path + " -> OK title=" + $r.title + " chars=" + $r.chars)
  } catch {
    Write-Host ("  " + $path + " -> HTTP " + $_.Exception.Response.StatusCode.value__)
  }
}

Write-Host ""
Write-Host "=== 测 dry_run（不落盘）==="
$f = "$env:APPDATA\novelapp-desktop\data\projects\<书名>\章节\009-第9章.md"
$before = if (Test-Path $f) { (Get-Item $f).LastWriteTime } else { "不存在" }
Write-Host ("  dry_run 前: " + $before)

$body = @{ book = "<书名>"; chapter = "009"; stream = $true; mode = "replace"; dry_run = $true } | ConvertTo-Json -Compress
try {
  $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:18760/api/write")
  $req.Method = "POST"; $req.ContentType = "application/json"; $req.Timeout = 300000
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
  $req.ContentLength = $bytes.Length
  $s1 = $req.GetRequestStream(); $s1.Write($bytes, 0, $bytes.Length); $s1.Close()
  $resp = $req.GetResponse()
  $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
  $texts = @(); $done = $null; $start = $null
  while (-not $sr.EndOfStream) {
    $line = $sr.ReadLine()
    if (-not $line -or -not $line.StartsWith("data:")) { continue }
    try {
      $d = $line.Substring(5).Trim() | ConvertFrom-Json
      if ($d.type -eq "start") { $start = $d }
      elseif ($d.type -eq "delta" -and $d.kind -eq "content") { $texts += $d.text }
      elseif ($d.type -eq "done") { $done = $d }
    } catch {}
  }
  $sr.Close(); $resp.Close()
  $result = -join $texts
  Write-Host ("  start.dry_run: " + $start.dry_run)
  Write-Host ("  正文: " + $result.Length + " 字符")
  Write-Host ("  done.dry_run: " + $done.dry_run + "  chars: " + $done.chars)
  Write-Host ("  done 有 commit: " + ($done.PSObject.Properties.Name -contains "commit"))
  if ($done.next) { Write-Host ("  next.options: " + (($done.next.options | ForEach-Object { $_.id }) -join ", ")) }
} catch {
  Write-Host ("  HTTP " + $_.Exception.Response.StatusCode.value__)
}

$after = if (Test-Path $f) { (Get-Item $f).LastWriteTime } else { "不存在" }
Write-Host ("  dry_run 后: " + $after)
if ($before -eq $after) { Write-Host "  ✅ 未写盘" } else { Write-Host "  ❌ 被写了" }