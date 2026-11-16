# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.join(os.environ.get("APPDATA") or "", "..", ""))
sys.path.insert(0, r"D:\NovelApp\scripts")
import oldbook_diagnose as D
data = os.path.join(os.environ["APPDATA"], "novelapp-desktop", "data", "projects", "\u957f\u751f\u5f53\u94fa", "\u7ae0\u8282")
chs = D.chapters_of(data)
print("chapters:", len(chs))
per = D.speakers_per_chapter(chs)
for no, fn, names in per:
    print(no, "->", sorted(names))
print()
# 专名轨道
half = max(1, len(chs)//2)
early = "".join(t for _n,_f,t in chs[:half])
late = "".join(t for _n,_f,t in chs[half:])
import re
props = re.findall(D.PROPER.pattern, early)
print("PROPER hits in early:", len(props), sorted(set(props))[:12])