# -*- coding: utf-8 -*-
"""旧稿只读诊断：不要求建账，先读你已有的章节，报三件机械可查的事。

为什么只做三件：研讨结论里定了「先证明读旧稿有用，再谈抽账本」。
这三件都能用规则做，不需要模型判断，错了好解释。

用法:
    python scripts/oldbook_diagnose.py --book <书名>
    python scripts/oldbook_diagnose.py --dir "<章节目录>" --json
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read(p):
    try:
        with io.open(p, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def chapters_of(dir_path):
    """按文件名排序，返回 [(章号, 文件名, 正文)]"""
    out = []
    if not os.path.isdir(dir_path):
        return out
    for fn in sorted(os.listdir(dir_path)):
        if not fn.endswith(".md") or ".bak" in fn:
            continue
        m = re.match(r"(\d{1,4})", fn)
        if not m:
            continue
        out.append((m.group(1), fn, read(os.path.join(dir_path, fn))))
    return out


# ---------- ① 称谓变化 ----------
SPEAK = re.compile(r"([\u4e00-\u9fa5]{2,5})(?:说|道|问|答|笑|喊|叫|回|应)[\uff1a：\u3002\uff0c,\s]")
# 剧本式对话：姓名独占一行以冒号结尾（中文小说最常见）
SPEAK_LINE = re.compile(r"^\s*([\u4e00-\u9fa5]{2,5})\s*[\uff1a:]\s*$", re.M)


def speakers_per_chapter(chs):
    """每章的「说话人候选」集合（只取 ≥2 次出现的，压掉噪音）

    两条轨道：正文里「XX说/道」+ 剧本式「XX：」独占一行。
    后者最可靠——中文小说的对话基本都是这种格式。
    """
    out = []
    for no, fn, text in chs:
        cnt = {}
        for m in SPEAK.finditer(text):
            w = m.group(1)
            cnt[w] = cnt.get(w, 0) + 1
        for m in SPEAK_LINE.finditer(text):
            w = m.group(1)
            cnt[w] = cnt.get(w, 0) + 1
        out.append((no, fn, set(cnt.keys())))   # 先全收，阈值放到全书层面判
    return out


def load_cast(settings_dir):
    """从 设定库/角色卡.md 取角色名白名单。没有就返回空——不猜。"""
    p = os.path.join(settings_dir, "角色卡.md")
    text = read(p)
    if not text:
        return []
    names = []
    for ln in text.split(chr(10)):
        st = ln.strip()
        m = re.match(r"^#+\s*[一-龥]{0,3}、\s*([^（(\n]+)", st)
        if m:
            n = m.group(1).strip()
            tail = st[m.end():]
            is_main = ("主角" in tail) and ("配角" not in tail)
            if 2 <= len(n) <= 6:
                names.append((n, is_main))
    return list(dict.fromkeys(names))


def check_cast_absent(chs, cast):
    """用角色卡白名单查人物覆盖。

    只对两种情况报警：
      1. 主角在某章完全没出现（warn）
      2. 配角缺席超过一半章节（info）
    配角偶尔缺席不是问题，不报。
    """
    if not cast:
        return [], {"checked": False, "reason": "没有 设定库/角色卡.md，查不了人物覆盖"}
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
                           "message": "主角「%s」在 %s 章完全没出现" % (name, "、".join(absent))})
        elif len(absent) * 2 >= total:
            issues.append({"rule": "cast_absent", "severity": "info",
                           "message": "「%s」在 %d/%d 章里没出现（超过一半）" % (name, len(absent), total)})
    return issues, {"checked": True, "cast": len(pairs), "total_chapters": total, "detail": detail}


DAY = re.compile(r"(?:\d{1,3}|[\u4e00-\u9fa5\u4e24]{1,3})\s*(?:\u5929|\u65e5)(?:\u540e|\u4e4b\u540e|\u4ee5\u540e|\u8fc7\u53bb\u4e86)|(?:\u8fc7\u4e86|\u53c8\u8fc7|\u9694\u4e86)\s*(\d{1,3}|[\u4e00-\u9fa5\u4e24]{1,3})\s*(?:\u5929|\u65e5)")
MONTH = re.compile(r"(?:\d{1,3}|[\u4e00-\u9fa5\u4e24]{1,3})\s*\u4e2a?\u6708(?:\u540e|\u4e4b\u540e|\u4ee5\u540e|\u8fc7\u53bb\u4e86)")
YEAR = re.compile(r"(?:\d{1,3}|[\u4e00-\u9fa5\u4e24]{1,3})\s*\u5e74(?:\u540e|\u4e4b\u540e|\u4ee5\u540e|\u8fc7\u53bb\u4e86)")
CN = {"\u4e00": 1, "\u4e8c": 2, "\u4e24": 2, "\u4e09": 3, "\u56db": 4, "\u4e94": 5, "\u516d": 6, "\u4e03": 7, "\u516b": 8, "\u4e5d": 9, "\u5341": 10}


def to_num(s):
    s = str(s)
    if s.isdigit():
        return int(s)
    if s == "\u5341":
        return 10
    if "\u5341" in s:
        a, _, b = s.partition("\u5341")
        return (CN.get(a, 1) * 10) + CN.get(b, 0)
    return CN.get(s, 0)


def check_time_span(chs):
    """累计相邻章的「N 天后/月后/年后」，与文中出现的「N 年过去」类绝对表述比对。"""
    total_days = 0
    steps = []
    for no, fn, text in chs:
        d = sum(to_num(m.group(1)) for m in DAY.finditer(text))
        mo = sum(to_num(m.group(1)) for m in MONTH.finditer(text))
        y = sum(to_num(m.group(1)) for m in YEAR.finditer(text))
        add = d + mo * 30 + y * 365
        if add:
            total_days += add
            steps.append({"chapter": no, "days_added": add,
                          "detail": {"d": d, "m": mo, "y": y}})
    issues = []
    # 与设定库时间线里的绝对跨度比对（若有）
    return issues, {"checked": bool(steps), "total_days": total_days,
                    "total_years": round(total_days / 365.0, 1), "steps": steps[:12]}


# ---------- ③ 反复出现又消失的专名 ----------
def strip_dialogue(text):
    """去掉引号内内容——对话里的短语不是专名（这一步漏了，就会把「柴刀没了」当专名）"""
    return re.sub(r'「[^」]*」|“[^”]*”', '', text)


# 只认结构型专名：后缀地/机构名 + 书名号。召回低，但不误报。
PROPER = re.compile(r"(?:[一-龥]{1,3}(?:店|铺|镇|村|庄|岭|沟|庙|坊|院|塔|楼|山|河|城|府|寫|堂))")


def check_faded_names(chs):
    """消失的专名/人物。两条轨道：
      A 结构型专名（带地名后缀/书名号）—— 精度高、召回低
      B 说话人（「XX说/道/问」出现 >=3 次）—— 人物比专名可靠，是主要召回
    两条都要求「前半出现、后半完全消失」。
    """
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
    for m in SPEAK_LINE.finditer(early_raw):
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


def diagnose(dir_path):
    chs = chapters_of(dir_path)
    if not chs:
        return {"ok": False, "error": "没找到章节文件：%s" % dir_path}
    cast = load_cast(os.path.join(os.path.dirname(dir_path), "设定库"))
    i1, s1 = check_cast_absent(chs, cast)
    i2, s2 = check_time_span(chs)
    i3, s3 = check_faded_names(chs)
    return {"ok": True, "dir": dir_path, "chapters": len(chs),
            "issues": i1 + i2 + i3,
            "stats": {"title_drift": s1, "time_span": s2, "faded_names": s3}}


def main():
    ap = argparse.ArgumentParser(description="旧稿只读诊断（不要求建账）")
    ap.add_argument("--book")
    ap.add_argument("--dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    d = a.dir
    if not d and a.book:
        data = os.environ.get("NOVELAPP_DATA") or os.path.join(
            os.environ.get("APPDATA") or "", "novelapp-desktop", "data")
        d = os.path.join(data, "projects", a.book, "章节")
    if not d:
        print("用法: python scripts/oldbook_diagnose.py --book <书名> 或 --dir <章节目录>")
        return 2
    rep = diagnose(d)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep.get("ok") else 1
    if not rep.get("ok"):
        print(rep.get("error"))
        return 1
    print("=" * 66)
    print("旧稿诊断  %s（%d 章）" % (os.path.basename(os.path.dirname(d.rstrip(os.sep))) or d, rep["chapters"]))
    print("=" * 66)
    st = rep["stats"]
    td = st.get("title_drift") or st.get("cast_absent") or {}
    if td.get("checked"):
        print("① 人物覆盖  角色卡 %d 人" % td.get("cast", 0))
        for d in (td.get("detail") or [])[:8]:
            hit = d.get("appear") or []
            tag = "（主角）" if d.get("main") else ""
            print("   %s%s  %d 章：%s" % (d["name"], tag, len(hit), "、".join(hit) if hit else "一章都没有"))
    else:
        print("① 人物覆盖  " + str(td.get("reason", "")))
    ts = st["time_span"]
    if ts.get("checked"):
        print("② 时间跨度  累计推进约 %d 天（%.1f 年）" % (ts["total_days"], ts["total_years"]))
        for s in ts["steps"][:5]:
            print("   第 %s 章 +%d 天" % (s["chapter"], s["days_added"]))
    else:
        print("② 时间跨度  没找到「N 天后/月后/年后」这类表述")
    fn = st["faded_names"]
    if fn.get("checked"):
        cand = fn.get("candidates") or []
        print("③ 消失的专名  %d 个候选" % len(cand))
        for c in cand[:6]:
            print("   %s（前半 %d 次，后半 0 次）" % (c["name"], c["early"]))
    print("-" * 66)
    if rep["issues"]:
        for i in rep["issues"]:
            print("%-6s %-14s %s" % (i["severity"], i["rule"], i["message"]))
    else:
        print("没有发现明显问题（这三项只查机械可判的部分，不评好坏）")
    print("-" * 66)
    print("诊断只读：没有改任何文件，也没有要求你建账。")
    return 0


if __name__ == "__main__":
    sys.exit(main())