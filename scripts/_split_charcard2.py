# -*- coding: utf-8 -*-
"""在 App 实际使用的 projects 目录里拆角色卡。"""
import io, os, re, sys

BASE = os.path.join(os.environ["APPDATA"], "novelapp-desktop", "data", "projects",
                    "<书名>", "设定库")
SRC = os.path.join(BASE, "角色卡.md")
OUT = os.path.join(BASE, "角色卡")
print("BASE:", BASE)
print("SRC exists:", os.path.exists(SRC))
if not os.path.exists(SRC):
    sys.exit(1)

s = io.open(SRC, encoding="utf-8").read()
lines = s.split(chr(10))
heads = []
for i, ln in enumerate(lines):
    m = re.match(r"^##\s*(?:[\u4e00-\u9fa5]+\s*[\u3001.]\s*)?([^\s（(]+)\s*(?:[（(]([^）)]*)[）)])?\s*$", ln)
    if m:
        heads.append((i, m.group(1).strip(), (m.group(2) or "").strip()))

print("found %d:" % len(heads), [h[1] for h in heads])
if not heads:
    sys.exit(2)

if not os.path.isdir(OUT):
    os.makedirs(OUT)

index_lines = ["# 《<书名>》· 角色卡", "", "> 一人一张卡，详情在 `角色卡/` 目录下。", ""]
for n, (i, name, note) in enumerate(heads):
    end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
    body = chr(10).join(lines[i:end]).rstrip()
    body = re.sub(r"\n+-{3,}\s*$", "", body).rstrip()
    body = re.sub(r"^##\s*(?:[\u4e00-\u9fa5]+\s*[\u3001.]\s*)?", "# ", body, count=1)
    fp = os.path.join(OUT, name + ".md")
    if os.path.exists(fp):
        print("  skip:", name)
    else:
        io.open(fp, "w", encoding="utf-8", newline="").write(body + chr(10))
        print("  wrote:", name + ".md", len(body), "chars")
    index_lines.append("- [[%s]] %s" % (name, ("—— " + note) if note else ""))

index_lines.append("")
io.open(SRC, "w", encoding="utf-8", newline="").write(chr(10).join(index_lines))
print("index updated")