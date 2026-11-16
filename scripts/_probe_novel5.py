# -*- coding: utf-8 -*-
import io, os, re
base = os.path.join("C:" + os.sep, "Users", "24929", "Documents", "deepseek-harness", "default-workspace", "work", "cases", "laper", "04-web", "assets")
for name in ("index-DMhpYWnC.js", "scriptAssistHost-FgQv1l4S.js"):
    p = os.path.join(base, name)
    if not os.path.isfile(p):
        print(name, "missing"); continue
    s = io.open(p, encoding="utf-8", errors="replace").read()
    print("===", name, len(s))
    for kw in ("novel", "manuscript", "screenplay", "storyBible", "story_bible"):
        c = s.count(kw)
        if c:
            print("  ", kw, "->", c)
    m = re.search("novel", s)
    if m:
        a = max(0, m.start() - 150)
        print("   ctx:", repr(s[a:m.start() + 200])[:420])