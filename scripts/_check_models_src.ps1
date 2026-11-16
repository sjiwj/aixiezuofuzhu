Write-Host "=== 确认产物会带新代码 ==="
Write-Host ("  源码 mtime: " + (Get-Item "D:\NovelApp\core\server.py").LastWriteTime)
Write-Host ("  含 POLISH_MODELS: " + (Select-String -Path "D:\NovelApp\core\server.py" -Pattern "POLISH_MODELS" -Quiet))
Write-Host ("  含 glm-5.3: " + (Select-String -Path "D:\NovelApp\core\server.py" -Pattern "glm-5\.3" -Quiet))
Write-Host ("  含 kimi-k3: " + (Select-String -Path "D:\NovelApp\core\server.py" -Pattern "kimi-k3" -Quiet))
Write-Host ""
Write-Host "=== POLISH_MODELS 定义 ==="
$c = Get-Content "D:\NovelApp\core\server.py"
$i = ($c | Select-String -Pattern "^POLISH_MODELS" | Select-Object -First 1).LineNumber
if ($i) { $c[($i-1)..([Math]::Min($i+30, $c.Count-1))] | ForEach-Object { Write-Host ("  " + $_) } }