$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 冷启动 v0.7.7 ==="
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" -ArgumentList "--remote-debugging-port=9640" | Out-Null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 9640 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  CDP " + ($i+1) + " 秒"); break }
}
Start-Sleep -Seconds 8
foreach ($p in @(18760, 8770)) {
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  " + $p + " OK") } else { Write-Host ("  " + $p + " MISS") }
}
Write-Host ""
Write-Host "=== 润色模型（6 个，live 价）==="
try {
  $r = Invoke-RestMethod "http://127.0.0.1:18760/api/polish/models" -TimeoutSec 15
  $r.models | ForEach-Object { Write-Host ("  " + $_.id.PadRight(16) + " " + $_.cny_per_1k + " 元/千字  src=" + $_.cny_source) }
} catch { Write-Host ("  ERR " + $_.Exception.Message.Substring(0,50)) }