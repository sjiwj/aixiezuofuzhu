# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()
if "def check_faded_names" not in s:
    print("anchor missing"); sys.exit(1)

NEW = """def check_faded_names(chs):
    \"\"\"消失的专名/人物。两条轨道：
      A 结构型专名（带地名后缀/书名号）—— 精度高、召回低
      B 说话人（「XX说/道/问」出现 >=3 次）—— 人物比专名可靠，是主要召回
    两条都要求「前半出现、后半完全消失」。
    \"\"\"
    if len(chs) < 3:
        return [], {"checked": False, "reason": "章节少于 3 章"}
    half = max(1, len(chs) // 2)
    early_raw = "".join(t for _n, _f, t in chs[:half])
    late_raw = "".join(t for _n, _f, t in chs[half:])
    early_text = strip_dialogue(early_raw)
    late_text = strip_dialogue(late_raw)

    issues, cands = [], []

    # 轨道 A：结构型专名（现在 PROPER 已是后缀型）
    cnt_a = {}
    for m in PROPER.finditer(early_text):
        w = m.group(0)
        cnt_a[w] = cnt_a.get(w, 0) + 1
    for w, c in sorted(cnt_a.items(), key=lambda x: -x[1]):
        if c >= 2 and late_text.count(w) == 0:
            cands.append({"name": w, "early": c, "track": "专名"})

    # 轨道 B：说话人（从原文本取，因为对话区才有「XX说」）
    cnt_b = {}
    for m in SPEAK.finditer(early_raw):
        w = m.group(1)
        cnt_b[w] = cnt_b.get(w, 0) + 1
    for w, c in sorted(cnt_b.items(), key=lambda x: -x[1]):
        if c >= 3 and late_raw.count(w) == 0:
            cands.append({"name": w, "early": c, "track": "说话人"})

    seen = set()
    for c in cands[:10]:
        if c["name"] in seen:
            continue
        seen.add(c["name"])
        issues.append({"rule": "faded_name", "severity": "info",
                       "message": "「%s」（%s）前半出现 %d 次，后半一次都没有" % (c["name"], c["track"], c["early"])})
    return issues, {"checked": True, "candidates": cands[:12]}
"""

start = s.find("def check_faded_names(chs):")
# 找到函数结束（下一个顶层 def 或 def diagnose）
nxt = s.find("def diagnose(dir_path):", start)
if start < 0 or nxt < 0:
    print("range missing"); sys.exit(1)
s = s[:start] + NEW + chr(10) + chr(10) + s[nxt:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("check_faded_names rewritten (2 tracks)")