# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
s = io.open(p, encoding="utf-8").read()
if "nvl-debt" in s:
    print("ALREADY"); raise SystemExit
ANCHOR = '\t\t".nvl-dock--wide { width: 340px;'
i = s.find(ANCHOR)
if i < 0:
    print("anchor missing"); raise SystemExit(1)
CSS = chr(9) + chr(9) + chr(34) + ".nvl-debt { display: flex; flex-direction: column; gap: 2px; margin: 0 12px 6px; padding: 6px 10px; border-radius: 8px; background: var(--nvl-paper-2); border-left: 2px solid var(--nvl-accent); }" + chr(34) + "," + chr(10)
CSS += chr(9) + chr(9) + chr(34) + ".nvl-debt__head { font-size: 11px; color: var(--nvl-ink-3); margin-bottom: 2px; }" + chr(34) + "," + chr(10)
CSS += chr(9) + chr(9) + chr(34) + ".nvl-debt__row { display: flex; align-items: baseline; gap: 8px; font-size: 12px; line-height: 1.7; }" + chr(34) + "," + chr(10)
CSS += chr(9) + chr(9) + chr(34) + ".nvl-debt__kind { flex: 0 0 auto; font-size: 10.5px; color: var(--nvl-accent); }" + chr(34) + "," + chr(10)
CSS += chr(9) + chr(9) + chr(34) + ".nvl-debt__title { flex: 0 1 auto; color: var(--nvl-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" + chr(34) + "," + chr(10)
CSS += chr(9) + chr(9) + chr(34) + ".nvl-debt__why { flex: 1 1 auto; min-width: 0; font-size: 11px; color: var(--nvl-ink-3); }" + chr(34) + "," + chr(10)
s = s[:i] + CSS + s[i:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("debt CSS added")