
import fs from 'node:fs'
const fp = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
const ref = 'D:/NovelApp/_archive/restore/client-079.js'
const parts = fs.readFileSync(fp, 'utf8')
const refTxt = fs.readFileSync(ref, 'utf8')
function blockAt(lines, start) {
  let j = -1
  for (let k = start + 1; k < lines.length; k++) { if (lines[k] === '\t\t\t});') { j = k; break } }
  return lines.slice(start, j + 1).join('\n')
}
function find(lines) {
  const out = []
  for (let i = 0; i < lines.length; i++) if (lines[i] === '\t\t\tconst rows = [];') out.push(i)
  return out
}
const L = parts.split(/\r?\n/)
const R = refTxt.split(/\r?\n/)
const pi = find(L), ri = find(R)
console.log('parts blocks at', pi, '| ref at', ri)
pi.forEach((i, n) => {
  const same = ri[n] != null && blockAt(L, i) === blockAt(R, ri[n])
  console.log('block', n, 'start', i, 'sameAsRef:', same, 'hasToggle:', blockAt(L, i).includes('toggleGroup'), 'hasBooks:', blockAt(L, i).includes('books.length'))
})
