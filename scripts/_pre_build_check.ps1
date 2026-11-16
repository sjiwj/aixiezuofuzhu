$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\client.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\client.js" -Force
Write-Host ("client.js " + [math]::Round((Get-Item "D:\NovelApp\plugin\lib\client.js").Length/1KB,1) + " KB 已部署")

Write-Host ""
Write-Host "=== 打包清单核对（backend 提醒的三个文件）==="
foreach ($f in @("core\coordinator.py", "core\server.py", "plugin\lib\index.js")) {
  $src = "D:\NovelApp\$f"
  if (Test-Path $src) {
    $st = Get-Item $src
    Write-Host ("  " + $f + "  " + [math]::Round($st.Length/1KB,1) + " KB  " + $st.LastWriteTime)
  } else { Write-Host ("  ❌ " + $f) }
}
Write-Host ""
Write-Host "=== model_map 确认 ==="
Select-String -Path "D:\NovelApp\core\coordinator.py" -Pattern ".model_map.:" | ForEach-Object { Write-Host ("  " + $_.Line.Trim()) }
Write-Host ""
Write-Host "=== config 打包清单 ==="
Select-String -Path "D:\NovelApp\build.ps1" -Pattern "cfgFiles" -Context 0,1 | ForEach-Object { Write-Host ("  " + $_.Line.Trim()) }