$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Get-ChildItem "D:\NovelApp\core" -Filter "*.py" | ForEach-Object { Copy-Item $_.FullName "$out\resources\core\$($_.Name)" -Force }
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 25; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  8770 在听（" + ($i+1) + " 秒）"); break }
}

Write-Host "=== /api/polish/options ==="
try {
  $r = Invoke-RestMethod "http://127.0.0.1:18760/api/polish/options" -TimeoutSec 10
  Write-Host ("  ok=" + $r.ok + "  default=" + $r.default_model + "  models=" + $r.models.Count + "  presets=" + $r.presets.Count)
  Write-Host "  presets:"
  $r.presets | ForEach-Object { Write-Host ("    " + $_.id.PadRight(8) + " " + $_.label.PadRight(12) + " " + $_.instruction) }
} catch { Write-Host ("  HTTP " + $_.Exception.Response.StatusCode.value__) }

Write-Host ""
Write-Host "=== 三个端点都在 ==="
foreach ($ep in @("/api/polish/options", "/api/polish/presets", "/api/polish/models")) {
  try {
    $r2 = Invoke-RestMethod ("http://127.0.0.1:18760" + $ep) -TimeoutSec 10
    Write-Host ("  " + $ep + " -> ok=" + $r2.ok)
  } catch { Write-Host ("  " + $ep + " -> HTTP " + $_.Exception.Response.StatusCode.value__) }
}