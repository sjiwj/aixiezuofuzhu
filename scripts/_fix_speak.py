# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()
if "SPEAK_LINE" in s:
    print("ALREADY"); sys.exit(0)

# 1) 加「独占一行的 姓名：」这条最可靠的轨道
old = 'SPEAK = re.compile(r"([\\u4e00-\\u9fa5]{2,5})(?:\u8bf4|\u9053|\u95ee|\u7b54|\u7b11|\u558a|\u53eb|\u56de|\u5e94)[\\uff1a\uff1a\u3002\uff0c,\\s]")'
if old not in s:
    # 兜底：用更宽松的定位
    i = s.find("SPEAK = re.compile(")
    j = s.find(chr(10), i)
    if i < 0:
        print("SPEAK missing"); sys.exit(1)
    s = s[:j] + chr(10) + "# 剧本式对话：姓名独占一行以冒号结尾（中文小说最常见）" + chr(10) + 'SPEAK_LINE = re.compile(r"^\\s*([\\u4e00-\\u9fa5]{2,5})\\s*[\\uff1a:]\\s*$", re.M)' + s[j:]
else:
    s = s.replace(old, old + chr(10) + "# 剧本式对话：姓名独占一行以冒号结尾（中文小说最常见）" + chr(10) + 'SPEAK_LINE = re.compile(r"^\\s*([\\u4e00-\\u9fa5]{2,5})\\s*[\\uff1a:]\\s*$", re.M)', 1)

# 2) speakers_per_chapter 同时用两条轨道
old2 = '        for m in SPEAK.finditer(text):'
new2 = chr(10).join([
    '        for m in SPEAK.finditer(text):',
    '            w = m.group(1)',
    '            cnt[w] = cnt.get(w, 0) + 1',
    '        for m in SPEAK_LINE.finditer(text):',
    '            w = m.group(1)',
    '            cnt[w] = cnt.get(w, 0) + 1',
])[:-len("    '            cnt[w] = cnt.get(w, 0) + 1'")]
if old2 not in s:
    print("speakers anchor missing"); sys.exit(1)
# 替换「for + w + cnt」三行
i2 = s.find(old2)
j2 = s.find(chr(10) + chr(10), i2)
block = s[i2:j2]
if "cnt[w] = cnt.get(w, 0) + 1" in block:
    s = s[:i2] + new2 + s[j2:]

# 3) 轨道 B 也用 SPEAK_LINE
old3 = '    for m in SPEAK.finditer(early_raw):'
new3 = chr(10).join([
    '    for m in SPEAK.finditer(early_raw):',
    '        w = m.group(1)',
    '        cnt_b[w] = cnt_b.get(w, 0) + 1',
    '    for m in SPEAK_LINE.finditer(early_raw):',
    '        w = m.group(1)',
    '        cnt_b[w] = cnt_b.get(w, 0) + 1',
])
i3 = s.find(old3)
if i3 > 0:
    j3 = s.find("    for w, c in sorted(cnt_b.items()", i3)
    if j3 > i3:
        s = s[:i3] + new3 + chr(10) + s[j3:]

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("SPEAK_LINE added")