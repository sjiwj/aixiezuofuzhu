# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()

# load_cast 返回 (名字, 是否主角)
old = "        if m:" + chr(10) + "            n = m.group(1).strip()" + chr(10) + "            if 2 <= len(n) <= 6:" + chr(10) + "                names.append(n)"
if old in s:
    new = ("        if m:" + chr(10) +
           "            n = m.group(1).strip()" + chr(10) +
           "            tail = st[m.end():]" + chr(10) +
           "            is_main = (\"\u4e3b\u89d2\" in tail) and (\"\u914d\u89d2\" not in tail)" + chr(10) +
           "            if 2 <= len(n) <= 6:" + chr(10) +
           "                names.append((n, is_main))")
    s = s.replace(old, new, 1)

# check_cast_absent 只对主角/高缺席率报警
old2 = '    for n in cast:'
i2 = s.find(old2)
if i2 > 0:
    j2 = s.find("    stats = {", i2)
    block_new = '''    for item in cast:
        if isinstance(item, (list, tuple)):
            n, is_main = item[0], bool(item[1])
        else:
            n, is_main = item, False
        appear = [no for no, _fn, present in per if n in present]
        absent = [no for no, _fn, present in per if n not in present]
        if not absent or len(appear) < 2:
            continue
        if is_main:
            issues.append({"rule": "cast_absent", "severity": "warn",
                           "message": "\u4e3b\u89d2\u300c%s\u300d\u5728 %s \u7ae0\u5b8c\u5168\u6ca1\u51fa\u73b0" % (n, "\u3001".join(absent))})
        elif len(absent) >= max(3, len(per) // 2):
            issues.append({"rule": "cast_absent", "severity": "info",
                           "message": "\u300c%s\u300d\u5728 %d \u7ae0\u91cc\u6ca1\u51fa\u73b0\uff08\u8d85\u8fc7\u4e00\u534a\uff09" % (n, len(absent))})
'''
    s = s[:i2] + block_new + s[j2:]

# per 里的 cast 名字要兼容 tuple
s = s.replace("        present = [n for n in cast if n in text]",
              "        present = [c[0] if isinstance(c, (list, tuple)) else c for c in cast if (c[0] if isinstance(c, (list, tuple)) else c) in text]")

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("cast_absent -> main only + high-absence")