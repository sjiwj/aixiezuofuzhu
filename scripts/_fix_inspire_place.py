# -*- coding: utf-8 -*-
"""把误插进类内部的模块级函数挪到 class H 之前，_inspire 方法留在类里。"""
import io, sys
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()

start = s.find("# ---------------- \u7075\u611f\u5c55\u5f00")
mstart = s.find("    def _inspire(self, data):")
if start < 0 or mstart < 0 or mstart < start:
    print("anchors missing", start, mstart); sys.exit(1)

module_part = s[start:mstart]          # 模块级：预算 + 三个函数
method_part = s[mstart:]
# 方法到下一个 4 空格 def 结束
nxt = method_part.find(chr(10) + "    def ", 10)
if nxt < 0:
    print("method end not found"); sys.exit(1)
method_block = method_part[:nxt + 1]
rest = method_part[nxt + 1:]

# 1) 从原位置删掉这两段
s = s[:start] + rest

# 2) 模块级块插到 class H: 之前
cls = s.find("class H:")
if cls < 0:
    print("class H missing"); sys.exit(1)
s = s[:cls] + module_part.rstrip() + chr(10) + chr(10) + chr(10) + s[cls:]

# 3) 方法插到 _polish 之前（此时 _polish 在类里）
pol = s.find("    def _polish(self, data):")
if pol < 0:
    print("polish missing"); sys.exit(1)
s = s[:pol] + method_block + s[pol:]

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("moved. class H at", s.find("class H:"), "_inspire at", s.find("def _inspire"), "_polish at", s.find("def _polish"))
