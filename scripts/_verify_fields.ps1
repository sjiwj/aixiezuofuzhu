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
Write-Host "=== 验 breakdown-list path ==="
$r = Invoke-RestMethod "http://127.0.0.1:18760/novelapp/breakdown-list" -TimeoutSec 10
$r.items | ForEach-Object { Write-Host ("  " + $_.path + "  " + $_.chars + " 字") }

Write-Host ""
Write-Host "=== 验 promises chars ==="
$p = Invoke-RestMethod "http://127.0.0.1:18760/novelapp/promises?book=%E9%95%BF%E7%94%9F%E5%BD%93%E9%93%BA" -TimeoutSec 10
$p.items | Select-Object -First 3 | ForEach-Object { Write-Host ("  " + $_.title + "  chars=" + $_.chars) }