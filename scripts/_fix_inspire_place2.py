# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()

start = s.find("# ---------------- \u7075\u611f\u5c55\u5f00")
mstart = s.find("    def _inspire(self, data):")
if start < 0 or mstart < 0 or mstart < start:
    print("anchors missing", start, mstart); sys.exit(1)

module_part = s[start:mstart]
method_part = s[mstart:]
nxt = method_part.find(chr(10) + "    def ", 10)
if nxt < 0:
    print("method end not found"); sys.exit(1)
method_block = method_part[:nxt + 1]
rest = method_part[nxt + 1:]

s = s[:start] + rest

cls = s.find("class H(BaseHTTPRequestHandler):")
if cls < 0:
    print("class H missing"); sys.exit(1)
s = s[:cls] + module_part.rstrip() + chr(10) + chr(10) + chr(10) + s[cls:]

pol = s.find("    def _polish(self, data):")
if pol < 0:
    print("polish missing"); sys.exit(1)
s = s[:pol] + method_block + s[pol:]

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("moved. class H at", s.find("class H(BaseHTTPRequestHandler)"), "_inspire at", s.find("def _inspire"), "_polish at", s.find("def _polish"))
