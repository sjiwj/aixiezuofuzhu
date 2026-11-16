$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 部署 ==="
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Write-Host ("  client.js " + [math]::Round((Get-Item "D:\NovelApp\plugin\lib\client.js").Length/1KB,1) + " KB")

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
Write-Host "=== 版本号 ==="
Select-String -Path "D:\NovelApp\plugin\lib\src\parts\010-bootstrap.js" -Pattern "0\.7\.\d" -EA SilentlyContinue | Select-Object -First 2 | ForEach-Object { Write-Host ("  " + $_.Line.Trim()) }
Select-String -Path "D:\NovelApp\package.json" -Pattern "\"version\"" -EA SilentlyContinue | ForEach-Object { Write-Host ("  " + $_.Line.Trim()) }