# -*- coding: utf-8 -*-
"""审稿历史 —— 让审稿团有「过去」

思路来源：DSH 社区插件「赛博公司」的 Persistent Runtime
  核心不是「多几个 Agent 卡片」，而是「刷新页面不会重置」

我们的现状：
  每章独立审，审完就忘
  critic-a 不记得上次怎么说的，不记得客户驳回过什么

这个模块补上「时间维度」：
  1. 从历史审稿报告提取问题
  2. 找出「反复出现」的（连续 3 章都提了 = 顽疾）
  3. 找出「上次提了这次有没有改」
  4. 组装成一段话，注入审稿提示词

用法：
  python core/review_history.py --book <书名>                    # 看历史摘要
  python core/review_history.py --book <书名> --for-chapter 004  # 给第 4 章审稿用的摘要
"""
import os
import re
import sys
import json
import argparse
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _projects_root():
    try:
        import coordinator as _CO
        return _CO.projects_root()
    except Exception:
        return os.path.join(ROOT, "projects")


def reports_dir(book):
    return os.path.join(_projects_root(), book, "reports")


def load_reports(book):
    """读所有审稿报告（.md，审稿团输出）"""
    d = reports_dir(book)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md") or fn.startswith("."):
            continue
        m = re.match(r"^(?:审稿结果-)?(\d{3})-", fn)
        if not m:
            continue
        ch = m.group(1)
        if ch == "999":
            continue  # 内部自检报告不算
        try:
            with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                text = f.read()
            out.append({"chapter": ch, "file": fn, "text": text})
        except Exception:
            continue
    return out

def extract_issues(report):
    """从一份 .md 报告里提取问题句"""
    issues = []
    text = report.get("text") or ""
    who = None
    for line in text.split("\n"):
        s = line.strip()
        # 记当前审稿人
        m = re.match(r"^##\s+critic-([a-z])", s)
        if m:
            who = "critic-" + m.group(1)
            continue
        # 跳过标题、表格、代码块
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("```") or s.startswith(">"):
            continue
        if len(s) < 12 or len(s) > 150:
            continue
        # 排除「通过 / 无问题 / ✅」这类（那是检查结果，不是问题）
        if re.search(r"(✅|通过|无问题|没发现|符合|一致|正常|无越级)", s):
            continue
        # 找问题句
        if re.search(r"(问题|但是|不过|建议|缺点|不足|拖|慢|散|弱|硬|假|套话|划走|注水|风险|矛盾|偏差)", s):
            issues.append({"chapter": report["chapter"], "who": who or "?", "text": s})
    return issues

def find_recurring(reports, min_chapters=3):
    """找反复出现的问题：同类关键词出现在 >= N 章"""
    # 用关键词归并（不依赖语义）
    KEYWORDS = {
        "节奏": ("拖", "慢", "节奏", "注水", "铺垫"),
        "结构": ("结构", "散", "乱", "跳跃"),
        "人物": ("人物", "动机", "崩", "OOC", "性格"),
        "设定": ("设定", "矛盾", "前后", "战力", "时间线"),
        "文笔": ("文笔", "套话", "AI味", "假", "硬"),
        "钩子": ("钩子", "结尾", "悬念", "追读"),
    }
    hits = defaultdict(set)
    samples = defaultdict(list)
    for r in reports:
        for it in extract_issues(r):
            for cat, kws in KEYWORDS.items():
                if any(k in it["text"] for k in kws):
                    hits[cat].add(it["chapter"])
                    if len(samples[cat]) < 3:
                        samples[cat].append(it)
    out = []
    for cat, chapters in hits.items():
        if len(chapters) >= min_chapters:
            out.append({"category": cat, "chapters": sorted(chapters), "count": len(chapters), "samples": samples[cat]})
    out.sort(key=lambda x: -x["count"])
    return out


def build_context(book, current_ch=None, min_chapters=3):
    """组装给审稿提示词用的历史摘要"""
    reports = load_reports(book)
    if not reports:
        return ""
    recurring = find_recurring(reports, min_chapters)
    if not recurring:
        return ""

    lines = ["【这本书的历史问题】", ""]
    lines.append("下面是前几章审稿时反复出现的问题（不是这一章的问题，是这本书的顽疾）。")
    lines.append("审这一章时，注意看这些问题有没有改进，或者在别的形式下重现。")
    lines.append("")
    for r in recurring:
        lines.append("- %s（%d 章都提过：%s）" % (r["category"], r["count"], "、".join("第 " + c + " 章" for c in r["chapters"][:5])))
        if r["samples"]:
            s = r["samples"][0]["text"]
            lines.append("  例：%s" % s[:80])
    lines.append("")
    lines.append("如果你的判断和上面的历史不一致（比如你觉得这次改好了），直接说。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--for-chapter", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    reports = load_reports(args.book)
    recurring = find_recurring(reports)

    if args.json:
        print(json.dumps({"reports": len(reports), "recurring": recurring}, ensure_ascii=False, indent=1, default=str))
        return 0

    print("=== 审稿历史 === ")
    print("  报告数: %d" % len(reports))
    if reports:
        print("  覆盖章节: %s" % "、".join(r["chapter"] for r in reports))

    if not recurring:
        print("  还没有反复出现的问题（需要至少 %d 章的审稿记录）" % 3)
        return 0

    print("=== 反复出现的问题 ===")
    for r in recurring:
        print("  %s: %d 章都提过（%s）" % (r["category"], r["count"], "、".join(r["chapters"][:5])))
        if r["samples"]:
            print("    例: %s" % r["samples"][0]["text"][:70])

    if args.for_chapter:
        ctx = build_context(args.book, args.for_chapter)
        print()
        print("=== 注入第 %s 章审稿的上下文 ===" % args.for_chapter)
        print(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())