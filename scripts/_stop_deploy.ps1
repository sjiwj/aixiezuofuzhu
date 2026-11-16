Write-Host "=== 停构建，清残留进程 ==="
Get-Process pwsh,node,dotnet -EA SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddMinutes(-15) } | ForEach-Object { Stop-Process -Id $_.Id -Force -EA SilentlyContinue }
Start-Sleep -Seconds 3
Write-Host "  已清"
Write-Host ""
Write-Host "=== 部署 model_map 修复 ==="
$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
if (Test-Path "$out\resources\core") {
  Copy-Item "D:\NovelApp\core\coordinator.py" "$out\resources\core\coordinator.py" -Force
  Copy-Item "D:\NovelApp\core\server.py" "$out\resources\core\server.py" -Force
  Write-Host "  已部署到产物"
} else { Write-Host "  产物被构建清了（正常）" }
Write-Host ""
Write-Host "=== model_map 当前值 ==="
Select-String -Path "D:\NovelApp\core\coordinator.py" -Pattern "model_map" | ForEach-Object { Write-Host ("  L" + $_.LineNumber + ": " + $_.Line.Trim()) }