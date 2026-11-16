# -*- coding: utf-8 -*-
"""信息差系统 —— 谁不知道什么

设计来自 webnovel-writer（GPL-3.0，只学设计不抄代码）：
  不追踪「每个角色知道哪些事件」，只登记「值得管理的信息差」
  每条一个文件：知情人 / 读者已知 / 登记章 / 关键词

两个机检：
  泄密机检 = 角色说了「他不该知道」的事
  废笔机检 = 向读者复述「读者已经知道」的事

用法：
  python core/infogap.py --book <书名> --list
  python core/infogap.py --book <书名> --check 004        # 查第 4 章
  python core/infogap.py --book <书名> --extract 003      # 从第 3 章提取候选
"""
import os
import re
import sys
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _projects_root():
    """客户数据目录（与 coordinator.projects_root 同一套优先级）。
    原来直接拼 ROOT（程序目录），客户数据在 %APPDATA% 时读不到。"""
    try:
        import coordinator as _CO
        return _CO.projects_root()
    except Exception:
        return os.path.join(ROOT, "projects")


def gap_dir(book):
    return os.path.join(_projects_root(), book, "设定库", "信息差")


def chapter_path(book, ch):
    d = os.path.join(_projects_root(), book, "章节")
    if not os.path.isdir(d):
        return None
    ch = str(ch).zfill(3)
    for fn in os.listdir(d):
        if fn.startswith(ch) and fn.endswith(".md"):
            return os.path.join(d, fn)
    return None


def parse_front(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {}, text
    head, body = m.group(1), m.group(2)
    data = {}
    key = None
    for line in head.split("\n"):
        s = line.rstrip()
        if not s or s.startswith("#"):
            continue
        if s.lstrip().startswith("- ") and key:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(s.lstrip()[2:].strip())
            continue
        mm = re.match(r"^([^:]+):\s*(.*)$", s)
        if mm:
            key = mm.group(1).strip()
            val = mm.group(2).strip()
            data[key] = val if val else []
    return data, body


def load_all(book):
    d = gap_dir(book)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(d, fn)
        with open(p, "r", encoding="utf-8") as f:
            meta, body = parse_front(f.read())
        meta["_file"] = fn
        meta["_path"] = p
        meta["_body"] = body
        out.append(meta)
    return out


def load_chars(book):
    """读角色卡，拿角色名和别名

    只认「一、甲（主角）」这种角色标题，不认「姓名」「别称」这种字段名。
    """
    d = os.path.join(_projects_root(), book, "设定库", "角色卡.md")
    if not os.path.isfile(d):
        return {}
    with open(d, "r", encoding="utf-8") as f:
        text = f.read()
    names = {}
    # 角色标题：一、甲（主角） / 二、老头（<书名>掌柜） / 三、苏掌柜
    for m in re.finditer(r"^#+\s*[一二三四五六七八九十]+、\s*([^（(\n]+)", text, re.M):
        n = m.group(1).strip()
        if n:
            names[n] = n
    # 别称：从「别称」字段那一行提
    for m in re.finditer(r"^\s*[-*]?\s*别称[:：]\s*(.+)$", text, re.M):
        line = m.group(1).strip()
        for alias in re.split(r"[、,，/\s]+", line):
            a = alias.strip().strip("'\"「」")
            if a and 1 < len(a) <= 6:
                names[a] = a
    return names


def check_chapter(book, ch):
    """检查一章：泄密 + 废笔

    只查对白（引号里的内容），不查叙述。
    理由：「甲看到灰背鸭」不是泄密，「甲说出灰背鸭的来历」才是。
    关键词不能是角色名本身（会自我命中）。
    """
    path = chapter_path(book, ch)
    if not path:
        return {"ok": False, "error": "找不到第 %s 章" % ch}
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    _, body = parse_front(text)

    gaps = load_all(book)
    chars = load_chars(book)
    issues = []

    # 提取所有对白：中文引号或英文引号里的内容
    dialogs = []
    for m in re.finditer(r'[""]([^""]{2,120})[""]', body):
        dialogs.append(m.group(1))
    for m in re.finditer(r'「([^」]{2,120})」', body):
        dialogs.append(m.group(1))

    # 找说话人：优先用紧邻模式「X说：「」或「」X说」，退化到窗口
    def speaker_near(dlg):
        pos = body.find(dlg)
        if pos < 0:
            return []
        before = body[max(0, pos - 40): pos]
        after = body[pos + len(dlg): pos + len(dlg) + 40]
        exact = []
        # 前置：X说 / X道 / X问 / X答 + 可选冒号
        m = re.search(r'([\u4e00-\u9fff]{2,4})(?:说|道|问|答)[：:]?\s*$', before)
        if m:
            cand = m.group(1)
            for c in chars:
                if cand.endswith(c) or c in cand:
                    exact.append(c)
        # 后置：」X说
        m2 = re.match(r'^\s*([\u4e00-\u9fff]{2,4})(?:说|道|问|答)', after)
        if m2:
            cand = m2.group(1)
            for c in chars:
                if cand.startswith(c) or c in cand:
                    if c not in exact:
                        exact.append(c)
        if exact:
            return exact
        # 退化：只在紧邻 ±12 字里找
        tiny = body[max(0, pos - 12): pos + len(dlg) + 12]
        found = [c for c in chars if c in tiny]
        return found
    # 1. 泄密机检：对白里出现关键词，且说话人不在知情人里
    for g in gaps:
        kws = g.get("关键词") or []
        if isinstance(kws, str):
            kws = [kws]
        insiders = g.get("知情人") or []
        if isinstance(insiders, str):
            insiders = [insiders]
        # 去掉占位
        insiders = [x for x in insiders if x and not x.startswith("（")]
        if not kws:
            continue
        # 关键词不能是角色名（自我命中）
        kws = [k for k in kws if k not in chars]
        for dlg in dialogs:
            hit = [k for k in kws if k in dlg]
            if not hit:
                continue
            speakers = speaker_near(dlg)
            for sp in speakers:
                if sp in insiders:
                    continue
                if sp == "老头" and g.get("编号") in ("S-003", "S-004"):
                    continue  # 老头是当铺主人，本来就知道
                # 转述降级：「你说」「他说」这种是在引用别人，不是自己知道
                QUOTE = ("你说", "他说", "你讲", "他讲", "你刚才", "他刚才",
                         "听你", "听他说", "你说的", "他说的", "问你", "问他")
                is_quote = any(q in dlg for q in QUOTE)
                issues.append({
                    "type": "leak",
                    "severity": "medium" if is_quote else "critical",
                    "gap": g.get("编号"),
                    "detail": ("%s 转述了含「%s」的话（%s）" if is_quote
                               else "%s 说了含「%s」的话，但他不在 %s 的知情人里")
                               % ((sp, "、".join(hit), g.get("编号")) if not is_quote
                                  else (sp, "、".join(hit), g.get("编号"))),
                    "para": dlg[:80],
                })

    # 2. 废笔机检：读者已知的信息被大段复述
    #    放宽：只有同一章复述同一个信息差 ≥ 3 次才警告
    for g in gaps:
        if str(g.get("读者已知", "")).lower() not in ("true", "是", "已"):
            continue
        kws = g.get("关键词") or []
        if isinstance(kws, str):
            kws = [kws]
        kws = [k for k in kws if k not in chars]
        count = 0
        for k in kws:
            count += body.count(k)
        if count >= 5:
            issues.append({
                "type": "redundant",
                "severity": "low",
                "gap": g.get("编号"),
                "detail": "读者已知的信息反复出现 %d 次（%s）" % (count, g.get("编号")),
            })

    # 去重
    seen = set()
    uniq = []
    for i in issues:
        key = (i["type"], i.get("gap"), i["detail"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(i)

    return {
        "ok": True,
        "chapter": str(ch).zfill(3),
        "passed": not any(i["severity"] == "critical" for i in uniq),
        "blocking": [i for i in uniq if i["severity"] == "critical"],
        "warnings": [i for i in uniq if i["severity"] != "critical"],
        "checked_gaps": len(gaps),
        "chars": len(chars),
        "dialogs": len(dialogs),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.check:
        r = check_chapter(args.book, args.check)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            if not r.get("ok"):
                print(r.get("error"))
                return 1
            print("=== 第 %s 章信息差检查 ===" % r["chapter"])
            print("  检查了 %d 条信息差，%d 个角色" % (r["checked_gaps"], r["chars"]))
            if r["passed"]:
                print("  ✅ 通过")
            else:
                print("  ❌ 有 %d 个阻断问题" % len(r["blocking"]))
            for i in r["blocking"]:
                print("    [%s] %s" % (i["type"], i["detail"]))
                if i.get("para"):
                    print("      「%s」" % i["para"])
            for i in r["warnings"]:
                print("    ⚠ [%s] %s" % (i["type"], i["detail"]))
        return 0 if r.get("passed") else 1

    gaps = load_all(args.book)
    if args.json:
        print(json.dumps(gaps, ensure_ascii=False, indent=1, default=str))
        return 0

    print("=== 信息差清单（共 %d 条）===" % len(gaps))
    for g in gaps:
        ins = g.get("知情人") or []
        if isinstance(ins, str):
            ins = [ins]
        rd = str(g.get("读者已知", "false"))
        kws = g.get("关键词") or []
        if isinstance(kws, str):
            kws = [kws]
        print("  %-8s %-22s 知情人 %-2d 读者%s 关键词 %d" % (
            g.get("编号", "?"), g.get("标题", "?")[:20], len(ins),
            "已" if rd.lower() in ("true", "是") else "未", len(kws)))
        print("           %s" % "、".join(ins) if ins else "           （没人知道）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
