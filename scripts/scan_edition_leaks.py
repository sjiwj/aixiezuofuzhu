# -*- coding: utf-8 -*-
"""交付包泄漏扫描：确保对外包里没有"标记出内部/客户身份"的痕迹。

用法：
  python scripts/scan_edition_leaks.py <zip 或 解包目录>

命中即 exit 1，并逐条打印 文件:行号:text。
"""
import io
import os
import re
import sys
import zipfile

MARKERS = [
    "内部测试版", "客户版", "内部版", "对外版", "测试版",
    "代理服务费", "服务费 5%", "5% 服务费", "内部自测", "仅供自测",
    "edition_label", "内部测试版", "客户版文案",
]
# 文件名/结构层面的痕迹（只看我们自己的目录，别把 pip/numpy 的 internal 当命中）
NAME_MARKERS = ["edition.json", "edition_self", "edition_std"]
OWN_PREFIX = ("resources/core/", "resources/config/", "resources/plugin/", "resources/preset-data/",
              "resources/app/")

TEXT_EXT = (".py", ".js", ".json", ".html", ".css", ".yaml", ".yml", ".txt", ".ps1", ".md", ".ts")


def iter_files(root):
    if os.path.isdir(root):
        for dirpath, _, names in os.walk(root):
            for n in names:
                p = os.path.join(dirpath, n)
                yield os.path.relpath(p, root), p
        return
    with zipfile.ZipFile(root) as z:
        for e in z.infolist():
            if e.is_dir():
                continue
            with z.open(e) as f:
                yield e.filename, f.read()


def scan(target):
    hits = []
    names = []
    for name, data in iter_files(target):
        low = name.lower().replace("\\", "/")
        if low.startswith(OWN_PREFIX):
            for m in NAME_MARKERS:
                if m in low:
                    names.append((name, "存在计费口径标记：%s" % m))
        if not name.lower().endswith(TEXT_EXT):
            continue
        try:
            txt = data.decode("utf-8", "ignore") if isinstance(data, bytes) else open(data, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            for m in MARKERS:
                if m in line:
                    hits.append((name, i, line.strip()[:120]))
    return hits, names


def main():
    if len(sys.argv) < 2:
        print("usage: scan_edition_leaks.py <zip|dir>")
        return 2
    target = sys.argv[1]
    hits, names = scan(target)
    print("target:", target)
    print("text hits:", len(hits), "| name hits:", len(names))
    for n, why in names[:20]:
        print("  NAME", n, "|", why)
    for n, i, t in hits[:40]:
        print("  LINE", n + ":" + str(i), "|", t)
    if hits or names:
        print("RESULT: FAIL（对外包不得出现这些痕迹）")
        return 1
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())