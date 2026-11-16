$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
$src = "D:\NovelApp\plugin\lib\client.js"
Write-Host ("=== client.js " + [math]::Round((Get-Item $src).Length/1KB,1) + " KB ===")
Copy-Item $src "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item $src "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" -ArgumentList "--remote-debugging-port=9700" | Out-Null
for ($i = 0; $i -lt 40; $i++) { Start-Sleep -Seconds 1; $c = Get-NetTCPConnection -LocalPort 9700 -State Listen -EA SilentlyContinue; if ($c) { Write-Host ("  CDP 9700（" + ($i+1) + " 秒）"); break } }
Start-Sleep -Seconds 8
foreach ($p in @(18760, 8770)) {
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  " + $p + " OK") } else { Write-Host ("  " + $p + " MISS") }
}