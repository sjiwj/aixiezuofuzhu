# -*- coding: utf-8 -*-
"""给 /api/inspire 加机械核对：输出里出现的专有名词必须在设定库里。
照 Laper 的思路 —— 把「别乱写设定」从软约束变成客户端可判定。"""
import io, sys
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()
if "def inspire_verify" in s:
    print("ALREADY"); sys.exit(0)

BLOCK = """


def _setting_vocab(book):
    ""从设定库收集所有已知专名（人物/地名/物件），用于机械核对。""
    base = os.path.join(PROJECTS, book, "设定库")
    vocab = set()
    if not os.path.isdir(base):
        return vocab
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            try:
                with open(os.path.join(root, fn), encoding="utf-8-sig") as f:
                    text = f.read()
            except OSError:
                continue
            for line in text.split(chr(10)):
                st = line.strip()
                if st.startswith("## ") or st.startswith("- **") or st.startswith("| "):
                    for w in re.findall(r"[\u4e00-\u9fa5]{2,6}", st):
                        vocab.add(w)
    return vocab


def inspire_verify(book, text):
    ""核对模型输出里的专名：不在设定库里的按「疑似新增设定」报出来。""
    vocab = _setting_vocab(book)
    if not vocab:
        return {"checked": False, "reason": "设定库为空，无法核对", "suspects": []}
    # 只查「像专名」的：姓氏+2字、地名后缀、书名号内
    cand = set()
    for m in re.finditer(r"[\u300a]([\u4e00-\u9fa5]{2,8})[\u300b]", text):
        cand.add(m.group(1))
    for m in re.finditer(r"([\u4e00-\u9fa5])(\u5e97|\u94fa|\u9547|\u6751|\u5e84|\u5cad|\u6c9f|\u5e99|\u4e0b|\u574a|\u9662)", text):
        cand.add(m.group(0))
    suspects = [w for w in cand if w not in vocab]
    return {"checked": True, "vocab_size": len(vocab), "suspects": suspects[:8]}
"""

anchor = "def inspire_prompt(book, seed, hint, ctx, idx, total):"
i = s.find(anchor)
if i < 0:
    print("anchor missing"); sys.exit(1)
s = s[:i] + BLOCK.strip() + chr(10) + chr(10) + chr(10) + s[i:]

# 在 variant 事件里带上核对结果
old = "            send({"type": "variant", "index": idx, "text": text,"
if old not in s:
    print("send anchor missing"); sys.exit(1)
new = ("            _ver = inspire_verify(book, text)" + chr(10) +
       "            send({\"type\": \"variant\", \"index\": idx, \"text\": text, \"verify\": _ver,")
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("inspire_verify added")