# -*- coding: utf-8 -*-
"""借 StyleKit Editorial 的结构：圆角归 0（直角才是杂志排版的骨相）。"""
import io, os, re, sys
P = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()

# 圆角 token 强制归零
s = s.replace('"--nvl-radius-1: 2px;"', '"--nvl-radius-1: 0;"')
s = s.replace('"--nvl-radius-2: 4px;"', '"--nvl-radius-2: 0;"')
s = s.replace('"--nvl-radius-3: 8px;"', '"--nvl-radius-3: 0;"')
s = s.replace('"  --nvl-radius-1: 2px;"', '"  --nvl-radius-1: 0;"')
s = s.replace('"  --nvl-radius-2: 4px;"', '"  --nvl-radius-2: 0;"')
s = s.replace('"  --nvl-radius-3: 8px;"', '"  --nvl-radius-3: 0;"')

# 硬编码的 border-radius 值也归零（保留 999px 胶囊和 50%）
cnt = [0]
def snap(m):
    head, val, tail = m.group(1), m.group(2).strip(), m.group(3)
    if val in ("999px", "50%", "0", "0px") or val.startswith("var(--nvl-radius"):
        return m.group(0)
    cnt[0] += 1
    return head + "0" + tail
s = re.sub(r"(border-radius\s*:\s*)([0-9]+px)(\s*;)", snap, s)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("radius -> 0, hardcoded fixed:", cnt[0])
