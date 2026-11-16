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
Write-Host ""
Write-Host "=== GET /api/polish/models ==="
try {
  $r = Invoke-RestMethod "http://127.0.0.1:18760/api/polish/models" -TimeoutSec 10
  Write-Host ("  ok=" + $r.ok + "  default=" + $r.default)
  $r.models | ForEach-Object {
    Write-Host ("    " + $_.id + "  " + $_.label + "  " + $_.cny_per_1k + " 元/千字  " + $_.speed)
  }
} catch { Write-Host ("  HTTP " + $_.Exception.Response.StatusCode.value__) }