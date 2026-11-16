Write-Host "=== 当前所有功能清单 ==="
Write-Host ""
Write-Host "左栏:"
$r = Invoke-RestMethod "http://127.0.0.1:18760/novelapp/status?book=%E9%95%BF%E7%94%9F%E5%BD%93%E9%93%BA" -TimeoutSec 10
Write-Host ("  项目 / 码字 / 设定库 / 拆书库 / 审稿 / 更多")
Write-Host ("  当前书: 5 章 / " + $r.chars + " 字 / 承诺 " + $r.promises.total)
Write-Host ""
Write-Host "挂件三 tab:"
Write-Host "  章节 / 承诺 / 信息差"
Write-Host ""
Write-Host "润色:"
Write-Host "  2 个模型 / 5 个预设 / 三端点"
Write-Host ""
Write-Host "写章（只在项目面板）:"
Write-Host "  四层流水线 + 资料门槛 + 防覆盖 + 决策点"
Write-Host ""
Write-Host "=== 章节状态 ==="
$st = Get-Content "$env:APPDATA\novelapp-desktop\data\projects\<书名>\章节\.stages.json" -Raw | ConvertFrom-Json
foreach ($k in @("001","002","003","004","005")) {
  if ($st.$k) { Write-Host ("  " + $k + ": " + $st.$k.stage) }
}