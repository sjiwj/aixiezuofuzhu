
import fs from 'node:fs'
const p = 'D:/NovelApp/build.ps1'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('APP_VERSION')) { console.log('build ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const anchor = "  Write-Host (\"    同步插件: \" + (Get-ChildItem \"$pluginSrc\*.js\" | Measure-Object).Count + \" 个文件\") -ForegroundColor DarkGray"
if (!s.includes(anchor)) throw new Error('sync anchor')
const add = [
  anchor,
  "  # 插件里的版本号跟随 $VERSION，别手改（关于页显示的就是这个）",
  "  $plugClient = Join-Path $pluginDst 'client.js'",
  "  if (Test-Path $plugClient) {",
  "    $pc = [IO.File]::ReadAllText($plugClient)",
  "    $pc = [regex]::Replace($pc, 'const APP_VERSION = \"[0-9.]+\"', ('const APP_VERSION = \"' + $VERSION + '\"'))",
  "    [IO.File]::WriteAllText($plugClient, $pc)",
  "  }",
].join(eol)
s = s.split(anchor).join(add)
fs.writeFileSync(p, s, 'utf8')
console.log('build.ps1: APP_VERSION 跟随 VERSION')
