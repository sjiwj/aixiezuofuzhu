# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
s = io.open(p, encoding="utf-8").read()
map_ = {
    "--nvl-fg": "--nvl-ink",
    "--nvl-muted": "--nvl-ink-3",
    "--nvl-hover": "--nvl-paper-3",
}
total = 0
for old, new in map_.items():
    n = s.count("var(" + old + ")")
    s = s.replace("var(" + old + ")", "var(" + new + ")")
    print("%-16s -> %-16s %d 处" % (old, new, n))
    total += n
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("total", total)