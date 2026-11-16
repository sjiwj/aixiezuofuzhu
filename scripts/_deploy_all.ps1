$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 部署全部 ==="
Get-ChildItem "D:\NovelApp\core" -Filter "*.py" | ForEach-Object { Copy-Item $_.FullName "$out\resources\core\$($_.Name)" -Force }
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Copy-Item "D:\NovelApp\config\layers.yaml" "$out\resources\config\layers.yaml" -Force
Write-Host ("  client.js " + [math]::Round((Get-Item "D:\NovelApp\plugin\lib\client.js").Length/1KB,1) + " KB")
Write-Host "  全部已部署"

Write-Host ""
Write-Host "=== 重启 ==="
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" -ArgumentList "--remote-debugging-port=9650" | Out-Null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 9650 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  CDP " + ($i+1) + " 秒"); break }
}
Start-Sleep -Seconds 8
foreach ($p in @(18760, 8770)) {
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  " + $p + " OK") } else { Write-Host ("  " + $p + " MISS") }
}
Write-Host ""
Write-Host "=== 项目目录 ==="
Get-ChildItem "$env:APPDATA\novelapp-desktop\data\projects" -Directory | ForEach-Object { Write-Host ("  " + $_.Name) }