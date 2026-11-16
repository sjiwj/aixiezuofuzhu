# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
START = "\t\t/* \u5199\u4f5c\u52a9\u624b\u6302\u4ef6\uff1a\u53f3\u4e0b\u89d2\u6d6e\u52a8\uff0c\u8f7b\u91cf\u5bf9\u8bdd\uff08\u8d70 /api/assistant\uff0c\u4e0d\u5e26\u5de5\u5177\u5faa\u73af\uff09 */"
END_MARK = "\t\ttry { installAssistant(); } catch (e) { /* \u52a9\u624b\u6302\u8f7d\u5931\u8d25\u4e0d\u5f71\u54cd\u4e3b\u6d41\u7a0b */ }"
i = s.find(START)
j = s.find(END_MARK)
if i < 0 or j < 0 or j < i:
    print("anchors missing", i, j); sys.exit(1)
NEW = io.open(r"D:\NovelApp\scripts\_asst_v2.txt", encoding="utf-8").read()
s = s[:i] + NEW + s[j:]
io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("assistant v2 written")