# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
s = io.open(p, encoding="utf-8").read()
if "nvl-debt" in s:
    print("ALREADY"); raise SystemExit

# 1) WritingPane 里加 state（第 3083 行的 note 之后）
lines = s.split(chr(10))
target = None
for i, ln in enumerate(lines):
    if i > 3050 and 'const [note, setNote] = useState("");' in ln:
        target = i
        break
if target is None:
    print("state anchor missing"); raise SystemExit(1)
lines.insert(target + 1, chr(9)*3 + 'const [debt, setDebt] = useState(null);')
s = chr(10).join(lines)

# 2) useEffect：切章时拉读债
ANCHOR = '\t\t\t/* \u7075\u611f\u5c55\u5f00\u91c7\u7528\uff1a\u63d2\u5230\u5149\u6807\u5904'
i = s.find(ANCHOR)
if i < 0:
    # \u515c\u5e95\uff1a\u63d2\u5728 takeInspire \u4e4b\u524d
    i = s.find("const takeInspire = function (seg) {")
    if i < 0:
        print("effect anchor missing"); raise SystemExit(1)

EFFECT = chr(9)*3 + '/* \u8bfb\u503a\uff1a\u5207\u7ae0\u65f6\u62c9\u300c\u672c\u7ae0\u5fc5\u987b\u52a8\u7684\u8d26\u300d\uff0c\u8bfb\u8def\u5f84\u5148\u4e8e\u5199\u8def\u5f84 */' + chr(10)
EFFECT += chr(9)*3 + 'useEffect(function () {' + chr(10)
EFFECT += chr(9)*4 + 'const info = path ? parseChapterPath(path) : null;' + chr(10)
EFFECT += chr(9)*4 + 'if (!info || !info.book) { setDebt(null); return; }' + chr(10)
EFFECT += chr(9)*4 + 'let gone = false;' + chr(10)
EFFECT += chr(9)*4 + 'fetch(apiBase().replace(/\\/+$/, "") + "/api/debt?book=" + encodeURIComponent(info.book) + "&chapter=" + encodeURIComponent(info.key || "001"), { headers: authHeaders() })' + chr(10)
EFFECT += chr(9)*5 + '.then(function (r) { return r.ok ? r.json() : null; })' + chr(10)
EFFECT += chr(9)*5 + '.then(function (j) { if (!gone && j && j.ok) setDebt(j); })' + chr(10)
EFFECT += chr(9)*5 + '.catch(function () { if (!gone) setDebt(null); });' + chr(10)
EFFECT += chr(9)*4 + 'return function () { gone = true; };' + chr(10)
EFFECT += chr(9)*3 + '}, [path]);' + chr(10) + chr(10)
s = s[:i] + EFFECT + s[i:]

# 3) \u6e32\u67d3\uff1a\u5728 nvl-editor__bar \u4e4b\u540e\u63d2\u4e00\u6761\u8bfb\u503a\u63d0\u793a
BAR = '\t\t\t\th(InspireBox, { chapterInfo: (path ? parseChapterPath(path) : null), onTake: takeInspire }),'
j = s.find(BAR)
if j < 0:
    print("render anchor missing"); raise SystemExit(1)

RENDER = chr(9)*3 + '(debt && debt.must_touch && debt.must_touch.length ? h("div", { className: "nvl-debt" },' + chr(10)
RENDER += chr(9)*4 + 'h("div", { className: "nvl-debt__head" }, debt.summary || "\u672c\u7ae0\u5fc5\u987b\u52a8\u7684\u8d26"),' + chr(10)
RENDER += chr(9)*4 + 'debt.must_touch.map(function (it, i2) {' + chr(10)
RENDER += chr(9)*5 + 'return h("div", { key: i2, className: "nvl-debt__row" },' + chr(10)
RENDER += chr(9)*6 + 'h("span", { className: "nvl-debt__kind" }, it.kind),' + chr(10)
RENDER += chr(9)*6 + 'h("span", { className: "nvl-debt__title" }, it.title),' + chr(10)
RENDER += chr(9)*6 + 'h("span", { className: "nvl-debt__why" }, it.why));' + chr(10)
RENDER += chr(9)*4 + '})) : null),'
s = s[:j] + RENDER + chr(10) + s[j:]

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("debt UI added")