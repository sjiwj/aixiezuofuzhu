import fs from 'node:fs'
const src = fs.readFileSync('D:/NovelApp/plugin/lib/src/parts/070-body.js', 'utf8')
const i = src.indexOf('function splitReviewItems(text) {')
const j = src.indexOf('\n\t\tfunction reviewItemList', i)
const fnSrc = src.slice(i, j)
const split = new Function(fnSrc + '\nreturn splitReviewItems;')()
const samples = [
  ['编号三条(每条>6字)', '1. 主角动机不够，第二章就该让他主动问一句\n2. 老头的台词太文绉绉，不像市井人\n3. 结尾太快，收尾应该多给一个动作'],
  ['破折号三条', '- 开场缺少环境，读者不知道在哪\n- 银子数目前后不一致，前面说四十文\n① 对话太密，连着八句没有动作'],
  ['短条目应被丢', '1. 好。\n2. 这一条够长了应该保留下来\n3. 行'],
  ['续行合并', '1. 第一条意见写到一半\n   接着又写了一行补充说明\n2. 第二条是完整的'],
]
for (const [name, text] of samples) {
  const r = split(text)
  console.log(name + ' -> total=' + r.total + ' | ' + JSON.stringify(r.items))
}
