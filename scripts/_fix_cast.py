# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()

NEW = '''def load_cast(settings_dir):
    """从 设定库/角色卡.md 取角色名白名单。没有就返回空——不猜。"""
    p = os.path.join(settings_dir, "\u89d2\u8272\u5361.md")
    text = read(p)
    if not text:
        return []
    names = []
    for ln in text.split(chr(10)):
        st = ln.strip()
        m = re.match(r"^#+\\s*[\u4e00-\u9fa5]{0,3}\u3001\\s*([^\uff08(\\n]+)", st)
        if m:
            n = m.group(1).strip()
            if 2 <= len(n) <= 6:
                names.append(n)
    return list(dict.fromkeys(names))


def check_cast_absent(chs, cast):
    """用角色卡白名单查「某角色在哪些章完全缺席」。

    比瞎猜说话人可靠得多：名字是作者自己登记的。
    """
    if not cast:
        return [], {"checked": False, "reason": "没有 设定库/角色卡.md，查不了人物缺席"}
    per = []
    for no, fn, text in chs:
        present = [n for n in cast if n in text]
        per.append((no, fn, present))
    issues = []
    for n in cast:
        appear = [no for no, _fn, present in per if n in present]
        absent = [no for no, _fn, present in per if n not in present]
        if len(appear) >= 2 and absent:
            issues.append({"rule": "cast_absent", "severity": "info",
                           "message": "「%s」出现在 %s 章，但 %s 章完全没出现" % (n, "、".join(appear), "、".join(absent))})
    stats = {"checked": True, "cast": len(cast),
             "detail": [{"name": n, "appear": [no for no, _f, p2 in per if n in p2]} for n in cast]}
    return issues, stats
'''

start = s.find("def check_title_drift(chs):")
end = s.find("def check_time_span(") if False else s.find("# ---------- \u2461")
if start < 0:
    print("start missing"); raise SystemExit(1)
# 找到 check_title_drift 结束：下一个 def 之前
import re as _re
m = _re.search(r"\ndef (check_time_span|check_faded_names)\(", s[start:])
if not m:
    print("end missing"); raise SystemExit(1)
end = start + m.start() + 1
s = s[:start] + NEW + chr(10) + chr(10) + s[end:]

# diagnose 里换掉 ①
s = s.replace("    i1, s1 = check_title_drift(chs)",
              "    cast = load_cast(os.path.join(os.path.dirname(dir_path), \"\u8bbe\u5b9a\u5e93\"))" + chr(10) +
              "    i1, s1 = check_cast_absent(chs, cast)")
s = s.replace('    td = st["title_drift"]', '    td = st.get("title_drift") or st.get("cast_absent") or {}')

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("check_cast_absent added")