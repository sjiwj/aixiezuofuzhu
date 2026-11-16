Write-Host "=== 停构建进程（排除自身）==="
$self = $PID
Get-Process pwsh -EA SilentlyContinue | Where-Object { $_.Id -ne $self -and $_.StartTime -gt (Get-Date).AddMinutes(-20) } | ForEach-Object {
  Write-Host ("  杀 pwsh " + $_.Id)
  Stop-Process -Id $_.Id -Force -EA SilentlyContinue
}
Get-Process node,dotnet -EA SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddMinutes(-20) } | ForEach-Object {
  Write-Host ("  杀 " + $_.ProcessName + " " + $_.Id)
  Stop-Process -Id $_.Id -Force -EA SilentlyContinue
}
Start-Sleep -Seconds 3
Write-Host ""
Write-Host "=== model_map 当前值 ==="
Select-String -Path "D:\NovelApp\core\coordinator.py" -Pattern "model_map" | ForEach-Object { Write-Host ("  L" + $_.LineNumber + ": " + $_.Line.Trim()) }
Write-Host ""
Write-Host "=== 产物状态 ==="
$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
if (Test-Path "$out\NovelApp.exe") {
  Write-Host "  win-unpacked 还在"
  Copy-Item "D:\NovelApp\core\coordinator.py" "$out\resources\core\coordinator.py" -Force
  Copy-Item "D:\NovelApp\core\server.py" "$out\resources\core\server.py" -Force
  Write-Host "  已部署修复"
} else { Write-Host "  win-unpacked 已被清（构建初期）" }