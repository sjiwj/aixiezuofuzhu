# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
s = io.open(p, encoding="utf-8").read()
if "InspireBox chapterInfo" in s or "h(InspireBox" in s:
    print("ALREADY"); sys.exit(0)

# 1) 在 WritingPane 的润色区之后插入 onTake 函数
fn = [
    "",
    "\t\t\t/* \u7075\u611f\u5c55\u5f00\u91c7\u7528\uff1a\u63d2\u5230\u5149\u6807\u5904\uff08\u6ca1\u5149\u6807\u5c31\u8ffd\u52a0\u5230\u672b\u5c3e\uff09\uff0c\u4e0d\u81ea\u52a8\u4fdd\u5b58 */",
    "\t\t\tconst takeInspire = function (seg) {",
    "\t\t\t\tconst area = areaRef.current;",
    "\t\t\t\tconst cur = String(textRef.current || \"\");",
    "\t\t\t\tlet at = cur.length;",
    "\t\t\t\tif (area && area.selectionStart != null) at = area.selectionStart;",
    "\t\t\t\tconst body = String(seg || \"\").trim();",
    "\t\t\t\tif (!body) return;",
    "\t\t\t\tconst next = cur.slice(0, at) + body + cur.slice(at);",
    "\t\t\t\tsetText(next);",
    "\t\t\t\ttry { textRef.current = next; } catch (e) { /* ignore */ }",
    "\t\t\t\tsetNote(\"\u5df2\u63d2\u5165\u7075\u611f\uff0c\u8bb0\u5f97\u70b9\u300c\u4fdd\u5b58\u300d\");",
    "\t\t\t\tif (area) { try { area.focus(); area.setSelectionRange(at + body.length, at + body.length); } catch (e2) { /* ignore */ } }",
    "\t\t\t};",
    "",
]
code = "\n".join(fn)
anchor = "\t\t\tconst clearSelection = function () {"
i = s.find(anchor)
if i < 0:
    print("anchor1 missing"); sys.exit(1)
s = s[:i] + code + s[i:]

# 2) 渲染：插在 nvl-editor__body 之前（WritingPane 里那个，取最后一个）
body_tag = "\t\t\t\th(\"div\", { className: \"nvl-editor__body\" },"
j = s.rfind(body_tag)
if j < 0:
    print("anchor2 missing"); sys.exit(1)
box = "\t\t\t\th(InspireBox, { chapterInfo: info, onTake: takeInspire })," + "\n" + "\t\t\t\t"
s = s[:j] + box + s[j:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("InspireBox mounted")