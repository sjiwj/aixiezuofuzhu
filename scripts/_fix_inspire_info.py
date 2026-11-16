# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
s = io.open(p, encoding="utf-8").read()
old = "h(InspireBox, { chapterInfo: info, onTake: takeInspire }),"
if old not in s:
    print("anchor missing"); sys.exit(1)
new = "h(InspireBox, { chapterInfo: (path ? parseChapterPath(path) : null), onTake: takeInspire }),"
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("fixed chapterInfo")