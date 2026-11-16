$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 部署 ==="
Get-ChildItem "D:\NovelApp\core" -Filter "*.py" | ForEach-Object { Copy-Item $_.FullName "$out\resources\core\$($_.Name)" -Force }
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 25; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  8770 在听（" + ($i+1) + " 秒）"); break }
}

Write-Host ""
Write-Host "=== 润色（带 model）测试 ==="
$before = (Get-ChildItem "$env:APPDATA\novelapp-desktop\data\projects\<书名>" -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("  润色前项目总字节: " + $before)

$body = @{
  book = "<书名>"
  chapter = "003"
  text = "雾没散。他从铺子门口退出来，米袋在肩上搭着。新草鞋踩在湿草上，鞋底陷下去，又拔出来。没声。走十几步回头，那灯还亮着。黄黄的，不摇，像给雾钉进去的一根钉子。"
  scope = "selection"
  instruction = "更紧凑"
  model = "deepseek-v4-pro"
} | ConvertTo-Json -Compress

try {
  $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:18760/api/polish")
  $req.Method = "POST"; $req.ContentType = "application/json"; $req.Timeout = 60000
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
  $req.ContentLength = $bytes.Length
  $s1 = $req.GetRequestStream(); $s1.Write($bytes, 0, $bytes.Length); $s1.Close()
  $resp = $req.GetResponse()
  $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
  $texts = @()
  $start = $null; $usage = $null; $done = $null
  while (-not $sr.EndOfStream) {
    $line = $sr.ReadLine()
    if (-not $line -or -not $line.StartsWith("data:")) { continue }
    try {
      $d = $line.Substring(5).Trim() | ConvertFrom-Json
      if ($d.type -eq "start") { $start = $d }
      elseif ($d.type -eq "delta") { $texts += $d.text }
      elseif ($d.type -eq "usage") { $usage = $d }
      elseif ($d.type -eq "done") { $done = $d }
    } catch {}
  }
  $sr.Close(); $resp.Close()
  $result = -join $texts
  Write-Host ("  start.model: " + $start.model)
  Write-Host ("  usage: prompt=" + $usage.prompt_tokens + " completion=" + $usage.completion_tokens + " cny=" + $usage.total_cny)
  Write-Host ("  done: chars_in=" + $done.chars_in + " chars_out=" + $done.chars_out + " model=" + $done.model + " fallback=" + $done.model_fallback)
  Write-Host ""
  Write-Host ("  改后（" + $result.Length + " 字符）:")
  Write-Host ("    " + $result)
} catch {
  Write-Host ("  HTTP " + $_.Exception.Response.StatusCode.value__)
}

Start-Sleep -Seconds 1
$after = (Get-ChildItem "$env:APPDATA\novelapp-desktop\data\projects\<书名>" -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host ("=== 润色后项目总字节: " + $after + "  变化: " + ($after - $before) + " ===")