$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Write-Host "index.js 已部署"

Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { break }
}
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "=== 验 stages 流转校验 ==="
foreach ($t in @(@{from="draft";to="done"}, @{from="draft";to="working"}, @{from="working";to="done"}, @{from="awaiting";to="done"})) {
  $body = @{ book = "<书名>"; chapter = "001"; stage = $t.to; source = "manual"; action = "confirm" } | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod "http://127.0.0.1:18760/novelapp/stages" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 10
    Write-Host ("  " + $t.from + " -> " + $t.to + " => OK")
  } catch {
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host ("  " + $t.from + " -> " + $t.to + " => HTTP " + $code)
  }
}

Write-Host ""
Write-Host "=== 恢复 001 为 done ==="
$body2 = @{ book = "<书名>"; chapter = "001"; stage = "done"; source = "manual"; action = "confirm"; force = $true } | ConvertTo-Json -Compress
try {
  $r2 = Invoke-RestMethod "http://127.0.0.1:18760/novelapp/stages" -Method POST -Body $body2 -ContentType "application/json" -TimeoutSec 10
  Write-Host ("  " + $r2.stage)
} catch { Write-Host ("  HTTP " + $_.Exception.Response.StatusCode.value__) }

Write-Host ""
Write-Host "=== 文档 ==="
$doc = "D:\NovelApp\docs\前端对接清单.md"
if (Test-Path $doc) {
  Write-Host ("  " + (Get-Item $doc).Length + " 字节 / " + (Get-Content $doc).Count + " 行")
} else { Write-Host "  ❌ 不存在" }