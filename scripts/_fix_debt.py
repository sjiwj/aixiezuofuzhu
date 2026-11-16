# -*- coding: utf-8 -*-
"""给读债加：① 按卷过滤 ② 混合来源（承诺+伏笔+状态缺口） ③ 分类配额"""
import io
p = r"D:\NovelApp\scripts\debt_view.py"
s = io.open(p, encoding="utf-8").read()
if "cur_volume" in s:
    print("ALREADY"); raise SystemExit

# 1) 卷解析 + 状态缺口
helpers = '''def cur_volume(book_dir, ch):
    """当前章属于哪一卷。解析 大纲/全书大纲.md 的「### 卷一 · 名字（001–060）」。"""
    d = os.path.join(book_dir, "\u5927\u7eb2")
    if not os.path.isdir(d):
        return ""
    pat = re.compile(r"###\\s*\u5377([\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+)[^\uff08(]*[\uff08(](\\d{1,4})\\s*[\u2013\\-~]\\s*(\\d{1,4})[\uff09)]")
    for fn in sorted(x for x in os.listdir(d) if x.endswith(".md")):
        text = read(os.path.join(d, fn))
        for m in pat.finditer(text):
            lo, hi = int(m.group(2)), int(m.group(3))
            if lo <= ch <= hi:
                return "\u5377" + m.group(1)
    return ""


def vol_ok(promise_fm, vol):
    """承诺写了「可推进卷」且不含当前卷 -> 排除。"""
    if not vol:
        return True
    vols = str(promise_fm.get("\u53ef\u63a8\u8fdb\u5377") or "").strip()
    if not vols:
        return True
    return vol in [v.strip() for v in re.split(r"[,,\u3001]", vols) if v.strip()]


def load_state_gaps(book_dir):
    """角色状态里「未记录/未说明」的字段——这也是债。"""
    d = os.path.join(book_dir, "\u8bbe\u5b9a\u5e93", "\u89d2\u8272\u72b6\u6001.md")
    text = read(d)
    if not text:
        return []
    out, who = [], ""
    for ln in text.split(chr(10)):
        if ln.startswith("## "):
            who = ln[3:].strip()
        elif ("\u672a\u8bb0\u5f55" in ln or "\u672a\u8bf4\u660e" in ln) and who:
            key = ln.strip().lstrip("-* ").split("**")[1] if "**" in ln else "\u5b57\u6bb5"
            out.append({"who": who, "field": key})
    return out


'''
i = s.find("def load_promises(book_dir, cur_ch):")
if i < 0:
    print("anchor1 missing"); raise SystemExit(1)
s = s[:i] + helpers + s[i:]

# 2) load_promises 加卷过滤
s = s.replace('def load_promises(book_dir, cur_ch):', 'def load_promises(book_dir, cur_ch, vol=""):')
s = s.replace('        title = fm.get("\u6807\u9898") or fn.replace(".md", "")',
              '        if not vol_ok(fm, vol):' + chr(10) +
              '            continue' + chr(10) +
              '        title = fm.get("\u6807\u9898") or fn.replace(".md", "")')

# 3) build_debt 用卷过滤 + 混合配额
s = s.replace("    prom = load_promises(book_dir, cur_ch)",
              '    vol = cur_volume(book_dir, cur_ch)' + chr(10) +
              '    prom = load_promises(book_dir, cur_ch, vol)' + chr(10) +
              '    gaps = load_state_gaps(book_dir)')

s = s.replace('    items = []', '    items = []\n    for g in gaps[:2]:\n        items.append({"kind": "\u72b6\u6001\u7f3a\u53e3", "id": g["who"], "title": "%s \u7684\u300c%s\u300d\u6ca1\u8bb0",\n                      "why": "\u5c5e\u6027\u7a7a\u7740\uff0c\u5199\u4e0b\u4e00\u7ae0\u65f6\u4f1a\u6f0f", "weight": 1.5})   # noqa')

s = s.replace('            "summary": "\u8fd9\u4e00\u7ae0\u5fc5\u987b\u52a8 %d \u6761\uff0c\u5176\u4f59 %d \u6761\u662f\u80cc\u666f" % (len(top), max(0, len(items) - len(top)))}',
              '            "volume": vol, "gaps": len(gaps),' + chr(10) +
              '            "summary": "\u8fd9\u4e00\u7ae0\u5fc5\u987b\u52a8 %d \u6761\uff0c\u5176\u4f59 %d \u6761\u662f\u80cc\u666f" % (len(top), max(0, len(items) - len(top)))}')

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("debt_view: vol filter + state gaps")