# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()
lines = s.split("\n")
bad = None
for i, ln in enumerate(lines):
    if ln.startswith("    head = '\u4f60\u662f\u300a%s\u300b"):
        bad = i
        break
if bad is None:
    print("not found")
    sys.exit(0)
print("bad at line", bad + 1)
print("ctx:", [repr(x) for x in lines[bad:bad + 3]])
new = [
    "    head = ('\u4f60\u662f\u300a%s\u300b\u7684\u4f5c\u8005\u3002\u4e0b\u9762\u662f\u4f60\u521a\u60f3\u5230\u7684\u4e00\u53e5\u8bdd\uff0c\u8bf7\u628a\u5b83\u5c55\u5f00\u6210\u4e00\u6bb5\u6b63\u6587\u3002'",
    "            + chr(10) + chr(10)",
    "            % (book or '\u8fd9\u672c\u4e66'))",
]
# 删掉原来的 3 行（head / 空行 / ' % (...)）
end = bad + 3
if lines[end - 1].strip().startswith("' % (book or"):
    lines[bad:end] = new
else:
    # 兜底：只替换 head 行与紧随的空行
    lines[bad:bad + 2] = new
io.open(p, "w", encoding="utf-8", newline="").write("\n".join(lines))
print("fixed")
