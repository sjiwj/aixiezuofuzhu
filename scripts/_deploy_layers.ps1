Write-Host "=== 对比两份 layers.yaml ==="
$src = "D:\NovelApp\config\layers.yaml"
$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked\resources\config\layers.yaml"
Write-Host ("  源码: " + (Get-Item $src).LastWriteTime + "  " + (Get-Item $src).Length + " 字节")
if (Test-Path $out) {
  Write-Host ("  产物: " + (Get-Item $out).LastWriteTime + "  " + (Get-Item $out).Length + " 字节")
  Write-Host ""
  Write-Host "=== 产物里的 writing 层 ==="
  $lines = Get-Content $out
  $s = -1
  for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match "^  writing:") { $s = $i; break } }
  if ($s -ge 0) { for ($i = $s; $i -lt [Math]::Min($s+10, $lines.Count); $i++) { Write-Host ("    " + $lines[$i]) } }
} else { Write-Host "  产物不存在" }

Write-Host ""
Write-Host "=== 部署源码配置到产物 ==="
Copy-Item $src $out -Force
Write-Host "  已复制"

Write-Host ""
Write-Host "=== 重启验证 ==="
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$unp = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$unp\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { break }
}
Start-Sleep -Seconds 2
try {
  $r = Invoke-RestMethod "http://127.0.0.1:18760/api/layers" -TimeoutSec 10
  $r.layers | Where-Object { $_.id -eq "writing" } | ForEach-Object { Write-Host ("  writing.model = " + $_.model) }
} catch { Write-Host ("  /api/layers 失败") }