
import fs from 'node:fs'
const cur = 'D:/NovelApp/plugin/lib/index.js'
const ref = 'D:/NovelApp/_archive/restore/index-080.js'
const cl = fs.readFileSync(cur, 'utf8').split(/\r?\n/)
const rl = fs.readFileSync(ref, 'utf8').split(/\r?\n/)

const findIn = (arr, frag, from) => { for (let i = from || 0; i < arr.length; i++) if (arr[i].includes(frag)) return i; return -1 }

const ci = findIn(cl, "'/novelapp/setting-new'")
let ciEnd = -1
for (let k = ci + 1; k < ci + 30; k++) { if (cl[k] === '    }') { ciEnd = k; break } }
const r0 = findIn(cl, "'/novelapp/setting-branch-rename'")
if (r0 < 0) throw new Error('rename missing')
// 从 r0 向前取它的 if 行（上一行）
const blocksStart = r0 - 1
const mv = findIn(cl, "'/novelapp/setting-move'")
let mvEnd = -1
for (let k = mv; k < mv + 40; k++) { if (cl[k] === '    }') { mvEnd = k; break } }
if (mvEnd < 0) throw new Error('move end')
const si = findIn(cl, "'/novelapp/save')")
const ii = findIn(cl, "'/novelapp/import')")
const rsi = findIn(rl, "'/novelapp/save')")
const rii = findIn(rl, "'/novelapp/import')")
console.log('ci/ciEnd', ci + 1, ciEnd + 1, '| blocks', blocksStart + 1, mvEnd + 1, '| save', si + 1, '| import', ii + 1)
console.log('ref save', rsi + 1, 'ref import', rii + 1)

const blocks = cl.slice(blocksStart, mvEnd + 1)
const saveBlock = rl.slice(rsi, rii)
console.log('blocks lines', blocks.length, 'saveBlock lines', saveBlock.length)
console.log('saveBlock tail:', JSON.stringify(saveBlock.slice(-3)))

const out = [...cl.slice(0, ciEnd + 1), '', ...blocks, ...saveBlock, ...cl.slice(ii)]
fs.writeFileSync(cur, out.join('\n'), 'utf8')
console.log('rewritten, lines', out.length)
