Write-Host "=== 重启 8770（让新配置生效）==="
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  8770 在听（" + ($i+1) + " 秒）"); break }
}
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "=== 确认 writing 层配置（后端视角）==="
try {
  $r = Invoke-RestMethod "http://127.0.0.1:18760/api/layers" -TimeoutSec 10
  $r.layers | Where-Object { $_.id -eq "writing" } | ForEach-Object {
    Write-Host ("  model=" + $_.model + "  label=" + $_.label)
  }
} catch {
  Write-Host ("  /api/layers 失败: " + $_.Exception.Message.Substring(0,[Math]::Min(50,$_.Exception.Message.Length)))
  try {
    $r2 = Invoke-RestMethod "http://127.0.0.1:18760/api/config" -TimeoutSec 10
    Write-Host ("  workers.writing.model = " + $r2.workers.writing.model)
  } catch {}
}

Write-Host ""
Write-Host "=== 第 7 章有没有落盘（机检未过）==="
$f7 = "$env:APPDATA\novelapp-desktop\data\projects\<书名>\章节\007-第7章.md"
if (Test-Path $f7) { Write-Host ("  存在: " + (Get-Item $f7).Length + " 字节") } else { Write-Host "  不存在（机检拦住了，正常）" }