$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Write-Host ("client.js " + [math]::Round((Get-Item "D:\NovelApp\plugin\lib\client.js").Length/1KB,1) + " KB 已部署")

Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" -ArgumentList "--remote-debugging-port=9630" | Out-Null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 9630 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("CDP " + ($i+1) + " 秒"); break }
}
Start-Sleep -Seconds 8
Write-Host "启动完成"