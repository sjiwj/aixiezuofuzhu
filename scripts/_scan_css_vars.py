# -*- coding: utf-8 -*-
import io, re
p = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
s = io.open(p, encoding="utf-8").read()
# 1) 定义了哪些
defined = set(re.findall(r'"(--nvl-[a-z0-9\-]+):', s))
# 2) 用到了哪些
used = set(re.findall(r"var\((--nvl-[a-z0-9\-]+)\)", s))
missing = sorted(used - defined)
print("defined:", len(defined))
print("used:", len(used))
print("MISSING:", len(missing))
for m in missing:
    cnt = s.count("var(" + m + ")")
    print("  %-22s used %d times" % (m, cnt))