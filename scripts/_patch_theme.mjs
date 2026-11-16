
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/040-theme.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('TOKENS_LIGHT')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) 把现有 TOKENS 改名 TOKENS_DARK，并追加 TOKENS_LIGHT
const start = s.indexOf('const TOKENS = [')
const endMark = '].join("\\n");'
const end = s.indexOf(endMark, start)
if (start < 0 || end < 0) throw new Error('TOKENS block')
const darkBlock = s.slice(start, end + endMark.length).replace('const TOKENS = [', 'const TOKENS_DARK = [')
const light = [
  '/* 浅色主题：取样自 Laper（v2.0.2）截图 —— 近无彩色、冷灰白、靠层次而不是颜色 */',
  'const TOKENS_LIGHT = [',
  '  "--nvl-paper: #f8faf9;",',
  '  "--nvl-paper-2: #eff1f0;",',
  '  "--nvl-paper-3: #e6e9e8;",',
  '  "--nvl-rule: #dfe3e1;",',
  '  "--nvl-ink: #171a19;",',
  '  "--nvl-ink-2: #454a48;",',
  '  "--nvl-ink-3: #7c8380;",',
  '  "--nvl-accent: #8a6540;",',
  '  "--nvl-accent-ink: #ffffff;",',
  '  "--nvl-accent-soft: rgba(138, 101, 64, 0.10);",',
  '  "--nvl-focus: #a47b4e;",',
  '  "--nvl-bg: #f8faf9;",',
  '  "--nvl-pass: #1f7a4d;",',
  '  "--nvl-fail: #b23f36;",',
  '  "--nvl-inconclusive: #7c8380;",',
  '  "--nvl-stage-draft: var(--nvl-ink-3);",',
  '  "--nvl-stage-working: var(--nvl-accent);",',
  '  "--nvl-stage-awaiting: #a97516;",',
  '  "--nvl-stage-blocked: #b23f36;",',
  '  "--nvl-stage-done: #1f7a4d;",',
  '  "--nvl-ok: #1f7a4d;",',
  '  "--nvl-warn: #9a6b12;",',
  '  "--nvl-err: #b23f36;",',
  '  "--nvl-space-1: 4px;",',
  '  "--nvl-space-2: 8px;",',
  '  "--nvl-space-3: 12px;",',
  '  "--nvl-space-4: 16px;",',
  '  "--nvl-space-5: 24px;",',
  '  "--nvl-space-6: 32px;",',
  '  "--nvl-radius-1: 6px;",',
  '  "--nvl-radius-2: 10px;",',
  '  "--nvl-radius-3: 14px;",',
  '  "--nvl-text-xs: 12px;",',
  '  "--nvl-text-sm: 14px;",',
  '  "--nvl-text-md: 16px;",',
  '  "--nvl-text-lg: 18px;",',
  '  "--nvl-hit: 44px;",',
  '  "--nvl-font-ui: -apple-system, \"Segoe UI\", \"Microsoft YaHei\", sans-serif;",',
  '  "--nvl-font-data: Consolas, \"Cascadia Mono\", \"Courier New\", monospace;",',
  '  "--nvl-shadow-1: 0 1px 2px rgba(23,26,25,.05);",',
  '  "--nvl-shadow-2: 0 6px 24px rgba(23,26,25,.10);"',
  '].join("\\n");',
].join(eol)
s = s.slice(0, start) + darkBlock + eol + eol + light + s.slice(end + endMark.length)

// 2) 让 :root 用默认（深色），并加浅色选择器
const rootLine = '":root { " + TOKENS + " }",'
if (!s.includes(rootLine)) throw new Error('root line')
const newRoot = [
  '":root, html[data-nvl-theme=\"dark\"] { " + TOKENS_DARK + " }",',
  '"html[data-nvl-theme=\"light\"] { " + TOKENS_LIGHT + " }",',
  '"@media (prefers-color-scheme: light) { html:not([data-nvl-theme=\"dark\"]) { " + TOKENS_LIGHT + " } }",',
].join(eol)
s = s.split(rootLine).join(newRoot)
fs.writeFileSync(p, s, 'utf8')
console.log('theme: +TOKENS_LIGHT + 两套切换')
