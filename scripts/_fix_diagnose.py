# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()
if "def strip_dialogue" in s:
    print("ALREADY"); sys.exit(0)

# 1) 加去对话函数 + 只认结构型专名
old = 'PROPER = re.compile(r"[\\u4e00-\\u9fa5]{2,4}")'
if old not in s:
    print("anchor missing"); sys.exit(1)
new = chr(10).join([
    'def strip_dialogue(text):',
    '    """去掉引号内内容——对话里的短语不是专名（这一步漏了，就会把「柴刀没了」当专名）"""',
    '    return re.sub(r"\u300c[^\u300d]*\u300d|\u201c[^\u201d]*\u201d|\"[^\"]*\"", "", text)',
    '',
    '',
    '# 只认结构型专名：后缀地/机构名 + 书名号。召回低，但不误报。',
    'PROPER = re.compile(r"(?:[\u4e00-\u9fa5]{1,3}(?:\u5e97|\u94fa|\u9547|\u6751|\u5e84|\u5cad|\u6c9f|\u5e99|\u574a|\u9662|\u5854|\u697c|\u5c71|\u6cb3|\u57ce|\u5e9c|\u5beb|\u5802))")',
]).lstrip(chr(10))
s = s.replace(old, new, 1)

# 2) check_faded_names 里先去对话
old2 = '    early_text = "".join(t for _n, _f, t in chs[:half])'
new2 = '    early_text = strip_dialogue("".join(t for _n, _f, t in chs[:half]))'
s = s.replace(old2, new2, 1)
old3 = '    late_text = "".join(t for _n, _f, t in chs[half:])'
new3 = '    late_text = strip_dialogue("".join(t for _n, _f, t in chs[half:]))'
s = s.replace(old3, new3, 1)

# 3) 时间正则放宽：也抓「过了N天」「N天过去」
s = s.replace(
    'DAY = re.compile(r"(\\d{1,3}|[\u4e00-\u9fa5\u4e24]{1,3})\\s*(?:\u5929|\u65e5)(?:\u540e|\u4e4b\u540e|\u4ee5\u540e|\u8fc7\u53bb\u4e86)")',
    'DAY = re.compile(r"(?:\\d{1,3}|[\u4e00-\u9fa5\u4e24]{1,3})\\s*(?:\u5929|\u65e5)(?:\u540e|\u4e4b\u540e|\u4ee5\u540e|\u8fc7\u53bb\u4e86)|(?:\u8fc7\u4e86|\u53c8\u8fc7|\u9694\u4e86)\\s*(\\d{1,3}|[\u4e00-\u9fa5\u4e24]{1,3})\\s*(?:\u5929|\u65e5)")',
)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("fixed: strip_dialogue + 结构型专名 + 时间正则")