# -*- coding: utf-8 -*-
import io, os, sys, re
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-dock__brief" in s:
    print("ALREADY"); sys.exit(0)

# 找 head.appendChild(title); 那一行，插在它后面
m = re.search(r"([ \t]*)head\.appendChild\(title\);\n", s)
if not m:
    print("anchor missing"); sys.exit(1)
ind = m.group(1)
INS = (ind + "// 折叠态补一行摘要（底部状态条要能一眼读到关键数字）" + chr(10) +
       ind + "if (!open) {" + chr(10) +
       ind + chr(9) + "const brief = [];" + chr(10) +
       ind + chr(9) + "if (data.chapters) brief.push(\"第 \" + data.chapters + \" 章\");" + chr(10) +
       ind + chr(9) + "if (data.chars) brief.push(data.chars + \" 字\");" + chr(10) +
       ind + chr(9) + "if (feas && feas !== \"loading\" && feas.M != null) brief.push(\"账目 \" + feas.M + \" 点\");" + chr(10) +
       ind + chr(9) + "if (pm0.open != null) brief.push(\"承诺 \" + pm0.open);" + chr(10) +
       ind + chr(9) + "if (brief.length) head.appendChild(el(\"span\", \"nvl-dock__brief\", brief.join(\"  ·  \")));" + chr(10) +
       ind + "}" + chr(10))
s = s[:m.end()] + INS + s[m.end():]

# pm 定义在哪？若在 render 里的后面，这里需要提前
if "const pm = data.promises || {};" in s:
    i_pm = s.find("const pm = data.promises || {};")
    i_head = s.find(ind + "// 折叠态补一行摘要")
    if i_pm > i_head:
        # pm 在后面定义，把它提到 head 之前
        s = s.replace("const pm = data.promises || {};", "", 1)
        s = s[:i_head] + ind + "const pm = data.promises || {};" + chr(10) + s[i_head:]
        print("pm hoisted")

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("brief added")