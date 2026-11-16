$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
foreach ($f in @("stages.py","server.py","coordinator.py")) {
  Copy-Item "D:\NovelApp\core\$f" "$out\resources\core\$f" -Force
}
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$out\resources\preset-data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Copy-Item "D:\NovelApp\plugin\lib\index.js" "$env:APPDATA\novelapp-desktop\data\profiles\desktop\node_modules\novelapp-plugin\lib\index.js" -Force
Write-Host "已部署"

Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { break }
}
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "=== 验 missing 标记 ==="
try {
  $r = Invoke-RestMethod "http://127.0.0.1:18760/novelapp/stages?book=%E9%95%BF%E7%94%9F%E5%BD%93%E9%93%BA" -TimeoutSec 10
  if ($r.missing) {
    $r.missing.PSObject.Properties | ForEach-Object { Write-Host ("  " + $_.Name + ": missing=" + $_.Value) }
  } else { Write-Host "  ❌ 没有 missing 字段" }
} catch { Write-Host ("  ERR " + $_.Exception.Message.Substring(0,60)) }

Write-Host ""
Write-Host "=== 项目目录 ==="
Get-ChildItem "$env:APPDATA\novelapp-desktop\data\projects" -Directory | ForEach-Object { Write-Host ("  " + $_.Name) }