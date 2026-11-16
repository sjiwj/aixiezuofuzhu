# -*- coding: utf-8 -*-
import io, re
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()
start = s.find("def check_cast_absent(chs, cast):")
m = re.search(r"\ndef (check_time_span|# ---------- \u2461)", s[start + 10:])
if start < 0 or not m:
    print("range missing"); raise SystemExit(1)
end = start + 10 + m.start() + 1

NEW = '''def check_cast_absent(chs, cast):
    """用角色卡白名单查人物覆盖。

    只对两种情况报警：
      1. 主角在某章完全没出现（warn）
      2. 配角缺席超过一半章节（info）
    配角偶尔缺席不是问题，不报。
    """
    if not cast:
        return [], {"checked": False, "reason": "\u6ca1\u6709 \u8bbe\u5b9a\u5e93/\u89d2\u8272\u5361.md\uff0c\u67e5\u4e0d\u4e86\u4eba\u7269\u8986\u76d6"}
    pairs = []
    for item in cast:
        if isinstance(item, (list, tuple)):
            pairs.append((str(item[0]), bool(item[1])))
        else:
            pairs.append((str(item), False))
    per = []
    for no, fn, text in chs:
        per.append((no, fn, text))
    issues, detail = [], []
    total = len(per)
    for name, is_main in pairs:
        appear = [no for no, _fn, text in per if name in text]
        absent = [no for no, _fn, text in per if name not in text]
        detail.append({"name": name, "main": is_main, "appear": appear, "absent": absent})
        if not absent or len(appear) < 2:
            continue
        if is_main:
            issues.append({"rule": "cast_absent", "severity": "warn",
                           "message": "\u4e3b\u89d2\u300c%s\u300d\u5728 %s \u7ae0\u5b8c\u5168\u6ca1\u51fa\u73b0" % (name, "\u3001".join(absent))})
        elif len(absent) * 2 >= total:
            issues.append({"rule": "cast_absent", "severity": "info",
                           "message": "\u300c%s\u300d\u5728 %d/%d \u7ae0\u91cc\u6ca1\u51fa\u73b0\uff08\u8d85\u8fc7\u4e00\u534a\uff09" % (name, len(absent), total)})
    return issues, {"checked": True, "cast": len(pairs), "total_chapters": total, "detail": detail}
'''
s = s[:start] + NEW + chr(10) + chr(10) + s[end:]

# 输出用 detail
s = s.replace('            hit = d.get("appear") or []', '            hit = d.get("appear") or []')
s = s.replace('            print("   %-7s %d \u7ae0\uff1a%s" % (d["name"], len(hit), "\u3001".join(hit) if hit else "\u4e00\u7ae0\u90fd\u6ca1\u6709"))',
              '            tag = "\uff08\u4e3b\u89d2\uff09" if d.get("main") else ""' + chr(10) +
              '            print("   %s%s  %d \u7ae0\uff1a%s" % (d["name"], tag, len(hit), "\u3001".join(hit) if hit else "\u4e00\u7ae0\u90fd\u6ca1\u6709"))')

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("check_cast_absent rewritten")