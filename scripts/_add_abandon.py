# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\scripts\l3_l4_check.py"
s = io.open(p, encoding="utf-8").read()
if "foreshadow_abandoned" in s:
    print("ALREADY"); sys.exit(0)

# 1) check_foreshadow 里识别「作废」并计数
old = '        status = str(r.get("\u72b6\u6001") or "").strip()'
if old not in s:
    print("anchor1 missing"); sys.exit(1)
new = old + chr(10) + \
      '        if status in ("\u4f5c\u5e9f", "\u5df2\u4f5c\u5e9f", "\u653e\u5f03", "\u4e22\u5f03", "drop", "abandoned"):' + chr(10) + \
      '            abandoned += 1' + chr(10) + \
      '            continue'
s = s.replace(old, new, 1)

# 2) 初始化 abandoned 计数
old2 = '    touched, stale = [], []'
if old2 in s:
    s = s.replace(old2, old2 + chr(10) + '    abandoned = 0', 1)

# 3) 返回值带上
old3 = '    return issues, {"foreshadow": len(rows), "foreshadow_touched": len(touched),'
if old3 in s:
    s = s.replace(old3, '    return issues, {"foreshadow": len(rows), "foreshadow_touched": len(touched),', 1)
old4 = '                    "foreshadow_stale": len(stale)}'
if old4 in s:
    s = s.replace(old4, '                    "foreshadow_stale": len(stale), "foreshadow_abandoned": abandoned}', 1)

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("foreshadow_abandoned added")