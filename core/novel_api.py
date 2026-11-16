# -*- coding: utf-8 -*-
"""小说工作台后端 · 对齐炼字工坊编辑器（两张真机截图）

功能面：
  创作向导：目标字数 / 灵感火花(频道赛道抽卡) / 仿写立项(经典) / 智能导入立项 / 熔炉仿写(1-3本·九维度)
  编辑器  ：卷-章目录、开篇/续写/优化/AI率检测/AI消痕/审稿/润色/神评/拆书/重写/灵感/设定
  编辑条  ：智能排版、高频词、替换、导出章节、一键发布
计费：所有 AI 动作先 estimate（灵石）再 reserve/commit，文类动作按输入+输出字数结算。

  python core/novel_http.py
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ling import Ling, LingError  # noqa: E402
import deai as D  # noqa: E402

BJ = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 数据根目录：优先 NOVELAPP_DATA（客户机 = %APPDATA%\novelapp-desktop\data），
# 没有才落回安装目录。否则装到 Program Files 或覆盖升级会把作品库弄丢。
_DATA_ROOT = os.environ.get("NOVELAPP_DATA") or os.path.join(ROOT, "data")
DB = os.path.join(_DATA_ROOT, "novel", "db.json")
EXPORT_DIR = os.path.join(_DATA_ROOT, "novel", "exports")

LING = Ling()

PROMPTS = [
    {"id": "official-opening", "title": "官方-黄金开篇", "kind": "opening", "author": "炼字官方",
     "updated": "2026-10-15", "desc": "前三章立人设、抛钩子、给爽点",
     "template": "为《{{title}}》写第{{start}}章开篇。频道：{{channel}}；赛道：{{genre}}。核心灵感：{{idea}}。前 300 字出冲突，结尾留钩子，{{words}} 字。"},
    {"id": "official-continue", "title": "官方-章节续写", "kind": "continue", "author": "炼字官方",
     "updated": "2026-10-16", "desc": "承接上一章情绪与大后续剧情",
     "template": "续写第{{start}}章。上一章结尾：{{prev_tail}}。后续剧情：{{next_summary}}。出场角色：{{characters}}。{{words}} 字。"},
    {"id": "official-outline", "title": "官方-总纲生成", "kind": "outline", "author": "炼字官方",
     "updated": "2026-10-17", "desc": "主线/阶段推进/核心矛盾",
     "template": "为《{{title}}》写总纲。题材：{{genre}}。灵感：{{idea}}。共 {{chapters}} 章。"},
]

# 编辑器工具带（截图里那一排）
TOOLS = {
    "optimize":    {"label": "优化",      "mode": "text", "rate": "in"},
    "detect":      {"label": "AI率检测",  "mode": "text", "rate": "in"},
    "deai":        {"label": "AI消痕",    "mode": "text", "rate": "both"},
    "review":      {"label": "审稿",      "mode": "text", "rate": "in"},
    "polish":      {"label": "润色",      "mode": "text", "rate": "both"},
    "comment":     {"label": "神评",      "mode": "text", "rate": "in"},
    "rewrite":     {"label": "重写",      "mode": "text", "rate": "both"},
    "deconstruct": {"label": "拆书",      "mode": "text", "rate": "in"},
    "inspiration": {"label": "灵感",      "mode": "idea", "rate": "in"},
    "setting":     {"label": "设定",      "mode": "idea", "rate": "in"},
}


def now() -> str:
    return datetime.now(BJ).isoformat(timespec="seconds")


def load_db() -> dict:
    if not os.path.isfile(DB):
        return {"projects": {}}
    try:
        with open(DB, encoding="utf-8") as f:
            db = json.load(f) or {}
    except ValueError:
        return {"projects": {}}
    db.setdefault("projects", {})
    for pj in db["projects"].values():
        if "volumes" not in pj:
            pj["volumes"] = [{"id": "v1", "title": "第1卷"}]
        for ch in pj.get("chapters", []):
            ch.setdefault("volumeId", pj["volumes"][0]["id"])
    return db


_BAK_DIR = os.path.join(os.path.dirname(DB), "backups")
_BAK_KEEP = 20


def backup_db(tag: str = "") -> str:
    """写库前留一份快照（同一内容不重复留），最多保留 20 份。

    2026-11-11 事故后加：验证写接口时曾把真实章节正文覆盖掉，
    虽然从 exports 恢复了，但库本身没有历史。这里补上最小可用的回滚能力。
    """
    if not os.path.isfile(DB):
        return ""
    try:
        os.makedirs(_BAK_DIR, exist_ok=True)
        with open(DB, "rb") as f:
            raw = f.read()
        if not raw.strip():
            return ""
        names = sorted(n for n in os.listdir(_BAK_DIR) if n.startswith("db-") and n.endswith(".json"))
        if names:
            last = os.path.join(_BAK_DIR, names[-1])
            try:
                if open(last, "rb").read() == raw:
                    return last
            except OSError:
                pass
        stamp = datetime.now(BJ).strftime("%Y%m%d-%H%M%S")
        suffix = ("-" + re.sub(r"[^A-Za-z0-9_-]", "", tag)[:24]) if tag else ""
        path = os.path.join(_BAK_DIR, "db-%s%s.json" % (stamp, suffix))
        with open(path, "wb") as f:
            f.write(raw)
        names = sorted(n for n in os.listdir(_BAK_DIR) if n.startswith("db-") and n.endswith(".json"))
        for old_name in names[:max(0, len(names) - _BAK_KEEP)]:
            try:
                os.remove(os.path.join(_BAK_DIR, old_name))
            except OSError:
                pass
        return path
    except Exception:
        return ""


def save_db(db: dict, tag: str = ""):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    backup_db(tag)
    tmp = DB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DB)


def count_words(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def get_project(pid: str) -> dict:
    pj = load_db()["projects"].get(pid)
    if not pj:
        raise LingError("NOT_FOUND", "项目不存在")
    return pj


def put_project(pj: dict):
    db = load_db()
    db["projects"][pj["id"]] = pj
    save_db(db)


# ---------------- 项目 / 卷 / 章 ----------------
def new_project(payload: dict) -> dict:
    db = load_db()
    pid = uuid.uuid4().hex[:12]
    pj = {
        "id": pid, "title": payload.get("title") or "未命名作品",
        "channel": payload.get("channel") or "男频", "genre": payload.get("genre") or "都市",
        "word_goal": int(payload.get("word_goal") or 1000000),
        "idea": payload.get("idea") or "", "protagonist": payload.get("protagonist") or "",
        "characters": payload.get("characters") or [], "world": payload.get("world") or "",
        "golden_finger": payload.get("golden_finger") or "", "outline": "", "pitch": "",
        "volumes": [{"id": "v1", "title": "第1卷"}],
        "chapters": [], "created": now(), "published": False,
    }
    db["projects"][pid] = pj
    save_db(db)
    return pj


def add_volume(pid: str, title: str) -> dict:
    pj = get_project(pid)
    v = {"id": "v%d" % (len(pj["volumes"]) + 1), "title": title or ("第%d卷" % (len(pj["volumes"]) + 1))}
    pj["volumes"].append(v)
    put_project(pj)
    return v


def add_chapter(pid: str, title: str = "", content: str = "", volume_id: str = "", status: str = "draft") -> dict:
    pj = get_project(pid)
    idx = len(pj["chapters"]) + 1
    ch = {"id": uuid.uuid4().hex[:12], "index": idx, "volumeId": volume_id or pj["volumes"][0]["id"],
          "title": title or ("第%d章" % idx), "content": content, "words": count_words(content),
          "status": status, "updated": now()}
    pj["chapters"].append(ch)
    put_project(pj)
    return ch


def update_chapter(cid: str, payload: dict) -> dict:
    db = load_db()
    for pj in db["projects"].values():
        for ch in pj["chapters"]:
            if ch["id"] == cid:
                for k in ("title", "content", "status", "volumeId"):
                    if k in payload:
                        ch[k] = payload[k]
                if "content" in payload:
                    ch["words"] = count_words(payload["content"])
                ch["updated"] = now()
                save_db(db)
                return ch
    raise LingError("NOT_FOUND", "章节不存在")


def replace_in_chapter(cid: str, find: str, repl: str) -> dict:
    db = load_db()
    for pj in db["projects"].values():
        for ch in pj["chapters"]:
            if ch["id"] == cid:
                n = (ch.get("content") or "").count(find)
                ch["content"] = (ch.get("content") or "").replace(find, repl)
                ch["words"] = count_words(ch["content"])
                save_db(db)
                return {"replaced": n, "words": ch["words"]}
    raise LingError("NOT_FOUND", "章节不存在")


def format_chapter(cid: str) -> dict:
    """智能排版：去多余空行、半角标点转全角、段首去空格、对话独立成段。"""
    db = load_db()
    for pj in db["projects"].values():
        for ch in pj["chapters"]:
            if ch["id"] == cid:
                raw = ch.get("content") or ""
                text = re.sub(r"[ \t\u3000]+", "", raw)
                text = re.sub(r"\n{3,}", "\n\n", text)
                pairs = [(",", "，"), (";", "；"), (":", "："), ("?", "？"), ("!", "！")]
                for a, b in pairs:
                    text = text.replace(a, b)
                text = text.replace('"', "“").replace("'", "‘")
                text = "\n".join((line if line.startswith("“") else line) for line in text.split("\n"))
                ch["content"] = text
                ch["words"] = count_words(text)
                save_db(db)
                return {"words": ch["words"], "content": text}
    raise LingError("NOT_FOUND", "章节不存在")


def highfreq(cid: str, top: int = 20):
    db = load_db()
    for pj in db["projects"].values():
        for ch in pj["chapters"]:
            if ch["id"] == cid:
                text = ch.get("content") or ""
                toks = re.findall(r"[\u4e00-\u9fa5]{2,6}", text)
                stop = {"他们", "什么", "这个", "那个", "自己", "已经", "没有", "不是", "可以", "就是"}
                freq = {}
                for t in toks:
                    if t in stop:
                        continue
                    freq[t] = freq.get(t, 0) + 1
                ranked = sorted(freq.items(), key=lambda kv: -kv[1])[:top]
                return [{"word": w, "count": c} for w, c in ranked]
    raise LingError("NOT_FOUND", "章节不存在")


# ---------------- 生成 / 文本工具 ----------------
SCENES = ["楼道口", "办公室", "后巷", "出租屋", "电梯间", "便利店门口", "停车场", "天桥下"]
ACTS = ["把账本合上", "点了一支烟又掐掉", "给手机换了张卡", "把外套搭在椅背上", "盯着门口的监控", "把水杯推远了一点"]
LINES = ["“你早就该来了。”", "“账不是这么算的。”", "“他昨天还跟我说没事。”", "“别说你不知情。”", "“这单我不接。”", "“明天中午，老地方。”", "“钱我认，条件得改。”"]
INNER = ["他忽然意识到，今天不会太平。", "这句话像一根针，扎在最不该碰的地方。", "他没接话，先算了算自己还剩多少底牌。", "有些事一旦开口，就再也退不回去了。", "对方越客气，他越觉得不对。"]
HOOKS = ["门外传来三声敲门，节奏不对——来的人知道他在家。", "手机屏幕亮了，是一条转账通知，金额刚好是他欠的数。", "他抬头，看见对面楼里有人正举着望远镜看他。", "信封里只有一张照片，背面写着明天的日期。"]


def mock_prose(pj: dict, kind: str, seed: int, words: int) -> str:
    rnd = random.Random("%s-%s-%s" % (pj["id"], kind, seed))
    hero = pj.get("protagonist") or "陈默"
    if kind == "outline":
        return ("《%s》主线：一个被按在底层的人，借旧账本反手掀桌。\n\n"
                "第一阶段：退单、断供、被踢出局。\n第二阶段：借对手的规则做局，第一次让对方出血。\n"
                "第三阶段：账本背后的旧人浮出水面，必须选择替谁收账。\n\n核心矛盾：他要公道，对方要他闭嘴。"
                % pj.get("title", ""))
    body = ["%s在%s站了一会儿，%s。" % (hero, rnd.choice(SCENES), rnd.choice(ACTS))]
    used = set()
    while sum(count_words(x) for x in body) < words:
        for pool in (LINES, INNER, HOOKS):
            s = rnd.choice(pool)
            if s in used:
                continue
            used.add(s)
            body.append(s)
        body.append("%s%s。" % (hero, rnd.choice(["没动", "把手插回兜里", "看了一眼时间", "笑了一下", "把话咽了回去"])))
    return "\n\n".join(body)[: int(words * 1.2)]


def tool_output(pj: dict, kind: str, text: str, payload: dict) -> str:
    """文本类工具（润色/审稿/消痕…）：无真实模型时给出结构化的确定性结果。"""
    n = count_words(text)
    if kind == "detect":
        score = round(min(0.95, 0.42 + (n % 37) / 100.0), 2)
        return ("AI率检测：%d%%\n判定：%s\n依据：句式整齐度偏高、连接词密度 %0.1f/千字、段落长度方差小。\n建议：拆长句、加口语、把总结句改成动作。"
                % (int(score * 100), "疑似 AI" if score > 0.5 else "偏人工", (n % 9) + 1.0))
    if kind == "deai":
        r = D.rewrite(text, "novel", "v4.0", 2, use_llm=bool(os.environ.get("NOVEL_LLM_BASE")))
        m = r["metrics"]
        report = ("\n\n—— 消痕报告 ——\n"
                  "字数 %d → %d（保留 %.0f%%）\n"
                  "连接词 %d → %d（每千字 %.1f → %.1f）\n"
                  "短句占比 %.0f%% → %.0f%%　平均句长 %.1f → %.1f\n"
                  "命中：连接词 %d / 空词 %d / 模糊语 %d / 总结句 %d / 拆句 %d / 拆段 %d　修订轮次 %d"
                  % (m["inputChars"], m["outputChars"], m["char_keep_ratio"] * 100,
                     m["before"]["connectives"], m["after"]["connectives"],
                     m["before"]["conn_per_k"], m["after"]["conn_per_k"],
                     m["before"]["short_ratio"] * 100, m["after"]["short_ratio"] * 100,
                     m["before"]["avg_len"], m["after"]["avg_len"],
                     m["hits"]["connectives"], m["hits"]["empty_words"], m["hits"]["hedges"],
                     m["hits"]["summary"], m["hits"]["split"], m["hits"]["split_para"], m["rounds"]))
        return r["output"] + report
    if kind == "review":
        return ("审稿意见：\n1. 开篇冲突点在第 %d 字，略晚，建议前移。\n2. 对白占比 %d%%，偏低。\n"
                "3. 有 %d 处“他/她”连续指代，建议换动作。\n4. 结尾钩子偏弱，可加一个具体威胁。"
                % (max(120, n // 5), min(60, n % 40 + 10), n // 300 + 1))
    if kind == "comment":
        return ("神评候选：\n· “这账本比合同还硬。”\n· “他不是不会低头，是低头也得先把账算清。”\n"
                "· “看到第 %d 段我就知道，这单他非接不可。”" % (n // 200 + 1))
    if kind == "deconstruct":
        return ("拆书结论（前 10 章）：\n类型：%s·%s\n开篇钩子：主角在 300 字内被逼到墙角。\n"
                "爽点节奏：每 2 章一次小反转，第 7 章第一次打脸。\n人设：低姿态+高算力，靠信息差取胜。\n"
                "可复用公式：被夺走 → 拿到凭证 → 借规则反杀。" % (pj.get("channel"), pj.get("genre")))
    if kind in ("inspiration", "setting"):
        return ("灵感：\n· 旧账本 + 新公司，双线对账\n· 主角每次让步都留证据\n· 反派用“合规”压人\n\n"
                "设定建议：金手指=过目不忘的账目记忆；代价=每用一次头疼一天。")
    # polish / rewrite / optimize
    prefix = {"polish": "【润色】", "rewrite": "【重写】", "optimize": "【优化】"}.get(kind, "【处理】")
    body = text.replace("。", "。\n\n") if kind == "rewrite" else text
    return prefix + body


def price_for(kind: str, text: str, out_hint: str) -> tuple[int, int]:
    """返回 (输入字数, 输出字数) 用于计价"""
    n = count_words(text)
    if kind in ("detect", "review", "deconstruct", "comment", "inspiration", "setting"):
        return n or 300, 400
    return n or 300, int((n or 300) * 1.1)


def run_text_tool(cid: str, payload: dict, uid: str = "local") -> dict:
    kind = payload.get("action") or "polish"
    if kind not in TOOLS:
        raise LingError("BAD_ACTION", kind)
    model = payload.get("model") or "gemini-3-flash"
    db = load_db()
    target = None
    proj = None
    for pj in db["projects"].values():
        for ch in pj["chapters"]:
            if ch["id"] == cid:
                target, proj = ch, pj
    if not target:
        raise LingError("NOT_FOUND", "章节不存在")
    text = target.get("content") or ""
    in_c, out_c = price_for(kind, text, "")
    est = LING.quote(model, in_c, out_c)
    usage = LING.reserve(uid, est["model"], in_c, out_c)
    try:
        result = tool_output(proj, kind, text, payload)
    except Exception:
        LING.refund(usage["usage_id"])
        raise
    settle = LING.commit(usage["usage_id"], count_words(result))
    return {"ok": True, "action": kind, "label": TOOLS[kind]["label"], "model": est["model"],
            "estimate": est["total"], "charged": settle["charged"], "refunded": settle["refunded"],
            "result": result}


def estimate_generate(pid: str, payload: dict) -> dict:
    pj = get_project(pid)
    kind = payload.get("kind") or "continue"
    n = max(1, min(int(payload.get("chapters") or 1), 5))
    words = max(200, min(int(payload.get("words") or 2000), 8000))
    model = _text_model(payload.get("model") or "")
    if kind == "outline":
        in_chars, out_chars = 800, 1500
    elif kind == "opening":
        in_chars, out_chars = 600 * n, words * n
    else:
        in_chars, out_chars = 1200 * n, words * n
    q = LING.quote(model, in_chars, out_chars)
    return {"kind": kind, "chapters": n, "words": words, "model": q["model"],
            "in_chars": in_chars, "out_chars": out_chars, **q}


def generate(pid: str, payload: dict, uid: str = "local") -> dict:
    """分章正文生成。

    opening / continue：走真模型（_llm_text），字数硬区间分别是 300-500 / 800-1200。
    模型失败才回退 mock_prose，并在返回值里标 fallback=true（逐条 + 汇总）。
    outline：保持原模板行为，不调模型。
    返回值不带价格/预估/token 数：计费只在内部分账，不出现在响应里。
    """
    pj = get_project(pid)
    kind = payload.get("kind") or "continue"
    n = max(1, min(int(payload.get("chapters") or 1), 5))
    words = max(200, min(int(payload.get("words") or 2000), 8000))
    # 不指定模型就用 config/coordinator.json 里的默认模型；
    # 别再写死 gemini-3-flash —— 本地网关没有这个模型名，请求会直接 503。
    model = (payload.get("model") or "").strip()
    prompt_id = payload.get("prompt_id") or {"opening": "official-opening", "continue": "official-continue",
                                              "outline": "official-outline"}.get(kind, "official-continue")
    tpl = next((p["template"] for p in PROMPTS if p["id"] == prompt_id), PROMPTS[1]["template"])

    # 字数硬区间（payload.words 只在区间内微调，不能把首场拉到 3000 字）
    if kind == "opening":
        lo, hi = 300, 500
    elif kind == "outline":
        lo, hi = 0, 0
    else:
        lo, hi = 800, 1200
    target = max(lo, min(hi, words)) if hi else 0
    in_c = 600 * n if kind == "opening" else max(200, 1200 * n)
    out_c = (target or 1200) * n

    def produce():
        produced = []
        any_fallback = False
        if kind == "outline":
            # 保持现状：总纲仍走本地模板，不调模型
            ctx = {"title": pj["title"], "genre": pj["genre"], "idea": pj["idea"], "chapters": n}
            text = fill(tpl, ctx) and mock_prose(pj, "outline", 0, 1200)
            cur = get_project(pid)
            cur["outline"] = text
            put_project(cur)
            produced.append({"kind": "outline", "words": count_words(text),
                             "preview": text[:120], "fallback": False})
            return produced, any_fallback

        start = len(pj["chapters"]) + 1
        prev_tail = (pj["chapters"][-1]["content"] or "")[-400:] if pj["chapters"] else ""
        vol = payload.get("volumeId") or pj["volumes"][0]["id"]
        for i in range(n):
            idx = start + i
            brief = _prose_brief(pj, kind, idx, lo, hi, prev_tail)
            fallback, reason = False, ""
            try:
                text = _fit_len(_llm_text(TEXT_SYSTEM, brief, model, 0.85, hi * 3 + 600), lo, hi)
                # 明显短于下限：给一稿补写机会（只重试一次，避免长尾耗时）
                if count_words(text) < int(lo * 0.7):
                    brief2 = brief + '\n\n【补写要求】上一稿只有 %d 字，太短。整章重写，必须落在 %d-%d 字之间。' % (
                        count_words(text), lo, hi)
                    text2 = _fit_len(_llm_text(TEXT_SYSTEM, brief2, model, 0.9, hi * 3 + 600), lo, hi)
                    if count_words(text2) > count_words(text):
                        text = text2
            except Exception as ex:
                fallback = True
                any_fallback = True
                reason = str(ex)[:160]
                text = mock_prose(pj, kind, idx, words)
            ch = add_chapter(pid, "第%d章 %s" % (idx, payload.get("chapter_title") or "（AI 草稿）"),
                             text, vol, "draft")
            item = {"chapter_id": ch["id"], "index": ch["index"], "words": ch["words"],
                    "status": ch["status"], "fallback": fallback, "preview": text[:80]}
            if reason:
                item["fallback_reason"] = reason
            produced.append(item)
            prev_tail = text[-400:]
        return produced, any_fallback

    (produced, any_fallback), _bill_info = _bill(uid, model, in_c, out_c, produce)
    return {"ok": True, "kind": kind, "model": _CO.map_model(_CO.gateway_cfg(), _text_model(model)),
            "prompt": prompt_id, "words": target,
            "fallback": any_fallback, "produced": produced}


def fill(tpl: str, ctx: dict) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), "")), tpl)


# ---------------- 创作向导（四模式，逐步） ----------------
WCFG = json.load(open(os.path.join(ROOT, "config", "lianzi_wizard.json"), encoding="utf-8"))
DECK = WCFG["deck"]
NINE = WCFG["nine"]

GAN_GE = ["世界", "体系", "阵营", "秘境", "规则", "势力", "王朝", "宗门", "街区"]
REN_GE = ["主角", "少年", "青年", "她", "他", "会计", "警", "少爷", "合同工"]


# 我们的商业模式是「模型成本 × (1 + 代理费)」，不是灵石。
# ling.py 只留作炼字口径的参考实现，不参与产品计费（2026-11-11 YG 定）。
_LAST_BILLING = {"cny": 0.0, "fee_rate": 0.0}


def _fee_rate() -> float:
    try:
        cfg = _CO.load_cfg()
        gw = (cfg.get("gateway") or {}) if isinstance(cfg, dict) else {}
        return float(gw.get("fee_rate") or 0)
    except Exception:
        return 0.0


def _bill(uid: str, model: str, in_c: int, out_c: int, fn):
    """不预扣、不拦余额：跑完按网关实际计费算 ¥（已含代理费）。"""
    before = float(_LAST_BILLING.get("cny") or 0)
    result = fn()
    delta = max(0.0, float(_LAST_BILLING.get("cny") or 0) - before)
    return result, {"cost_cny": round(delta, 4), "fee_rate": _fee_rate()}


def _pick(pool, locks: dict, key: str, seed: str, n: int = 1):
    locked = (locks or {}).get(key)
    if locked:
        return locked if n == 1 else [locked]
    rnd = random.Random("%s-%s" % (seed, key))
    items = list(pool)
    rnd.shuffle(items)
    return items[:n] if n > 1 else items[0]


def wizard_draw(payload: dict, uid: str = "local") -> dict:
    """灵感火花：频道/赛道 + 世界观/人设/金手指/开局/爽点/反派 抽卡，可锁定重抽。"""
    channel = payload.get("channel") or "男频"
    genres = [g[0] for g in WCFG["channels"].get(channel, [])]
    genre = payload.get("genre") or (genres[0] if genres else "都市")
    seed = payload.get("seed") or uuid.uuid4().hex
    locks = payload.get("locks") or {}
    model = payload.get("model") or "gemini-3-flash"

    def build():
        return {
            "channel": channel, "genres": genres, "genre": genre,
            "cards": {
                "world": _pick(DECK["world"], locks, "world", seed),
                "hero": _pick(DECK["hero"], locks, "hero", seed),
                "golden": _pick(DECK["golden"], locks, "golden", seed),
                "hook": _pick(DECK["hook"], locks, "hook", seed),
                "trope": _pick(DECK["trope"], locks, "trope", seed),
                "villain": _pick(DECK["villain"], locks, "villain", seed),
            },
            "labels": {"world": "世界观", "hero": "人设", "golden": "金手指",
                       "hook": "开局钩子", "trope": "爽点机制", "villain": "反派类型"},
            "seed": seed,
        }
    res, bill = _bill(uid, model, 80, 260, build)
    res["bill"] = bill
    return res


def _split_chapters(text: str):
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    marks = list(re.finditer(r"(?m)^\s*(第[0-9一二三四五六七八九十百千]+[章节回][^\n]{0,40})\s*$", text))
    if marks:
        out = []
        for i, m in enumerate(marks):
            body = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
            out.append({"title": m.group(1).strip(), "content": body.strip()})
        return out
    # 无章节标记：按 1500 字切
    size = 1500
    return [{"title": "第%d段" % (i + 1), "content": text[i:i + size]} for i in range(0, len(text), size)]


def _chapter_features(ch: dict):
    body = ch["content"]
    paras = [p for p in re.split(r"\n+", body) if p.strip()]
    dialogue = sum(len(re.findall(r"[“\"「][^”\"」]{2,}[”\"」]", p)) for p in paras)
    return {
        "title": ch["title"], "words": count_words(body),
        "first": body[:40].replace("\n", " "), "last": body[-40:].replace("\n", " "),
        "paragraphs": len(paras), "avg_para": round(count_words(body) / max(1, len(paras))),
        "dialogue_hits": dialogue,
    }


def wizard_imitate(payload: dict, uid: str = "local") -> dict:
    """仿写立项·经典：上传/粘贴参考正文 → 切章 → 分析前 10 章。"""
    text = payload.get("text") or ""
    ref = payload.get("reference") or {}
    model = payload.get("model") or "gemini-3-flash"

    def build():
        chs = _split_chapters(text)
        feats = [_chapter_features(c) for c in chs[:10]]
        total = sum(f["words"] for f in feats) or count_words(text)
        avg_para = round(sum(f["avg_para"] for f in feats) / len(feats)) if feats else 0
        dlg = sum(f["dialogue_hits"] for f in feats)
        hooks = [f["last"] for f in feats[:3] if f["last"]]
        formula = "被夺走 → 拿到凭证 → 借规则反杀" if "账" in text or "合同" in text else "困境 → 意外凭证 → 第一次反击"
        # 章节特征用本地统计（快且可解释）；结构判断与仿写建议交给模型
        llm_rep = None
        try:
            sample = "\n".join(c.get("text", "")[:800] for c in chs[:3])[:2600]
            req = ('下面是参考书前几章的正文。请判断它的结构与爽点，输出 JSON：'
                   '{"formula":"四段式主线","rhythm":"节奏判断","opening_hook":"开篇钩子一句",'
                   '"strengths":["3条"],"suggestions":["3条仿写建议，要具体到怎么做"]}。正文：\n' + sample)
            llm_rep = _llm_json('你是网文主编，只输出 JSON。', req, model, 0.4)
        except Exception as _ex:
            try:
                WSTEP_FALLBACK['imitate'] = str(_ex)
            except Exception:
                pass
        return {
            "reference": ref or {"title": payload.get("title") or "粘贴文本"},
            "chapter_count": len(chs),
            "analyzed": len(feats),
            "features": feats,
            "report": {
                "total_words": total,
                "avg_chapter_words": round(total / max(1, len(feats))),
                "avg_paragraph_words": avg_para,
                "dialogue_density": round(dlg / max(1, sum(f["words"] for f in feats)) * 100, 1),
                "opening_hook": hooks[0] if hooks else "",
                "rhythm": "两章一小反转" if len(feats) >= 3 else "样本不足",
                "formula": formula,
            },
            "llm_report": llm_rep or None,
            "suggestions": (llm_rep or {}).get("suggestions") or [
                "保留结构：开篇 300 字内出冲突",
                "替换题材与人设，动机改成「讨回属于自己的东西」",
                "爽点密度：每 2 章一次小胜，第 7 章第一次打脸",
            ],
        }
    res, bill = _bill(uid, model, max(300, count_words(text)), 900, build)
    res["bill"] = bill
    return res


FIELD_RULES = [
    ("title", r"书名[：:]\s*《?([^》\s，。]{2,20})》?|《([^》\s]{2,20})》"),
    ("protagonist", r"主角[：:]?\s*([^\s，。：]{2,10})"),
    ("genre", r"(都市|玄幻|仙侠|悬疑|言情|历史|科幻|末世|古言|现言|快穿)"),
    ("worldview", r"世界观[：:]\s*([^\s，。]{4,60})"),
    ("golden", r"金手指[：:]\s*([^\s，。]{4,60})"),
]


def wizard_parse(payload: dict, uid: str = "local") -> dict:
    """智能导入立项：解析原始信息 → 字段 + 缺失清单（不落库，等确认）。"""
    text = (payload.get("text") or "").strip()
    model = payload.get("model") or "gemini-3-flash"

    def build():
        # 先用模型抽字段（客户给的是整段想法，正则抽不全）；失败才退回正则
        try:
            req = ('从下面的创作想法里抽取立项字段，输出 JSON：'
                   '{"title":"","genre":"","protagonist":"","worldview":"","golden":"",'
                   '"power_system":"","conflict":"","style":""}；'
                   '抽不到的字段留空字符串，不要编造。原文：\n' + text[:3000])
            data = _llm_json('你是网文编辑，只输出 JSON。', req, model, 0.3)
            if isinstance(data, dict) and any((data.get(k) or '').strip() for k in
                                              ('title', 'genre', 'protagonist', 'worldview', 'golden')):
                fields = {k: (v or '').strip() for k, v in data.items() if isinstance(v, str)}
                need0 = ["title", "genre", "protagonist", "worldview", "golden"]
                missing0 = [k for k in need0 if not fields.get(k)]
                labels0 = {"title": "书名", "genre": "赛道", "protagonist": "主角",
                           "worldview": "世界观", "golden": "金手指"}
                return {"fields": fields, "missing": missing0,
                        "missing_labels": [labels0[m] for m in missing0],
                        "raw": text[:400], "extractor": "llm"}
        except Exception as _ex:
            try:
                WSTEP_FALLBACK['parse'] = str(_ex)
            except Exception:
                pass
        fields = {}
        for key, pat in FIELD_RULES:
            m = re.search(pat, text)
            if m:
                fields[key] = next((g for g in m.groups() if g), "").strip()
        if "title" not in fields and text[:20]:
            fields["title"] = text[:12].strip()
        if "genre" not in fields:
            for g in ("都市", "玄幻", "悬疑", "言情", "历史", "科幻"):
                if g in text:
                    fields["genre"] = g
                    break
        need = ["title", "genre", "protagonist", "worldview", "golden"]
        missing = [k for k in need if not fields.get(k)]
        labels = {"title": "书名", "genre": "赛道", "protagonist": "主角", "worldview": "世界观", "golden": "金手指"}
        return {"fields": fields, "missing": missing, "missing_labels": [labels[m] for m in missing],
                "raw": text[:400]}
    res, bill = _bill(uid, model, max(200, count_words(text)), 400, build)
    res["bill"] = bill
    return res


def _score_dim(text: str, dim: dict) -> dict:
    n = count_words(text)
    dlg = len(re.findall(r"[“\"「][^”\"」]{2,}[”\"」]", text))
    paras = [p for p in re.split(r"\n+", text) if p.strip()]
    base = 55 + (hash(dim["key"] + str(n)) % 30)
    if dim["key"] == "dialogue":
        base = 40 + min(50, dlg)
    if dim["key"] == "rhythm":
        base = 45 + min(45, len(paras) % 40)
    if dim["key"] == "world":
        base = 50 + min(40, sum(1 for w in ("体系", "规则", "世界", "势力", "朝", "宗") if w in text) * 8)
    base = max(30, min(96, base))
    verdict = "强" if base >= 80 else ("中" if base >= 60 else "弱")
    return {"key": dim["key"], "label": dim["label"], "score": base, "weight": dim["weight"], "verdict": verdict, "ask": dim["ask"]}


def wizard_furnace(payload: dict, uid: str = "local") -> dict:
    """熔炉仿写：1-3 本参考 → 九维度评分 → 融合配方建议。"""
    refs = payload.get("refs") or []
    model = payload.get("model") or "gemini-3-flash"
    joined = "\n".join([(r.get("text") or "") if isinstance(r, dict) else str(r) for r in refs])

    def build():
        per_ref = []
        for r in refs[:3]:
            txt = (r.get("text") or "") if isinstance(r, dict) else str(r)
            per_ref.append({
                "title": (r.get("title") if isinstance(r, dict) else "参考%d" % (len(per_ref) + 1)) or "参考",
                "words": count_words(txt),
                "dims": [_score_dim(txt, d) for d in NINE],
            })
        merged = []
        for d in NINE:
            vals = [next((x["score"] for x in ref["dims"] if x["key"] == d["key"]), 60) for ref in per_ref] or [60]
            merged.append({"key": d["key"], "label": d["label"], "weight": d["weight"],
                           "score": round(sum(vals) / len(vals)), "spread": max(vals) - min(vals)})
        total = round(sum(m["score"] * m["weight"] for m in merged))
        return {
            "refs": per_ref, "nine": merged, "total": total,
            "recipes": WCFG["recipes"],
            "suggest": WCFG["recipes"][0]["id"],
            "note": "spread 越大说明该维度可融合空间越大（各参考书差异大）",
        }
    res, bill = _bill(uid, model, max(400, count_words(joined)), 900, build)
    res["bill"] = bill
    return res


def wizard_book(pid: str, payload: dict, uid: str = "local") -> dict:
    """把卡片/分析结果落成立项书，并写入项目字段。"""
    pj = get_project(pid)
    mode = payload.get("mode") or "spark"
    cards = payload.get("cards") or {}
    extra = payload.get("extra") or {}
    model = payload.get("model") or "gemini-3-flash"
    channel = payload.get("channel") or pj.get("channel") or "男频"
    genre = payload.get("genre") or pj.get("genre") or "都市"
    hero_card = cards.get("hero") or pj.get("protagonist") or "陈默"
    world = cards.get("world") or extra.get("worldview") or pj.get("world") or ""
    golden = cards.get("golden") or extra.get("golden") or pj.get("golden_finger") or ""
    hook = cards.get("hook") or ""
    trope = cards.get("trope") or ""
    villain = cards.get("villain") or ""
    title = extra.get("title") or pj.get("title") or "未命名作品"

    def build():
        # 先让模型写立项书（书名/简介/力量体系/总纲/卷纲/前 10 章钩子），失败才用模板
        try:
            req = ('根据以下要素写一份网文立项书，输出 JSON：'
                   '{"title":"","tags":[],"style":"","summary":"200-300字","worldview":"",'
                   '"hero":"","golden_finger":"","power_system":"","main_line":"四段式主线",'
                   '"volumes":[{"title":"","range":"","goal":""}],'
                   '"first10":[{"idx":1,"hook":""}],"pitch":""}。'
                   '要素：频道=%s；赛道=%s；主角=%s；世界规则=%s；金手指=%s；开局钩子=%s；爽点=%s；反派=%s；模式=%s。'
                   '要求：volumes 3 卷（1-50/51-120/121-200），first10 正好 10 条且每条一句钩子。'
                   % (channel, genre, hero_card, world, golden, hook, trope, villain, mode))
            data = _llm_json('你是网文主编，只输出 JSON，不要解释。', req, model, 0.6)
            if isinstance(data, dict) and data.get('summary'):
                book = dict(data)
                book.setdefault('mode', mode)
                book.setdefault('channel', channel)
                book.setdefault('genre', genre)
                book.setdefault('word_goal', int(payload.get('word_goal') or pj.get('word_goal') or 1000000))
                book.setdefault('title', title)
                book.setdefault('worldview', world)
                book.setdefault('hero', hero_card)
                book.setdefault('golden_finger', golden)
                book['prompt_context'] = {
                    '书名': book.get('title', ''), '类型': channel, '题材': genre,
                    '标签': '、'.join(book.get('tags') or []), '文风': book.get('style', ''),
                    '作品简介': book.get('summary', ''), '世界观': book.get('worldview', ''),
                    '主角': book.get('hero', ''), '金手指': book.get('golden_finger', ''),
                    '力量体系': book.get('power_system', ''), '总纲': book.get('main_line', ''),
                    '目标字数': str(book.get('word_goal', '')),
                }
                book['pitch'] = book.get('pitch') or ('《%s》%s · %s｜%s' % (
                    book.get('title', ''), channel, genre, book.get('summary', '')[:40]))
                return book
        except Exception as _ex:
            try:
                WSTEP_FALLBACK['book'] = str(_ex)
            except Exception:
                pass
        summary = "%s：%s被卷入%s。%s，主角只能靠自身底牌翻盘。" % (genre, hero_card, hook or "一场突如其来的变故", trope or "在夹缝里找活路")
        main_line = "① 被夺走 → ② 拿到凭证 → ③ 借规则反杀 → ④ 定价权易主"
        volumes = [
            {"title": "第1卷 退单", "range": "1-50", "goal": "立人设、出第一次小胜"},
            {"title": "第2卷 借刀", "range": "51-120", "goal": "借对手规则做局"},
            {"title": "第3卷 对账", "range": "121-200", "goal": "旧案浮出，主线收束"},
        ]
        first10 = [
            {"idx": i + 1, "hook": (hook if i == 0 else ["第一次反击", "新的证人", "对方改规则", "旧账露头"][(i - 1) % 4])}
            for i in range(10)
        ]
        book = {
            "mode": mode, "title": title, "channel": channel, "genre": genre,
            "tags": [genre, "爽文", "成长"],
            "style": "短句、白描、对白推进，避免总结句",
            "summary": summary,
            "word_goal": int(payload.get("word_goal") or pj.get("word_goal") or 1000000),
            "worldview": world, "hero": hero_card, "golden_finger": golden,
            "hook": hook, "trope": trope, "villain": villain,
            "power_system": extra.get("power_system") or "以「凭证/契约」为力量载体，越高的权限越难取得",
            "main_line": main_line, "volumes": volumes, "first10": first10,
            "pitch": "《%s》%s · %s｜%s" % (title, channel, genre, summary),
        }
        book["prompt_context"] = {
            "书名": title, "类型": channel, "题材": genre, "标签": "、".join(book["tags"]),
            "文风": book["style"], "作品简介": summary, "世界观": world,
            "主角": hero_card, "金手指": golden, "力量体系": book["power_system"],
            "总纲": main_line, "目标字数": str(book["word_goal"]),
        }
        return book
    book, bill = _bill(uid, model, 500, 1400, build)

    pj = get_project(pid)
    pj.update({
        "title": book["title"], "channel": channel, "genre": genre,
        "protagonist": hero_card, "world": world, "golden_finger": golden,
        "idea": book["summary"], "pitch": book["pitch"], "outline": book["main_line"],
        "tags": book["tags"], "style": book["style"], "summary": book["summary"],
        "volumes_plan": book["volumes"], "first10": book["first10"],
        "prompt_context": book["prompt_context"], "wizard_mode": mode,
    })
    put_project(pj)
    book["bill"] = bill
    book["project_id"] = pid
    return book


# ---------------- 导出 / 发布 ----------------
def export_txt(pid: str) -> dict:
    pj = get_project(pid)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    lines = ["《%s》" % pj["title"], "频道：%s  赛道：%s  目标：%d 字" % (pj["channel"], pj["genre"], pj["word_goal"]), ""]
    for ch in pj["chapters"]:
        lines.append(ch["title"])
        lines.append("")
        lines.append(ch.get("content") or "")
        lines.append("")
    path = os.path.join(EXPORT_DIR, "%s-%s.txt" % (re.sub(r"[\\/:*?\"<>|]", "_", pj["title"]), pj["id"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return {"path": path, "chapters": len(pj["chapters"]), "words": sum(c.get("words", 0) for c in pj["chapters"])}


def publish(pid: str) -> dict:
    pj = get_project(pid)
    if not pj["chapters"]:
        raise LingError("EMPTY", "没有章节可发布")
    approved = [c for c in pj["chapters"] if c.get("status") == "approved"]
    if not approved:
        raise LingError("NOT_APPROVED", "没有定稿章节，先审批")
    pj["published"] = True
    pj["published_at"] = now()
    put_project(pj)
    return {"ok": True, "published": True, "chapters": len(approved), "at": pj["published_at"]}



# ---------------- 模型桥（2026-11-11）：四个立项模式必须真调模型 ----------------
# 之前 wizard_* 全是模板拼装（_gen_options/_final_result），和炼字的「options[9] 每次现生成」
# 不是一回事。这里接 coordinator.chat（走本地网关、带客户令牌），失败才退回模板。
import coordinator as _CO  # noqa: E402


def _llm_json(system: str, user: str, model: str = '', temperature: float = 0.7, retries: int = 1) -> dict:
    """要模型输出 JSON。解析失败重试一次；仍失败抛错，由调用方决定是否回退模板。"""
    cfg = {}
    try:
        cfg = _CO.load_cfg()
        cfg = cfg.get('coordinator', cfg) if isinstance(cfg, dict) else {}
    except Exception:
        cfg = {}
    last = None
    for _ in range(retries + 1):
        msgs = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': user}]
        resp = _CO.chat(cfg, msgs)
        try:
            b = resp.get("_billing") or {}
            _LAST_BILLING["cny"] = float(_LAST_BILLING.get("cny") or 0) + float(b.get("total_cny") or 0)
        except Exception:
            pass
        try:
            content = ((resp.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
        except Exception:
            content = ''
        txt = content.strip()
        if txt.startswith('```'):
            txt = re.sub(r'^```[a-zA-Z]*\s*', '', txt)
            txt = re.sub(r'\s*```$', '', txt)
        m = re.search(r'\{.*\}', txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception as ex:
                last = ex
        last = last or ValueError('模型没有返回 JSON')
        user = user + '\n\n只输出一个 JSON 对象，不要解释、不要 Markdown 代码块。'
    raise LingError('LLM_BAD_JSON', str(last))


# ---------------- 正文模型桥（2026-11-11） ----------------
# _llm_json 走的是 JSON 模式，正文要的是纯文本，所以单独一条 _llm_text：
# 直接取 choices[0].message.content，不解析 JSON、不重试 JSON、不拼模板。
TEXT_SYSTEM = (
    '你是中文网文写手。只输出小说正文本身：不要书名/章节标题，不要“以下是正文”这类说明，'
    '不要 Markdown 标记，不要在结尾写字数统计。'
    '用短句、白描、对白推动，避免总结句和书面化连接词；段落之间用空行分隔。'
)


def _text_model(model: str = '') -> str:
    """实际会用的模型名：payload 指定优先，否则取 config/coordinator.json 的默认模型。"""
    if model:
        return str(model).strip()
    try:
        raw = _CO.load_cfg()
        cfg = raw.get('coordinator', raw) if isinstance(raw, dict) else {}
        return str((cfg or {}).get('model') or 'default')
    except Exception:
        return 'default'


def _clean_prose(text: str) -> str:
    """把模型输出洗成能直接进库的正文：去代码块、去标题、去结尾字数括注、收空行。"""
    t = (text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if t.startswith('```'):
        t = re.sub(r'^```[a-zA-Z]*\s*', '', t)
        t = re.sub(r'\s*```$', '', t)
    t = re.sub(r'(?m)^\s*#{1,6}\s*', '', t)          # Markdown 标题
    t = t.replace('**', '')
    # 模型常自作主张在开头补一行章节标题，标题由库里另行写，这里去掉
    t = re.sub(r'^\s*第[0-9一二三四五六七八九十百千两]+[章节回][^\n]{0,40}\n+', '', t)
    # 结尾的「（本章 980 字）」之类统计
    t = re.sub(r'\n*\s*[（(]\s*(本章|全章|全文|共)?\s*[约共]?\s*\d{2,5}\s*字\s*[）)]\s*$', '', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def _balance_quotes(text: str) -> str:
    """截断后如果引号没闭合，补一个右引号，别让正文停在半句对白里。"""
    t = text.rstrip()
    if t.count('“') > t.count('”'):
        t += '”'
    return t


def _fit_len(text: str, lo: int, hi: int) -> str:
    """超过上限先按整段截（保住结尾完整），段落粒度丢太多再按整句截。

    截断点永远落在段落或句子边界上，不切半句；不足下限不硬补
    （短稿交给调用方决定是否重写）。
    """
    if hi <= 0 or count_words(text) <= hi:
        return _balance_quotes(text)
    out, n = [], 0
    for para in [p for p in re.split(r'\n{2,}', text) if p.strip()]:
        w = count_words(para)
        if n + w > hi:
            break
        out.append(para)
        n += w
    body = '\n\n'.join(out).strip()
    if count_words(body) < lo:
        # 按段落切丢太多（模型写成大段），退回按整句切
        out, n = [], 0
        for sent in re.split(r'(?<=[。！？…])', text):
            w = count_words(sent)
            if n + w > hi:
                break
            out.append(sent)
            n += w
        body = ''.join(out).strip()
    return _balance_quotes(body or text[:hi])


def _llm_text(system: str, user: str, model: str = '', temperature: float = 0.85,
              max_tokens: int = 4000) -> str:
    """要模型输出纯文本（正文）。失败抛错，由调用方决定是否回退模板。"""
    cfg = {}
    try:
        raw = _CO.load_cfg()
        cfg = raw.get('coordinator', raw) if isinstance(raw, dict) else {}
    except Exception:
        cfg = {}
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    if model:
        cfg['model'] = model
    cfg['temperature'] = temperature
    if max_tokens:
        cfg['max_tokens'] = int(max_tokens)
    msgs = [{'role': 'system', 'content': system},
            {'role': 'user', 'content': user}]
    resp = _CO.chat(cfg, msgs)
    try:
        b = resp.get('_billing') or {}
        _LAST_BILLING["cny"] = float(_LAST_BILLING.get("cny") or 0) + float(b.get("total_cny") or 0)
    except Exception:
        pass
    try:
        content = ((resp.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
    except Exception:
        content = ''
    text = _clean_prose(content)
    if not text:
        raise LingError('LLM_EMPTY_TEXT', '模型没有返回正文')
    return text


def _prose_brief(pj: dict, kind: str, index: int, lo: int, hi: int, prev_tail: str = '') -> str:
    """把项目要素压成一段写作任务书；空字段不写，避免模型拿空串去编。"""
    bits = []
    if pj.get('title'):
        bits.append('书名《%s》' % pj['title'])
    bits.append('频道 %s' % (pj.get('channel') or '男频'))
    bits.append('赛道 %s' % (pj.get('genre') or '都市'))
    if pj.get('protagonist'):
        bits.append('主角 %s' % pj['protagonist'])
    if pj.get('world'):
        bits.append('世界设定 %s' % pj['world'])
    if pj.get('golden_finger'):
        bits.append('金手指 %s' % pj['golden_finger'])
    if pj.get('style'):
        bits.append('文风 %s' % pj['style'])
    if pj.get('idea'):
        bits.append('核心设定 %s' % str(pj['idea'])[:300])
    head = '【本书要素】' + '；'.join(bits) + '。'

    if kind == 'opening':
        task = ('【任务】写第 %d 章的开场首场戏，只写一场戏、一个场景，%d-%d 字。'
                '要求：前 200 字内就出冲突或异常；人物靠动作和对白立住，不要心理总结；'
                '结尾停在一个具体动作、一句话或一个反常细节上，让读者想往下看。'
                % (index, lo, hi))
        if prev_tail.strip():
            return head + '\n' + task + '\n【前文结尾】\n' + prev_tail.strip()
        return head + '\n' + task

    task = ('【任务】接着上一章往下写第 %d 章，%d-%d 字。'
            '要求：延续上一章结尾的时间、地点、在场人物和情绪，不要跳场景、不要重新介绍人物；'
            '本章至少推进一个具体事件；结尾留一个钩子。' % (index, lo, hi))
    if prev_tail.strip():
        return head + '\n' + task + '\n【上一章结尾原文】\n' + prev_tail.strip()
    return head + '\n' + task + '\n【说明】这是本书的第一章，直接从一个具体场景开始写。'


WSTEP_SYSTEM = (
    '你是网文立项台的策划。只输出 JSON，不要解释。'
    '输出必须严格符合给定的字段结构，options 必须正好 9 条，payload 是一句话的核心设定（后续只用它）。'
)

WSTEP_PROMPTS = {
    'World_Rule_Gen': '为%s《%s》生成 9 条「世界背景/世界规则」候选，必须贴合赛道、能持续产冲突。',
    'Protagonist_Archetype': '已定世界规则：%s。生成 9 个主角人设候选（欲望+缺陷+底线齐全）。',
    'Golden_Finger_Design': '已定世界规则：%s；主角：%s。生成 9 个金手指候选，每个都要写清代价/限制。',
}

# ---------------- 立项向导 · 协议级（POST /api/wizard/step 同构） ----------------
WSTEPS = ["World_Rule_Gen", "Protagonist_Archetype", "Golden_Finger_Design", "Final_Generation"]
WPROG = {"World_Rule_Gen": 25, "Protagonist_Archetype": 50, "Golden_Finger_Design": 75, "Final_Generation": 100}
ANGLES = ["经济货币异化", "制度规则超凡化", "时间法则与信息差", "能力商品化", "阶层跌落与复仇",
          "情绪转化机制", "信仰与职场解构", "概率因果量化", "语言与概念法则"]
TAGSET = [["高概念", "强冲突"], ["反差喜剧", "轻松向"], ["黑暗都市", "智斗"], ["爽感拉满", "日常反差"],
          ["悬疑", "幕后操盘"], ["逆袭", "打脸"], ["群像", "成长流"], ["系统流", "签到变强"], ["脑洞", "玩梗"]]


def _next_step(state: dict) -> str:
    sel = (state or {}).get("selections") or {}
    for s in WSTEPS[:-1]:
        if s not in sel:
            return s
    return "Final_Generation"


def _nine(pool, seed: str, key: str):
    rnd = random.Random("%s-%s" % (seed, key))
    items = list(pool)
    rnd.shuffle(items)
    return items[:9]


def _opt(i: int, text: str, payload: str | None = None, desc: str = "", tags=None, angle: str = ""):
    title = text if len(text) <= 18 else text[:18]
    return {
        "id": "%s_%d" % ("opt", i + 1),
        "title": title,
        "description": desc or text,
        "payload": payload or text,
        "tags": tags or TAGSET[i % len(TAGSET)],
        "angle": angle or ANGLES[i % len(ANGLES)],
    }


def _gen_options(step: str, state: dict, seed: str):
    genre = (state or {}).get("genre") or "都市"
    if step == "World_Rule_Gen":
        pool = _nine(DECK["world"], seed, step)
        return [_opt(i, w, payload="%s：%s" % (genre, w),
                     desc="以「%s」为底层规则重构%s，冲突直接来自规则本身，越守规则的人越吃亏。" % (w, genre))
                for i, w in enumerate(pool)]
    if step == "Protagonist_Archetype":
        pool = _nine(DECK["hero"], seed, step)
        return [_opt(i, h, payload="%s，性格骄傲且深谙潜规则" % h,
                     desc="身份是%s。开局被夺走最在意的东西，靠算清规则反打；缺点是宁可硬扛也不肯低头。" % h)
                for i, h in enumerate(pool)]
    if step == "Golden_Finger_Design":
        pool = _nine(DECK["golden"], seed, step)
        return [_opt(i, g.split("，")[0], payload=g,
                     desc="%s。升级路径：观察取证 → 借规则做局 → 改写规则；限制越用越痛。" % g)
                for i, g in enumerate(pool)]
    return []


def _final_result(state: dict, seed: str):
    sel = state.get("selections") or {}
    world = sel.get("World_Rule_Gen") or state.get("world") or ""
    hero = sel.get("Protagonist_Archetype") or state.get("protagonist") or ""
    golden = sel.get("Golden_Finger_Design") or state.get("golden_finger") or ""
    genre = state.get("genre") or "都市"
    rnd = random.Random(seed)
    titles = [
        "%s：我从今天开始收账！" % genre,
        "退单之后，全城都得还我钱",
        "被夺走的一切，我按规则拿回来",
        "旧账本一翻，大佬全跪了",
        "我只讲真话，你们别装",
        "规则是你们定的，那就按规则来",
        "开局背债，我靠合同反杀",
        "他们叫我废少，直到我拿出凭证",
        "这一单，我要连本带利",
    ]
    rnd.shuffle(titles)
    return {
        "book_title": titles[0],
        "title_candidates": titles,
        "synopsis": "%s：%s。%s，主角只能靠“%s”翻盘——每一次让步都留证据，每一次反击都按合同来。"
                    % (genre, hero, world, golden.split("，")[0]),
        "genre": genre,
        "style": "短句白描、对白推进，避免总结句；每 1500 字一次小反转，每 3000 字一次打脸闭环。",
        "protagonist": hero,
        "golden_finger": golden,
        "power_system": "以「凭证/契约」为力量载体：权限越高，代价越大；违契当场兑现。",
        "conflict": "他要公道，对方要他闭嘴；规则由对方制定，却被他逐条反过来用。",
        "world_focus": world,
        "tags": [genre, "爽文", "逆袭", "规则流"],
    }



WSTEP_FALLBACK = {'last': ''}


def _llm_step(step: str, state: dict, model: str) -> dict:
    """协议级：state + 一句话指令 → 9 个候选 / 立项书。字段与炼字 05 篇一致。"""
    channel = state.get('channel') or '男频'
    genre = state.get('genre') or '都市'
    sels = state.get('selections') or {}
    world = sels.get('World_Rule_Gen') or state.get('world') or ''
    hero = sels.get('Protagonist_Archetype') or state.get('protagonist') or ''
    if step == 'Final_Generation':
        sysmsg = WSTEP_SYSTEM
        user = ('把以下要素合成一份立项书，输出 JSON：'
                '{"final_result":{"book_title":"","title_candidates":[9个],"synopsis":"","genre":"",'
                '"style":"","protagonist":"","golden_finger":"","power_system":"","conflict":"",'
                '"world_focus":"","tags":[]}}。'
                '要素：频道=%s；赛道=%s；世界规则=%s；主角=%s；金手指=%s；'
                '要求：书名要有网文味，synopsis 200-300 字，title_candidates 必须 9 个。'
                % (channel, genre, world, hero, sels.get('Golden_Finger_Design') or ''))
        data = _llm_json(sysmsg, user, model)
        fr = data.get('final_result') or data
        return {'step': {'step_name': step, 'assistant_message': '立项书已生成，可直接开写。',
                         'progress': 100, 'is_final': True, 'options': [], 'final_result': fr},
                'rawOutput': json.dumps(data, ensure_ascii=False)}
    tpl = WSTEP_PROMPTS.get(step) or ''
    if step == 'World_Rule_Gen':
        topic = tpl % (channel, genre)
    elif step == 'Protagonist_Archetype':
        topic = tpl % world
    else:
        topic = tpl % (world, hero)
    user = (topic + '\n输出 JSON：{"options":[{"id":"","title":"","description":"","payload":"",'
            '"tags":[],"angle":""}]}；options 正好 9 条；description 80-120 字；payload 一句话。')
    data = _llm_json(WSTEP_SYSTEM, user, model)
    opts = data.get('options') or []
    if not isinstance(opts, list) or len(opts) < 1:
        raise LingError('LLM_EMPTY_OPTIONS', '模型没给 options')
    for i, o in enumerate(opts):
        o.setdefault('id', 'opt_%d' % (i + 1))
        o.setdefault('tags', [])
        o.setdefault('angle', '')
    msgs = {'World_Rule_Gen': '先定一条能持续产冲突的底层规则。',
            'Protagonist_Archetype': '规则定了，接下来定人：欲望、缺陷、底线。',
            'Golden_Finger_Design': '最后一块：金手指必须有代价。'}
    return {'step': {'step_name': step, 'assistant_message': msgs.get(step, ''),
                     'progress': WPROG[step], 'is_final': False, 'options': opts[:9],
                     'final_result': None},
            'rawOutput': json.dumps(data, ensure_ascii=False)}

def wizard_step(payload: dict, uid: str = "local") -> dict:
    """与炼字 POST /api/wizard/step 同构：state + userAction → 9 个候选或 final_result"""
    state = payload.get("currentState") or {}
    step = payload.get("stepName") or _next_step(state)
    if step not in WSTEPS:
        raise LingError("BAD_STEP", step)
    model = payload.get("model") or "gemini-3-flash"
    seed = payload.get("seed") or uuid.uuid4().hex
    in_c = 3000
    out_c = 1500 if step != "Final_Generation" else 2200

    def build():
        # 先让模型生成；失败才退回模板（模板只作兜底，不再当主路径）
        try:
            return _llm_step(step, state, model)
        except Exception as _ex:
            try:
                WSTEP_FALLBACK['last'] = str(_ex)
            except Exception:
                pass
        if step == "Final_Generation":
            fr = _final_result(state, seed)
            msg = "核心拼图已全部落位！《%s》立项书已生成，直接开写。" % fr["book_title"]
            return {"step": {"step_name": step, "assistant_message": msg, "progress": 100,
                             "is_final": True, "options": [], "final_result": fr},
                    "rawOutput": json.dumps({"step_name": step, "final_result": fr}, ensure_ascii=False)}
        opts = _gen_options(step, state, seed)
        msgs = {
            "World_Rule_Gen": "欢迎来到%s《%s》立项台！先定一条能持续产冲突的底层规则。" % (state.get("channel", "男频"), state.get("genre", "都市")),
            "Protagonist_Archetype": "规则定了，接下来定人：欲望、缺陷、底线，三样都要有。",
            "Golden_Finger_Design": "最后一块拼图：金手指必须有代价，否则撑不住长篇。",
        }
        return {"step": {"step_name": step, "assistant_message": msgs.get(step, ""),
                         "progress": WPROG[step], "is_final": False,
                         "options": opts, "final_result": None},
                "rawOutput": json.dumps({"step_name": step, "options": opts}, ensure_ascii=False)}

    res, bill = _bill(uid, model, in_c, out_c, build)
    res["usage"] = {"promptTokens": in_c, "completionTokens": out_c,
                    "thinkingTokens": 0, "totalTokens": in_c + out_c}
    res["bill"] = bill
    res["_next"] = _next_step({"selections": {**(state.get("selections") or {}), **({step: "x"} if step != "Final_Generation" else {})}})
    return res

def save_entries(pid, entries):
    """设定库条目（角色/地点/势力/规则）。整表覆盖，前端提交全量。"""
    db = load_db()
    pj = (db.get("projects") or {}).get(pid)
    if not pj:
        raise KeyError("project not found: %s" % pid)
    clean = []
    for e in (entries or []):
        kind = str((e or {}).get("kind") or "").strip()
        name = str((e or {}).get("name") or "").strip()
        if kind not in ("character", "place", "faction", "rule") or not name:
            continue
        clean.append({"id": str(e.get("id") or uuid.uuid4().hex[:12]),
                      "kind": kind, "name": name[:40], "note": str(e.get("note") or "")[:200]})
    pj["entries"] = clean
    save_db(db, "entries")
    return {"entries": clean, "count": len(clean)}
