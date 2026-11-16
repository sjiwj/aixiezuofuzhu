
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('if (tk) headers["X-Novelapp-Token"]')) { console.log('ALREADY'); process.exit(0) }
const old = [
  '\t\t\tres = await fetch(url, {',
  '\t\t\t\tmethod: "POST",',
  '\t\t\t\theaders: { "Content-Type": "application/json" },',
  '\t\t\t\tbody: JSON.stringify(body || {}),',
  '\t\t\t\tsignal: signal',
  '\t\t\t});',
].join('\n')
if (!s.includes(old)) throw new Error('streamSSE anchor')
const neu = [
  '\t\t\t/* 本地鉴权：SSE 也是 POST，必须带 X-Novelapp-Token（auth 改造时这里漏过） */',
  '\t\t\tlet tk = "";',
  '\t\t\ttry { tk = await nvlToken(); } catch (e0) { tk = ""; }',
  '\t\t\tconst sseHeaders = { "Content-Type": "application/json" };',
  '\t\t\tif (tk) sseHeaders["X-Novelapp-Token"] = tk;',
  '\t\t\tres = await fetch(url, {',
  '\t\t\t\tmethod: "POST",',
  '\t\t\t\theaders: sseHeaders,',
  '\t\t\t\tbody: JSON.stringify(body || {}),',
  '\t\t\t\tsignal: signal',
  '\t\t\t});',
].join('\n')
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('streamSSE: +X-Novelapp-Token')
