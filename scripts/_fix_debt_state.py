# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
s = io.open(p, encoding="utf-8").read()
lines = s.split(chr(10))

# 1) 删掉错位置的（3084 附近，在 WritingPane 之前）
del_at = None
for i, ln in enumerate(lines):
    if "const [debt, setDebt] = useState(null);" in ln and i < 4000:
        del_at = i
        break
if del_at is None:
    print("del anchor missing"); raise SystemExit(1)
lines.pop(del_at)
print("removed at line", del_at + 1)

# 2) 插到 WritingPane 里（4029 之后的第一个 const [note, setNote]）
wp = None
for i, ln in enumerate(lines):
    if "function WritingPane()" in ln:
        wp = i
        break
if wp is None:
    print("WritingPane missing"); raise SystemExit(1)
ins_at = None
for i in range(wp, min(wp + 80, len(lines))):
    if 'const [note, setNote] = useState("");' in lines[i]:
        ins_at = i + 1
        break
if ins_at is None:
    print("note anchor missing"); raise SystemExit(1)
lines.insert(ins_at, chr(9)*3 + "const [debt, setDebt] = useState(null);")
print("inserted at line", ins_at + 1)

s = chr(10).join(lines)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("done")