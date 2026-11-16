$out = "D:\NovelApp\dsh-src\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked"
Write-Host "=== 部署两个文件（coordinator + server）==="
foreach ($f in @("coordinator.py", "server.py")) {
  Copy-Item "D:\NovelApp\core\$f" "$out\resources\core\$f" -Force
  $has = Test-Path "$out\resources\core\$f"
  Write-Host ("  " + $f + " -> " + $has)
}
Write-Host ("  coordinator 含 gateway_pricing: " + (Select-String -Path "$out\resources\core\coordinator.py" -Pattern "def gateway_pricing" -Quiet))
Write-Host ("  server 含 cny_per_1k_for: " + (Select-String -Path "$out\resources\core\server.py" -Pattern "def cny_per_1k_for" -Quiet))

Write-Host ""
Write-Host "=== 重启验证 live 价 ==="
Get-Process NovelApp -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
Remove-Item Env:ELECTRON_RUN_AS_NODE -EA SilentlyContinue
Start-Process -FilePath "$out\NovelApp.exe" | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $c = Get-NetTCPConnection -LocalPort 8770 -State Listen -EA SilentlyContinue
  if ($c) { Write-Host ("  8770 在听（" + ($i+1) + " 秒）"); break }
}
Start-Sleep -Seconds 2
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $r = Invoke-RestMethod "http://127.0.0.1:18760/api/polish/models" -TimeoutSec 20
  $sw.Stop()
  Write-Host ("  耗时: " + $sw.ElapsedMilliseconds + " ms  模型数: " + $r.models.Count)
  Write-Host ("  cny_basis: " + $r.cny_basis)
  Write-Host ""
  $r.models | ForEach-Object {
    Write-Host ("    " + $_.id.PadRight(16) + " " + [string]$_.cny_per_1k).PadRight(28) + " src=" + $_.cny_source
  }
} catch { Write-Host ("  ERR: " + $_.Exception.Message.Substring(0,[Math]::Min(60,$_.Exception.Message.Length))) }