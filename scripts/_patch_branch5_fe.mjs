
import fs from 'node:fs'
const fp = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(fp, 'utf8')
if (s.includes('branchesOf')) { console.log('frontend ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const oldFn = [
  '\t\tfunction splitSettingBranches(items) {',
  '\t\t\tconst order = [];',
  '\t\t\tconst map = {};',
  '\t\t\t(items || []).forEach(function (it) {',
].join(eol)
const neuFn = [
  '\t\tfunction splitSettingBranches(items, branches) {',
  '\t\t\tconst order = [];',
  '\t\t\tconst map = {};',
  '\t\t\t/* 先建空分支（刚建好还没文件的也要看得见），再填文件 */',
  '\t\t\t(branches || []).forEach(function (name) {',
  '\t\t\t\tif (!name) return;',
  '\t\t\t\tif (!map[name]) { map[name] = { label: name, kind: "docs", branch: name, items: [] }; order.push(name); }',
  '\t\t\t});',
  '\t\t\t(items || []).forEach(function (it) {',
].join(eol)
if (!s.includes(oldFn)) throw new Error('splitSettingBranches anchor fail')
s = s.split(oldFn).join(neuFn)

const oldCall = '\t\t\t\t].concat(splitSettingBranches(docItems)));'
const neuCall = [
  '\t\t\t\t].concat(splitSettingBranches(docItems, (docs.ok && docs.data && docs.data.branches) || [])));',
].join(eol)
if (!s.includes(oldCall)) throw new Error('call anchor fail')
s = s.split(oldCall).join(neuCall)
fs.writeFileSync(fp, s, 'utf8')
console.log('frontend: 空分支也显示')
