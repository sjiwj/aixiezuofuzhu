# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()

# 输出：① 改成「人物覆盖」，并列出每个角色的出场章数
old = '    print("\u2460 \u79f0\u8c13\u6f02\u79fb  " + (\"''
i = s.find('    print("\u2460')
if i < 0:
    print("anchor 1 missing"); raise SystemExit(1)
j = s.find("    if td.get(\"gone\"):", i)
if j < 0:
    j = s.find("    ts = st[", i)
NEW = '''    if td.get("checked"):
        print("\u2460 \u4eba\u7269\u8986\u76d6  \u89d2\u8272\u5361 %d \u4eba" % td.get("cast", 0))
        for d in (td.get("detail") or [])[:8]:
            chs_hit = d.get("appear") or []
            print("   %-6s %d \u7ae0\uff1a%s" % (d["name"], len(chs_hit), "\u3001".join(chs_hit) if chs_hit else "\u4e00\u7ae0\u90fd\u6ca1\u6709"))
    else:
        print("\u2460 \u4eba\u7269\u8986\u76d6  " + str(td.get("reason", "")))
'''
s = s[:i] + NEW + s[j:]

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("output relabeled")