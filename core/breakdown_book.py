# -*- coding: utf-8 -*-
"""拆书：把一本书拆成 13 个写作维度

用法：
  python core/breakdown_book.py --book "D:\books\某某书.txt" --out "拆书库/书籍拆解/某某书"
  python core/breakdown_book.py --list                          # 看现有拆解
  python core/breakdown_book.py --dimension 01                  # 只拆一个维度

13 个维度：
  01-开篇钩子  02-人设塑造  03-金手指设计  04-世界观  05-节奏
  05b-剧情结构拆解  06-爽点情绪  07-对话  08-战斗描写  08b-战斗情形拆解
  09-断章钩子  10-文笔句式  11-配角拆解  十合一
"""
import os
import re
import sys
import json
import argparse
import posixpath
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

DIMENSIONS = [
    ("01", "开篇钩子", "黄金三章怎么抓人：第一段、第一个人、第一个悬念"),
    ("02", "人设塑造", "主角/配角/反派的功能分工，性格怎么立"),
    ("03", "金手指设计", "规则、限制、成长线、爽点来源"),
    ("04", "世界观", "力量体系、地图、势力格局"),
    ("05", "节奏", "冲突/爽点/高潮的间隔与密度"),
    ("05b", "剧情结构拆解", "卷/章/事件的结构骨架"),
    ("06", "爽点情绪", "读者为什么买单，什么让他爽"),
    ("07", "对话", "对话风格、口头禅、信息密度"),
    ("08", "战斗描写", "战斗怎么写：详略、镜头、节奏"),
    ("08b", "战斗情形拆解", "具体战斗场面的拆法"),
    ("09", "断章钩子", "结尾怎么断章、留什么悬念"),
    ("10", "文笔句式", "句式/用词/段落节奏"),
    ("11", "配角拆解", "配角怎么立、怎么用"),
]


# ---------------- epub 支持（只用标准库：zipfile / html.parser / re）----------------

_BLOCK_TAGS = frozenset((
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "div",
    "dl", "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
))
_SKIP_TAGS = frozenset(("script", "style", "head", "title"))
_HTML_EXT = (".xhtml", ".html", ".htm")
_ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*("([^"]*)"|'([^']*)')""")


class _TextExtractor(HTMLParser):
    """xhtml/html → 纯文本：块级标签处断行，实体自动还原。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self._seg = []
        self._lines = []
        self._skip = 0

    def _flush(self):
        s = re.sub(r"\s+", " ", "".join(self._seg)).strip()
        if s:
            self._lines.append(s)
        self._seg = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            if self._skip > 0:
                self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip == 0 and data:
            self._seg.append(data)

    def text(self):
        self._flush()
        return "\n".join(self._lines)


def _html_to_text(markup):
    """xhtml 片段 → 纯文本，解析异常也返回已拿到的部分。"""
    p = _TextExtractor()
    try:
        p.feed(markup)
        p.close()
    except Exception:
        pass
    return p.text()


def _decode_bytes(data):
    """字节 → 文本：utf-8 → gbk → gb18030，全失败用 utf-8/replace。"""
    if isinstance(data, str):
        return data
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            s = data.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError, LookupError):
            continue
    else:
        s = data.decode("utf-8", "replace")
    if s.startswith("\ufeff"):
        s = s[1:]
    return s


def _attrs(tag):
    """从一个标签文本里抠属性（键小写，值去引号）。"""
    out = {}
    for m in _ATTR_RE.finditer(tag):
        val = m.group(3)
        if val is None:
            val = m.group(4)
        out[m.group(1).lower()] = val or ""
    return out


def _name_variants(name):
    """zip 内文件名的等价写法（cp437 存的 utf-8、NFC/NFD 归一化）。"""
    try:
        import unicodedata
    except Exception:
        unicodedata = None
    out = [name]
    if unicodedata is not None:
        for norm in ("NFC", "NFD"):
            try:
                v = unicodedata.normalize(norm, name)
            except Exception:
                continue
            if v not in out:
                out.append(v)
    try:
        v = name.encode("cp437").decode("utf-8")
        if v not in out:
            out.append(v)
    except Exception:
        pass
    return out


def _resolve_zip_name(names, href, base):
    """opf 里的 href（可能带 %xx）→ zip 里真实条目名；找不到返回 None。"""
    href = unquote(href.split("#")[0].split("?")[0]).replace("\\", "/").strip()
    if not href:
        return None
    cand = href if not base else posixpath.join(base, href)
    cand = posixpath.normpath(cand).replace("\\", "/")
    while cand.startswith("../"):
        cand = cand[3:]
    if cand.startswith("./"):
        cand = cand[2:]
    table = {}
    for n in names:
        for v in _name_variants(n):
            table.setdefault(v.replace("\\", "/").lower(), n)
    hit = table.get(cand.lower())
    if hit:
        return hit
    base_name = posixpath.basename(cand.lower())
    hits = set(table[k] for k in table if posixpath.basename(k) == base_name)
    if len(hits) == 1:
        return hits.pop()
    return None


def _spine_files(zf, names):
    """按 container.xml → opf → spine 拿正文顺序；解析不出来返回 []。"""
    try:
        container = _decode_bytes(zf.read("META-INF/container.xml"))
    except Exception:
        container = ""
    opf = None
    for m in re.finditer(r"<rootfile\b[^>]*>", container, re.I):
        full = _attrs(m.group(0)).get("full-path")
        if full:
            opf = _resolve_zip_name(names, full, "")
            if opf:
                break
    if not opf:
        opfs = sorted(n for n in names if n.lower().endswith(".opf"))
        opf = opfs[0] if opfs else None
    if not opf:
        return []
    try:
        xml = _decode_bytes(zf.read(opf))
    except Exception:
        return []
    base = posixpath.dirname(opf)
    manifest = {}
    mscope = re.search(r"<manifest\b.*?</manifest>", xml, re.I | re.S)
    for m in re.finditer(r"<item\b[^>]*>", mscope.group(0) if mscope else xml, re.I):
        a = _attrs(m.group(0))
        if a.get("id") and a.get("href"):
            manifest[a["id"]] = a["href"]
    out = []
    sscope = re.search(r"<spine\b.*?</spine>", xml, re.I | re.S)
    for m in re.finditer(r"<itemref\b[^>]*>", sscope.group(0) if sscope else xml, re.I):
        a = _attrs(m.group(0))
        if a.get("linear", "").lower() == "no":
            continue
        href = manifest.get(a.get("idref", ""))
        if not href:
            continue
        name = _resolve_zip_name(names, href, base)
        if not name or not name.lower().endswith(_HTML_EXT):
            continue
        if name not in out:
            out.append(name)
    return out


def _read_epub(path):
    """epub → 纯文本；任何失败返回 None。"""
    try:
        zf = zipfile.ZipFile(path)
    except Exception:
        return None
    try:
        names = zf.namelist()
    except Exception:
        zf.close()
        return None
    with zf:
        try:
            files = _spine_files(zf, names)
        except Exception:
            files = []
        if not files:
            files = sorted(n for n in names
                           if n.lower().endswith(_HTML_EXT) and not n.endswith("/"))
        chapters = []
        for name in files:
            try:
                raw = zf.read(name)
            except Exception:
                continue
            if not raw:
                continue
            try:
                body = _html_to_text(_decode_bytes(raw)).strip()
            except Exception:
                continue
            if body:
                chapters.append(body)
        if not chapters:
            return None
        text = "\n\n".join(chapters)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _looks_like_epub(path):
    """扩展名是 .epub，或者压缩包里真有 container/opf，就当 epub 读。"""
    if os.path.splitext(path)[1].lower() == ".epub":
        return True
    try:
        if not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except Exception:
        return False
    if "META-INF/container.xml" in names:
        return True
    return any(n.lower().endswith(".opf") for n in names)


def read_book(path):
    """读一本书（txt / epub），返回 (text, encoding)；读不了返回 (None, None)。"""
    if _looks_like_epub(path):
        try:
            text = _read_epub(path)
        except Exception:
            text = None
        if text and text.strip():
            return text, "epub"
        try:
            is_zip = zipfile.is_zipfile(path)
        except Exception:
            is_zip = False
        if is_zip:
            # 真是压缩包但读不出正文（加密/结构坏），别再当 txt 硬读
            return None, None
        # 只是扩展名骗人的纯文本，继续往下按 txt 解
    for enc in ("utf-8", "gbk", "gb18030", "utf-16"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            return None, None
    return None, None


def split_chapters(text):
    """粗分章节"""
    pats = [
        r"^第[零一二三四五六七八九十百千万\d]+章[^\n]{0,40}$",
        r"^Chapter\s+\d+[^\n]{0,40}$",
        r"^卷[零一二三四五六七八九十\d]+[^\n]{0,40}$",
    ]
    lines = text.split("\n")
    marks = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if any(re.match(p, s) for p in pats):
            marks.append(i)
    if len(marks) < 3:
        return [(0, len(lines))]
    out = []
    for i, idx in enumerate(marks):
        end = marks[i + 1] if i + 1 < len(marks) else len(lines)
        out.append((idx, end))
    return out


def build_prompt(dim_code, dim_name, dim_desc, book_text, book_name):
    """给一个维度构造提示词"""
    sys_p = ("你是网文拆解专家。把一本书的「%s」维度拆出来。\n\n"
             "拆解目标：%s\n\n"
             "输出格式：\n"
             "## 一句话内核\n（这个维度，这本书的核心做法）\n\n"
             "## 可复用写法规则\n（具体怎么做，能直接用的，列 3-7 条）\n\n"
             "## 反面（别这样写）\n（这本书没做的事，或者踩过的坑）\n\n"
             "## 迁移要点\n（怎么用到自己的书上，注意什么）\n"
             % (dim_name, dim_desc))

    body = ("书名：%s\n\n"
            "请只针对「%s」这一个维度拆解，不要泛泛而谈。\n"
            "拆不出就写「这本书这个维度不突出」，不要编。\n\n"
            "=== 正文（节选，约 8000 字）===\n%s"
            % (book_name, dim_name, book_text[:8000]))

    return sys_p, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dimension", default=None)
    ap.add_argument("--root", default=None)
    args = ap.parse_args()

    lib_root = args.root or os.path.join(ROOT, "assets", "拆书库", "书籍拆解")

    if args.list:
        if not os.path.isdir(lib_root):
            print("拆书库是空的（%s）" % lib_root)
            return 0
        books = [d for d in os.listdir(lib_root) if os.path.isdir(os.path.join(lib_root, d))]
        if not books:
            print("拆书库是空的 —— 说「拆一下 <文件路径>」开始")
            return 0
        print("已有 %d 本：" % len(books))
        for b in books:
            files = [f for f in os.listdir(os.path.join(lib_root, b)) if f.endswith(".md")]
            print("  %s（%d 个维度）" % (b, len(files)))
        return 0

    if not args.book:
        print("用法：python core/breakdown_book.py --book <文件> [--out <目录>]")
        print("      python core/breakdown_book.py --list")
        return 1

    if not os.path.isfile(args.book):
        print("❌ 文件不存在: %s" % args.book)
        return 1

    text, enc = read_book(args.book)
    if text is None:
        print("❌ 读不了（编码不对）: %s" % args.book)
        return 1

    book_name = os.path.splitext(os.path.basename(args.book))[0]
    out_dir = args.out or os.path.join(lib_root, book_name)
    os.makedirs(out_dir, exist_ok=True)

    chs = split_chapters(text)
    print("书名: %s" % book_name)
    print("编码: %s" % enc)
    print("字数: %d" % len(text))
    print("章节: %d" % len(chs))
    print("输出: %s" % out_dir)
    print()

    # 只输出提示词，调模型由上层做（这个脚本不直接调）
    targets = DIMENSIONS
    if args.dimension:
        targets = [d for d in DIMENSIONS if d[0] == args.dimension]
        if not targets:
            print("❌ 没有这个维度: %s" % args.dimension)
            return 1

    print("=== 要拆的维度（%d 个）===" % len(targets))
    for code, name, desc in targets:
        print("  %s-%s：%s" % (code, name, desc))
    print()
    print("提示：这个脚本只准备提示词，实际拆解靠 AI。")
    print("     在对话里说「拆一下 %s」，AI 会逐维度跑。" % args.book)
    return 0


if __name__ == "__main__":
    sys.exit(main())