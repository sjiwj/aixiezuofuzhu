$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 部署 client.js（199.7 KB）==="
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Write-Host "  已部署"

Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" -ArgumentList "--remote-debugging-port=9660" | Out-Null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 9660 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  CDP " + ($i+1) + " 秒"); break }
}
Start-Sleep -Seconds 8
foreach ($p in @(18760, 8770)) {
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  " + $p + " OK") } else { Write-Host ("  " + $p + " MISS") }
}

Write-Host ""
Write-Host "=== 基线（book_counts）==="
pwsh -NoProfile -File "D:\NovelApp\scripts\book_counts.ps1" 2>&1