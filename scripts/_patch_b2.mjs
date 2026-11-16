
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const BS = String.fromCharCode(92)
const bad = '.replace(/.md$/i, "")'
const good = '.replace(/' + BS + '.md$/i, "")'
if (s.includes(bad)) { s = s.split(bad).join(good); console.log('fixed regex'); }
fs.writeFileSync(p, s, 'utf8')

const b = 'D:/NovelApp/build.ps1'
let t = fs.readFileSync(b, 'utf8')
if (t.includes('APP_VERSION')) { console.log('build ALREADY') }
else {
  const eol = t.includes('\r\n') ? '\r\n' : '\n'
  const anchor = '    Write-Host ("    同步插件: " + (Get-ChildItem "$pluginSrc*.js" | Measure-Object).Count + " 个文件") -ForegroundColor DarkGray'
  if (!t.includes(anchor)) throw new Error('anchor')
  const add = [
    anchor,
    '    # 插件里的版本号跟随 $VERSION（关于页显示的就是这个），别手改',
    '    $plugClient = Join-Path $pluginDst "client.js"',
    '    if (Test-Path $plugClient) {',
    '      $pc = [IO.File]::ReadAllText($plugClient)',
    '      $pc = [regex]::Replace($pc, ' + "'const APP_VERSION = "[0-9.]+"'" + ', (' + "'const APP_VERSION = "' + '$VERSION' + '"'" + '))',
    '      [IO.File]::WriteAllText($plugClient, $pc)',
    '    }',
  ].join(eol)
  t = t.split(anchor).join(add)
  fs.writeFileSync(b, t, 'utf8')
  console.log('build.ps1 patched')
}
