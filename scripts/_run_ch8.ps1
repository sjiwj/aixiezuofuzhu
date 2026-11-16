Write-Host "=== 跑第 8 章（flash + 无思考，产物配置已更新）==="
$body = @{ book = "<书名>"; chapter = "008"; stream = $true; mode = "replace" } | ConvertTo-Json -Compress
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:18760/api/write")
  $req.Method = "POST"; $req.ContentType = "application/json"; $req.Timeout = 300000
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
  $req.ContentLength = $bytes.Length
  $s1 = $req.GetRequestStream(); $s1.Write($bytes, 0, $bytes.Length); $s1.Close()
  $resp = $req.GetResponse()
  $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
  $texts = @(); $start = $null; $usage = $null; $done = $null; $err = $null
  $firstByte = $null; $firstContent = $null; $deltaN = 0; $reasonN = 0
  while (-not $sr.EndOfStream) {
    $line = $sr.ReadLine()
    if (-not $line -or -not $line.StartsWith("data:")) { continue }
    if (-not $firstByte) { $firstByte = $sw.ElapsedMilliseconds }
    try {
      $d = $line.Substring(5).Trim() | ConvertFrom-Json
      if ($d.type -eq "start") { $start = $d }
      elseif ($d.type -eq "delta") {
        if ($d.kind -eq "content") {
          if (-not $firstContent) { $firstContent = $sw.ElapsedMilliseconds }
          $texts += $d.text; $deltaN++
        } elseif ($d.kind -eq "reasoning") { $reasonN++ }
      }
      elseif ($d.type -eq "usage") { $usage = $d }
      elseif ($d.type -eq "done") { $done = $d }
      elseif ($d.type -eq "error") { $err = $d }
    } catch {}
  }
  $sr.Close(); $resp.Close(); $sw.Stop()
  $result = -join $texts
  Write-Host ""
  Write-Host "=== 结果 ==="
  Write-Host ("  模型: " + $start.model)
  Write-Host ("  首字节: " + $firstByte + " ms")
  Write-Host ("  首正文: " + $firstContent + " ms")
  Write-Host ("  总时长: " + [math]::Round($sw.ElapsedMilliseconds/1000, 1) + " 秒")
  Write-Host ("  正文: " + $result.Length + " 字符（" + $deltaN + " 块）  思考: " + $reasonN + " 块")
  if ($usage) { Write-Host ("  usage: prompt=" + $usage.prompt_tokens + " completion=" + $usage.completion_tokens + " cny=" + $usage.total_cny) }
  if ($done) { Write-Host ("  done: chars=" + $done.chars + " commit=" + $done.commit.ok) }
  if ($err) { Write-Host ("  ERROR: " + $err.message) }
  Write-Host ""
  Write-Host "=== 正文前 150 字 ==="
  Write-Host ("  " + $result.Substring(0, [Math]::Min(150, $result.Length)).Replace("`n", " "))
} catch {
  Write-Host ("  HTTP " + $_.Exception.Response.StatusCode.value__)
}