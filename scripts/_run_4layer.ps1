$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 启动 v0.7.7 产物 ==="
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  8770 在听（" + ($i+1) + " 秒）"); break }
}

Write-Host ""
Write-Host "=== 记录对账前状态 ==="
python -X utf8 -c "
import sqlite3
con = sqlite3.connect(r"D:\relay\data\new-api.db")
cur = con.cursor()
cur.execute("SELECT COUNT(*), COALESCE(SUM(quota),0) FROM logs WHERE type=2")
r = cur.fetchone()
print("  总请求数: %s  总 quota: %s" % (r[0], r[1]))
con.close()
" 2>&1

Write-Host ""
Write-Host "=== 跑第 6 章（完整四层）==="
$body = @{ book = "<书名>"; chapter = "006"; stream = $true; mode = "replace" } | ConvertTo-Json -Compress
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:18760/api/write")
  $req.Method = "POST"; $req.ContentType = "application/json"; $req.Timeout = 300000
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
  $req.ContentLength = $bytes.Length
  $s1 = $req.GetRequestStream(); $s1.Write($bytes, 0, $bytes.Length); $s1.Close()
  $resp = $req.GetResponse()
  $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
  $texts = @(); $events = @{}; $start = $null; $usage = $null; $done = $null; $err = $null
  $firstByte = $null; $firstContent = $null
  while (-not $sr.EndOfStream) {
    $line = $sr.ReadLine()
    if (-not $line -or -not $line.StartsWith("data:")) { continue }
    if (-not $firstByte) { $firstByte = $sw.ElapsedMilliseconds }
    try {
      $d = $line.Substring(5).Trim() | ConvertFrom-Json
      $t = $d.type
      $events[$t] = 1 + $(if ($events[$t]) { $events[$t] } else { 0 })
      if ($t -eq "start") { $start = $d }
      elseif ($t -eq "delta" -and $d.kind -eq "content") {
        if (-not $firstContent) { $firstContent = $sw.ElapsedMilliseconds }
        $texts += $d.text
      }
      elseif ($t -eq "usage") { $usage = $d }
      elseif ($t -eq "done") { $done = $d }
      elseif ($t -eq "error") { $err = $d }
    } catch {}
  }
  $sr.Close(); $resp.Close()
  $sw.Stop()
  $result = -join $texts
  Write-Host ""
  Write-Host "=== 结果 ==="
  Write-Host ("  首字节: " + $firstByte + " ms")
  Write-Host ("  首正文: " + $firstContent + " ms")
  Write-Host ("  总时长: " + [math]::Round($sw.ElapsedMilliseconds/1000, 1) + " 秒")
  Write-Host ("  正文字符: " + $result.Length)
  Write-Host ("  事件: " + (($events.GetEnumerator() | ForEach-Object { $_.Key + "=" + $_.Value }) -join ", "))
  if ($start.context) { Write-Host ("  context.hit: " + ($start.context | ConvertTo-Json -Compress -Depth 3)) }
  if ($usage) { Write-Host ("  usage: prompt=" + $usage.prompt_tokens + " completion=" + $usage.completion_tokens + " cny=" + $usage.total_cny) }
  if ($done) { Write-Host ("  done: chars=" + $done.chars + " path=" + $done.path + " commit=" + $done.commit.ok) }
  if ($err) { Write-Host ("  ERROR: " + $err.message) }
  Write-Host ""
  Write-Host "=== 正文前 200 字 ==="
  Write-Host ("  " + $result.Substring(0, [Math]::Min(200, $result.Length)).Replace("`n", " "))
} catch {
  Write-Host ("  HTTP " + $_.Exception.Response.StatusCode.value__)
  try {
    $sr2 = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
    $t2 = $sr2.ReadToEnd()
    Write-Host ("  body: " + $t2.Substring(0, [Math]::Min(600, $t2.Length)))
  } catch {}
}