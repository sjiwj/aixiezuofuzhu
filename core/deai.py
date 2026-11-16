# -*- coding: utf-8 -*-
"""降 AI 味（de-AI）· 复刻降得快的四阶段改写

对齐依据（公开前端逆向，见知识库 09 篇）：
  请求：{text, type, version, level}
        type   ∈ novel | script | media | paper
        version∈ v3.2 | v3.3 | v4.0 | v1.0(学术)
        level  ∈ 1 低 | 2 中 | 3 高
  阶段：q3_rewrite（分段重写，带 linesDone/linesTotal）
        agent_review（审校：start → reasoning(流式 thinking) → revise_start(第 N 轮) → done）
        final_optimize（整体润色）
  限制：普通 10000 字；论文/学术 20000 字

本地实现：
  - 规则引擎负责"可解释的改写"（连接词、长句、被动、总结句、段落长度、短句占比）；
  - 规则覆盖不到的语义层面，交给 LLM（配 NOVEL_LLM_BASE/KEY 时启用）；
  - 每轮 review 用指标判断是否收敛，最多 level+1 轮；
  - 输出带 stages 与 metrics，前端据此显示"正在消痕 x/y"。

  python core/deai.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

LIMITS = {"paper": (20000, 40000), "v1.0": (20000, 40000)}  # (maxChars, maxRawChars)
DEFAULT_LIMIT = (10000, 20000)

# —— 规则表：可解释、可统计 ——
CONNECTIVES = {
    "因此": "结果", "然而": "可是", "此外": "另外", "综上所述": "说到底",
    "值得注意的是": "有意思的是", "总而言之": "说白了", "首先": "一开始",
    "其次": "接着", "最后": "末了", "与此同时": "同一时间", "由此可见": "这么看",
    "不可否认": "说实话", "毋庸置疑": "明摆着", "在一定程度上": "多少",
}
EMPTY_WORDS = ["非常", "十分", "极其", "显著", "极大", "充分", "有效"]
HEDGES = ["可以说", "某种程度上", "从某种意义上讲", "客观来讲"]
SUMMARY_PATTERNS = [
    r"这[一]?[切些][^。！？]{0,20}(说明|表明|意味着)[^。！？]{0,30}[。！？]",
    r"(总之|综上|总的来说)[^。！？]{0,60}[。！？]",
]


def count_chars(s: str) -> int:
    return len(re.sub(r"\s+", "", s or ""))


def split_sentences(text: str):
    return re.findall(r"[^。！？…\n]+[。！？…]?", text)


def stats(text: str) -> dict:
    sents = [s.strip() for s in split_sentences(text) if s.strip()]
    lens = [count_chars(s) for s in sents] or [0]
    paras = [p for p in re.split(r"\n+", text) if p.strip()]
    conn = sum(text.count(k) for k in CONNECTIVES)
    short_ratio = sum(1 for x in lens if x <= 12) / max(1, len(lens))
    avg = sum(lens) / max(1, len(lens))
    var = sum((x - avg) ** 2 for x in lens) / max(1, len(lens))
    return {
        "chars": count_chars(text), "sentences": len(sents), "avg_len": round(avg, 1),
        "len_var": round(var, 1), "short_ratio": round(short_ratio, 2),
        "paragraphs": len(paras), "avg_para": round(sum(count_chars(p) for p in paras) / max(1, len(paras)), 1),
        "connectives": conn, "conn_per_k": round(conn / max(1, count_chars(text)) * 1000, 1),
    }


def _rewrite_paragraph(p: str, level: int, log: dict) -> str:
    t = p
    for a, b in CONNECTIVES.items():
        if a in t:
            log["connectives"] += t.count(a)
            t = t.replace(a, b if level >= 2 else "")
    if level >= 2:
        for w in EMPTY_WORDS:
            if w in t:
                log["empty_words"] += t.count(w)
                t = t.replace(w, "")
        for h in HEDGES:
            if h in t:
                log["hedges"] += t.count(h)
                t = t.replace(h + "，", "").replace(h, "")
    if level >= 3:
        for pat in SUMMARY_PATTERNS:
            for m in re.finditer(pat, t):
                log["summary"] += 1
            t = re.sub(pat, "", t)
    # 长句拆短：> 45 字按逗号切一次
    out = []
    for s in split_sentences(t):
        if count_chars(s) > 45 and "，" in s:
            parts = s.split("，")
            mid = len(parts) // 2
            out.append("，".join(parts[:mid]) + "。")
            out.append("，".join(parts[mid:]))
            log["split"] += 1
        else:
            out.append(s)
    t = "".join(out)
    # 段落过长切段
    if count_chars(t) > 140:
        chunks, cur = [], ""
        for s in split_sentences(t):
            if count_chars(cur) + count_chars(s) > 110:
                chunks.append(cur); cur = s
            else:
                cur += s
        if cur:
            chunks.append(cur)
        t = "\n\n".join(chunks)
        log["split_para"] += 1
    return t.strip()


def _llm_conf():
    """拿网关地址/令牌/模型：优先环境变量，其次 coordinator 的网关配置。

    这样产品侧不用多配一套 env —— 网关与客户令牌本来就在 config 里。
    """
    base = (os.environ.get("NOVEL_LLM_BASE") or "").strip()
    key = (os.environ.get("NOVEL_LLM_KEY") or "").strip()
    model = (os.environ.get("NOVEL_LLM_MODEL") or "").strip()
    if not (base and key):
        try:
            import coordinator as CO
            g = CO.gateway_cfg({}) or {}
            base = base or (g.get("base") or "")
            key = key or (g.get("key") or g.get("api_key") or g.get("downstream_key") or "")
            model = model or (g.get("model") or "")
        except Exception:
            pass
    if not model:
        try:
            import coordinator as CO
            raw = CO.load_cfg()
            cfg = raw.get("coordinator", raw) if isinstance(raw, dict) else {}
            model = (cfg or {}).get("model") or ""
        except Exception:
            model = ""
    return base, key, (model or "deepseek-flash")


def _llm_rewrite(text: str, ptype: str, version: str, level: int) -> str:
    base, key, model = _llm_conf()
    if not base or not key:
        return ""
    import urllib.request
    tone = {1: "轻度", 2: "中度", 3: "彻底"}[level]
    prompt = (
        "你是资深网文编辑。把下面的正文改写成更自然的人工写作：\n"
        "1) 保留全部情节、人物、信息，不增删事实；\n"
        "2) 打散模板化句式与三段排比，长短句交错，短句占比 >30%%；\n"
        "3) 去掉总结句、'因此/然而/综上所述'这类硬连接词；\n"
        "4) 对白要像人说话，允许省略与停顿；\n"
        "改写强度：%s。只输出改写后的正文。\n\n正文：\n%s" % (tone, text)
    )
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.85}).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8"))
    return (d.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""


def rewrite(text: str, ptype: str = "novel", version: str = "v4.0", level: int = 2,
            use_llm: bool = True) -> dict:
    if ptype not in ("novel", "script", "media", "paper"):
        raise ValueError("bad type: %s" % ptype)
    if version not in ("v3.2", "v3.3", "v4.0", "v1.0"):
        raise ValueError("bad version: %s" % version)
    level = max(1, min(3, int(level)))
    max_chars = LIMITS.get(ptype) or LIMITS.get(version) or DEFAULT_LIMIT
    limit = max_chars[0]
    src = (text or "").strip()
    if count_chars(src) > limit:
        raise ValueError("单次最多 %d 字" % limit)

    before = stats(src)
    stages, log = [], {"connectives": 0, "empty_words": 0, "hedges": 0, "summary": 0,
                       "split": 0, "split_para": 0}
    # —— 阶段 1：分段重写（q3_rewrite）——
    paras = [p for p in re.split(r"\n+", src) if p.strip()]
    rewritten = []
    for i, p in enumerate(paras, 1):
        rewritten.append(_rewrite_paragraph(p, level, log))
        stages.append({"phase": "q3_rewrite", "linesDone": i, "linesTotal": len(paras)})
    out = "\n\n".join(rewritten)

    # —— 阶段 2：审校（agent_review），按指标决定是否再改 ——
    rounds = 0
    max_rounds = 1 + (level - 1)
    while rounds < max_rounds:
        st = stats(out)
        needs = st["conn_per_k"] > 3 or st["short_ratio"] < 0.25 or st["avg_len"] > 32
        stages.append({"phase": "agent_review", "step": "reasoning", "leg": "review-%d" % (rounds + 1),
                       "delta": "指标：连接词 %.1f/千字，短句占比 %.0f%%，平均句长 %.1f → %s"
                                % (st["conn_per_k"], st["short_ratio"] * 100, st["avg_len"],
                                   "需要再改一轮" if needs else "已达标")})
        if not needs:
            stages.append({"phase": "agent_review", "step": "done", "round": rounds + 1})
            break
        rounds += 1
        stages.append({"phase": "agent_review", "step": "revise_start", "round": rounds})
        ps = [p for p in re.split(r"\n+", out) if p.strip()]
        out = "\n\n".join(_rewrite_paragraph(p, 3, log) for p in ps)
        stages.append({"phase": "agent_review", "step": "revise_done", "round": rounds})

    # —— 阶段 3：整体润色（final_optimize）——
    if use_llm:
        llm_out = _llm_rewrite(out, ptype, version, level)
        if llm_out.strip():
            out = llm_out.strip()
            stages.append({"phase": "final_optimize", "by": "llm"})
    stages.append({"phase": "final_optimize", "by": "rules"})

    after = stats(out)
    return {
        "output": out,
        "stages": stages,
        "metrics": {
            "inputChars": before["chars"], "outputChars": after["chars"],
            "chunkCount": len(paras), "rounds": rounds,
            "before": before, "after": after,
            "hits": log,
            "char_keep_ratio": round(after["chars"] / max(1, before["chars"]), 3),
        },
        "params": {"type": ptype, "version": version, "level": level},
    }


def selftest() -> int:
    sample = (
        "因此，我们需要重视这个问题。然而，很多人并没有意识到它的严重性。\n\n"
        "值得注意的是，这个问题非常复杂，涉及多个方面。首先，它影响到个人的生活；其次，它影响到团队协作；最后，它还会影响整个行业的效率。\n\n"
        "综上所述，我们可以说，只有充分认识并有效解决这个问题，才能实现更好的发展。"
    )
    ok, fail = [], []

    def check(name, cond, extra=""):
        (ok if cond else fail).append(name)
        print(("  PASS " if cond else "  FAIL ") + name + ((" | " + str(extra)) if extra else ""))

    r = rewrite(sample, "novel", "v4.0", 3, use_llm=False)
    b, a = r["metrics"]["before"], r["metrics"]["after"]
    check("连接词下降", a["connectives"] < b["connectives"], (b["connectives"], a["connectives"]))
    check("连接词密度下降", a["conn_per_k"] <= b["conn_per_k"], (b["conn_per_k"], a["conn_per_k"]))
    check("有 q3_rewrite 阶段", any(s["phase"] == "q3_rewrite" for s in r["stages"]))
    check("有 agent_review reasoning", any(s.get("step") == "reasoning" for s in r["stages"]))
    check("有 final_optimize", any(s["phase"] == "final_optimize" for s in r["stages"]))
    check("字数保留 >70%", r["metrics"]["char_keep_ratio"] > 0.7, r["metrics"]["char_keep_ratio"])
    check("不再出现「因此」", "因此" not in r["output"])
    check("不再出现「综上所述」", "综上所述" not in r["output"])

    # 限额
    try:
        rewrite("字" * 10001, "novel", "v4.0", 2, use_llm=False)
        check("超限应报错", False)
    except ValueError:
        check("超限报错", True)
    try:
        rewrite("字" * 15000, "paper", "v1.0", 2, use_llm=False)
        check("论文 1.5 万字允许", True)
    except ValueError as e:
        check("论文 1.5 万字允许", False, e)

    print("\n%d passed, %d failed" % (len(ok), len(fail)))
    return 0 if not fail else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--type", default="novel")
    ap.add_argument("--version", default="v4.0")
    ap.add_argument("--level", type=int, default=2)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            r = rewrite(f.read(), a.type, a.version, a.level)
        print(json.dumps({"metrics": r["metrics"], "stages": r["stages"][-4:]}, ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())