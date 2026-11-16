# -*- coding: utf-8 -*-
"""dry_run 写一章，然后按队友建议的三件事验收 prompt 有没有被模型吃到。

① 输出里有没有残留「自查/以下是」
② cliche 命中数
③ 引号成对 / 破折号 / 阿拉伯数字
"""
import json
import os
import re
import sys
import urllib.request

HOST = "http://127.0.0.1:18760"


def token():
    with urllib.request.urlopen(HOST + "/novelapp/handshake", timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))["token"]


def write(book, ch):
    body = json.dumps({"book": book, "chapter": ch, "dry_run": True}).encode("utf-8")
    req = urllib.request.Request(HOST + "/api/write", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Novelapp-Token", token())
    buf = []
    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            try:
                ev = json.loads(line[6:])
            except Exception:
                continue
            if ev.get("type") == "delta" and ev.get("kind") == "content":
                buf.append(ev.get("text") or "")
    return "".join(buf)


def analyze(text):
    body = re.sub(r"^#\s*\u7b2c\s*\d+\s*\u7ae0.*?\n", "", text, count=1)
    out = {}
    out["chars"] = len(re.findall(r"[\u4e00-\u9fa5]", body))
    # ① 自查残留
    meta = [w for w in ["\u81ea\u67e5", "\u68c0\u67e5\u7ed3\u679c", "\u4ee5\u4e0b\u662f", "\u786e\u8ba4\u65e0\u8bef", "\u5df2\u68c0\u67e5"]
            if w in body]
    out["meta_leak"] = meta
    # ③ 格式
    out["dash"] = body.count("\u2014\u2014")
    out["arabic"] = len(re.findall(r"\d", body))
    out["quote_open"] = body.count("\u201c")
    out["quote_close"] = body.count("\u201d")
    out["quote_paired"] = out["quote_open"] == out["quote_close"]
    # ② 套话（新加的 18 条 + 原有高频）
    new18 = ["\u7136\u800c", "\u4e0d\u7981", "\u7f13\u7f13", "\u5fae\u5fae\u4e00\u7b11", "\u5fc3\u4e2d\u6697\u60f3", "\u773c\u4e2d\u95ea\u8fc7\u4e00\u4e1d",
             "\u5634\u89d2\u5fae\u5fae\u4e0a\u626c", "\u6df1\u5438\u4e00\u53e3\u6c14", "\u4e0d\u7531\u5f97", "\u96be\u4ee5\u7f6e\u4fe1", "\u82e5\u6709\u6240\u601d",
             "\u4f3c\u4e4e", "\u4eff\u4f5b", "\u5239\u90a3\u95f4", "\u987f\u65f6", "\u6cb9\u7136\u800c\u751f", "\u604d\u7136\u5927\u609f", "\u83ab\u540d\u5176\u5999"]
    hits = {w: body.count(w) for w in new18 if w in body}
    out["cliche_new18"] = hits
    out["cliche_total"] = sum(hits.values())
    # 情绪直写 / 总结腔
    emo = [w for w in ["\u5fc3\u4e2d\u4e00\u51db", "\u5fc3\u4e2d\u4e00\u7d27", "\u5fc3\u91cc\u4e00\u6c89", "\u611f\u5230\u4e00\u9635"] if w in body]
    out["emo_direct"] = emo
    strong = [w for w in ["\u603b\u4e4b", "\u4e5f\u5c31\u662f\u8bf4", "\u8fd9\u8bf4\u660e", "\u6362\u53e5\u8bdd\u8bf4", "\u4e0d\u5f97\u4e0d\u8bf4"] if w in body]
    out["summary_tone"] = strong
    # 不是…而是
    out["not_but"] = len(re.findall(r"\u4e0d\u662f[^\u3002\uff01\uff1f]{0,20}(?:\u800c\u662f|\u662f)", body))
    return out, body


if __name__ == "__main__":
    book = sys.argv[1] if len(sys.argv) > 1 else "\u957f\u751f\u5f53\u94fa"
    ch = sys.argv[2] if len(sys.argv) > 2 else "009"
    text = write(book, ch)
    res, body = analyze(text)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    os.makedirs(r"D:\NovelApp\_tmp", exist_ok=True)
    with open(r"D:\NovelApp\_tmp\write-test.md", "w", encoding="utf-8") as f:
        f.write(body)
    print("\n--- \u6b63\u6587\u524d 400 \u5b57 ---")
    print(body[:400])
