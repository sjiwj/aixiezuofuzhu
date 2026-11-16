# -*- coding: utf-8 -*-
"""把 角色卡.md 拆成 角色卡/<名字>.md，原文件改成索引。"""
import io, os, re, sys

BASE = r"D:\NovelApp\projects\<书名>\设定库"
SRC = os.path.join(BASE, "角色卡.md")
OUT = os.path.join(BASE, "角色卡")

s = io.open(SRC, encoding="utf-8").read()
lines = s.split(chr(10))

# 找所有 "## 一、甲（主角）" 这样的标题
heads = []
for i, ln in enumerate(lines):
    m = re.match(r"^##\s*(?:[\u4e00-\u9fa5]+\s*[\u3001.]\s*)?([^\s（(]+)\s*(?:[（(]([^）)]*)[）)])?\s*$", ln)
    if m:
        heads.append((i, m.group(1).strip(), (m.group(2) or "").strip()))

print("found %d characters:" % len(heads))
for h in heads: print("  ", h[1], h[2])

if not os.path.isdir(OUT):
    os.makedirs(OUT)

# 每个角色的内容 = 从它的标题到下一个标题（去掉尾部的 ---）
index_lines = ["# 《<书名>》· 角色卡", "", "> 一人一张卡，详情在 `角色卡/` 目录下。", ""]
for n, (i, name, note) in enumerate(heads):
    end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
    body = chr(10).join(lines[i:end]).rstrip()
    # 去掉尾部单独的 ---
    body = re.sub(r"\n+-{3,}\s*$", "", body).rstrip()
    # 把 "## 一、甲（主角）" 降级为 "# 甲（主角）"
    body = re.sub(r"^##\s*(?:[\u4e00-\u9fa5]+\s*[\u3001.]\s*)?", "# ", body, count=1)
    title = name + (("（" + note + "）") if note else "")
    fp = os.path.join(OUT, name + ".md")
    if os.path.exists(fp):
        print("  skip (exists):", name)
    else:
        io.open(fp, "w", encoding="utf-8", newline="").write(body + chr(10))
        print("  wrote:", name + ".md")
    index_lines.append("- [[%s]] %s" % (name, ("—— " + note) if note else ""))

# 原文件改成索引
index_lines.append("")
io.open(SRC, "w", encoding="utf-8", newline="").write(chr(10).join(index_lines))
print("index written:", SRC)