# -*- coding: utf-8 -*-
"""间距收敛：把非 4 倍数的 padding/margin/gap 拉到 4 的倍数。"""
import io, os, re, sys, collections
P = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()

changes = []
def snap(v, prop):
    """把 px 值吸到最近的 4 的倍数（0/1/2 这类小值保留）。"""
    try:
        n = float(v.replace("px", ""))
    except ValueError:
        return None
    if n <= 3:
        return None
    snapped = int(round(n / 4.0) * 4)
    if snapped == int(n):
        return None
    return "%dpx" % snapped

PROPS = ["padding", "margin", "gap", "row-gap", "column-gap"]
PAT = re.compile(r"\b(padding|margin|gap|row-gap|column-gap)\s*:\s*([^;\"}]*)")

def repl(m):
    prop, val = m.group(1), m.group(2)
    parts = val.split()
    out = []
    for p in parts:
        mm = re.match(r"^(-?)(\d+(?:\.\d+)?)px$", p)
        if mm:
            sign, num = mm.group(1), mm.group(2)
            ns = snap(num + "px", prop)
            if ns:
                changes.append((prop + ": " + val.strip(), ns))
                out.append(sign + ns)
                continue
        out.append(p)
    return prop + ": " + " ".join(out)

new = PAT.sub(repl, s)
print("snapped:", len(changes))
for a, b in changes[:12]:
    print("  %-46s -> %s" % (a[:44], b))

if "--apply" in sys.argv and changes:
    io.open(TMP, "w", encoding="utf-8", newline="").write(new)
    os.replace(TMP, P)
    print("written")