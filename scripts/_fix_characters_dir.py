# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\core\write_context.py"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "_characters_dir" in s:
    print("ALREADY"); sys.exit(0)

OLD = """def _characters(book, probe_text):
    \"\"\"\u89d2\u8272\u5361\uff1a\u6309\u6b63\u6587/\u7ae0\u7eb2\u91cc\u51fa\u73b0\u8fc7\u7684\u540d\u5b57\u6311\uff08\u590d\u7528 reviewers.pick_characters\uff09\u3002\"\"\"
    text = _read(os.path.join(_book_dir(book), '\u8bbe\u5b9a\u5e93', '\u89d2\u8272\u5361.md'))
    if not text:
        return []"""

NEW = """def _characters(book, probe_text):
    \"\"\"\u89d2\u8272\u5361\uff1a\u6309\u6b63\u6587/\u7ae0\u7eb2\u91cc\u51fa\u73b0\u8fc7\u7684\u540d\u5b57\u6311\uff08\u590d\u7528 reviewers.pick_characters\uff09\u3002

    \u4e24\u79cd\u5b58\u6cd5\u90fd\u652f\u6301\uff1a
      \u00b7 \u65b0\uff1a\u8bbe\u5b9a\u5e93/\u89d2\u8272\u5361/\u5468\u590d.md\uff08\u4e00\u4eba\u4e00\u5f20\u5361\uff0cUI \u4e0a\u662f\u53ef\u6536\u8d77\u7684\u5206\u652f\uff09
      \u00b7 \u65e7\uff1a\u8bbe\u5b9a\u5e93/\u89d2\u8272\u5361.md\uff08\u5168\u90e8\u89d2\u8272\u6324\u4e00\u4e2a\u6587\u4ef6\uff0c\u5df2\u964d\u7ea7\u4e3a\u7d22\u5f15\uff09
    \u76ee\u5f55\u4f18\u5148\uff1b\u76ee\u5f55\u91cc\u6ca1\u4e1c\u897f\u624d\u8bfb\u5355\u6587\u4ef6\u3002
    \"\"\"
    text = _characters_dir(book)
    if not text:
        text = _read(os.path.join(_book_dir(book), '\u8bbe\u5b9a\u5e93', '\u89d2\u8272\u5361.md'))
    if not text:
        return []"""

if OLD not in s:
    print("anchor missing"); sys.exit(1)
s = s.replace(OLD, NEW, 1)

# 加目录读取函数（放在 _characters 之前）
HELPER = """def _characters_dir(book):
    \"\"\"\u8bfb \u8bbe\u5b9a\u5e93/\u89d2\u8272\u5361/ \u4e0b\u6240\u6709 .md\uff0c\u62fc\u6210\u4e00\u4efd\u300c\u5408\u5e76\u89d2\u8272\u5361\u300d\u3002

    \u6bcf\u4e2a\u6587\u4ef6\u7684\u7b2c\u4e00\u884c\u662f '# \u5468\u590d\uff08\u4e3b\u89d2\uff09'\uff0c\u8f6c\u56de parse_char_cards \u80fd\u8ba4\u7684
    '## \u4e00\u3001\u5468\u590d\uff08\u4e3b\u89d2\uff09' \u5f62\u5f0f\uff1b\u5426\u5219\u4e00\u4eba\u4e00\u5361\u4f1a\u88ab\u5f53\u6210\u540c\u4e00\u4e2a\u89d2\u8272\u3002
    \u6309\u6587\u4ef6\u540d\u6392\u5e8f\uff0c\u4fdd\u8bc1\u6bcf\u6b21\u88c5\u914d\u7ed3\u679c\u7a33\u5b9a\u3002
    \"\"\"
    d = os.path.join(_book_dir(book), '\u8bbe\u5b9a\u5e93', '\u89d2\u8272\u5361')
    if not os.path.isdir(d):
        return ''
    names = sorted(n for n in os.listdir(d) if n.endswith('.md') and not n.startswith('.'))
    if not names:
        return ''
    parts = []
    for i, n in enumerate(names):
        t = _read(os.path.join(d, n))
        if not t:
            continue
        t = t.lstrip()
        # '# \u5468\u590d\uff08\u4e3b\u89d2\uff09' -> '## \u4e00\u3001\u5468\u590d\uff08\u4e3b\u89d2\uff09'
        if t.startswith('# '):
            t = '## ' + _CN_ORD[i % len(_CN_ORD)] + '\u3001' + t[2:]
        parts.append(t.rstrip())
    return '\n\n'.join(parts)


_CN_ORD = '\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341'


def _characters(book, probe_text):"""

OLD2 = """def _characters(book, probe_text):
    \"\"\"\u89d2\u8272\u5361\uff1a\u6309\u6b63\u6587/\u7ae0\u7eb2\u91cc\u51fa\u73b0\u8fc7\u7684\u540d\u5b57\u6311\uff08\u590d\u7528 reviewers.pick_characters\uff09\u3002
"""
if OLD2 in s:
    s = s.replace(OLD2, HELPER, 1)
    print("helper inserted")
else:
    print("helper anchor missing (will insert before _characters)")
    i = s.find("def _characters(book, probe_text):")
    if i < 0:
        print("no _characters"); sys.exit(1)
    s = s[:i] + HELPER.replace("def _characters(book, probe_text):\"\"\"", "") + s[i:]

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("done")