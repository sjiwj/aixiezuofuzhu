import fs from 'node:fs'
const src = fs.readFileSync('D:/NovelApp/plugin/lib/src/parts/070-body.js', 'utf8')
const i = src.indexOf('function splitReviewItems(text) {')
const j = src.indexOf('\n\t\tfunction reviewItemList', i)
if (i < 0 || j < 0) { console.log('EXTRACT FAIL'); process.exit(1) }
const fnSrc = src.slice(i, j)
const factory = new Function(fnSrc + '\nreturn splitReviewItems;')
const split = factory()
const samples = [
  ['编号', '1. 主角动机不够，第二章就该让他主动问一句\n2. 老头的台词太文\n3. 结尾太快'],
  ['破折号+①', '- 开场缺环境\n- 银子数目前后不一致\n① 对话太密'],
  ['段落', '第一段他写得不错但节奏拖。\n\n好。\n\n第二段又太急，结尾没收住。'],
  ['空', '']
]
for (const [name, text] of samples) {
  const r = split(text)
  console.log(name + ' -> total=' + r.total + ' more=' + r.more + ' items=' + JSON.stringify(r.items.slice(0, 4)))
}
