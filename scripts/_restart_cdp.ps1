Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" -ArgumentList "--remote-debugging-port=9690" | Out-Null
for ($i = 0; $i -lt 40; $i++) { Start-Sleep -Seconds 1; $c = Get-NetTCPConnection -LocalPort 9690 -State Listen -EA SilentlyContinue; if ($c) { break } }
Start-Sleep -Seconds 6
Write-Host "启动完成"