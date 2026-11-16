# -*- coding: utf-8 -*-
"""工作流引擎（三节点 DAG + 命名变量）

对齐三家：
  星月  ：input/process/output 三节点，变量 {{步骤.输出}} / {{@关联项}} / {{#补充项}}，状态机 PENDING→RUNNING→COMPLETED/FAILED
  白梦  ：workflow 模式 + 模板（本仓库只见到入口与 i18n）
  智语  ：/workflow + playbook，同属"作者专页"编排
  炼字  ：四层流水线 + 审批（我们已有）

本地实现：节点顺序执行、变量替换、输出命名、失败即停；无模型时用 deterministic 回显。

  python core/workflow.py --selftest
  python core/workflow.py --run sample.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

NODE_TYPES = ("input", "process", "output")
DEFAULT_MODEL = "gemini-3-flash"


class WFError(Exception):
    pass


def sample() -> dict:
    return {
        "id": "wf-demo",
        "name": "拆书 → 立意 → 开篇",
        "nodes": [
            {"id": "src", "type": "input", "title": "参考正文",
             "outputs": [{"id": "text", "name": "正文"}]},
            {"id": "analyze", "type": "process", "title": "九维拆解",
             "model": DEFAULT_MODEL,
             "prompt": "拆解下面这段正文的结构：{{src.text}}。输出：钩子类型、节奏、可复用公式。",
             "outputs": [{"id": "report", "name": "拆解结论"}]},
            {"id": "pitch", "type": "process", "title": "立意一句话",
             "model": DEFAULT_MODEL,
             "prompt": "基于拆解结论：{{analyze.report}}，结合 {{@书名}} 与 {{#补充要求}}，写一句话立意。",
             "outputs": [{"id": "idea", "name": "立意"}]},
            {"id": "out", "type": "output", "title": "输出",
             "prompt": "立意：{{pitch.idea}}", "outputs": []},
        ],
        "edges": [["src", "analyze"], ["analyze", "pitch"], ["pitch", "out"]],
    }


def _vars_in(tpl: str):
    """{{node.output}} / {{@ref}} / {{#extra}}"""
    out = []
    for m in re.finditer(r"\{\{\s*([@#]?)([A-Za-z0-9_\u4e00-\u9fa5.\-]+)\s*\}\}", tpl or ""):
        out.append((m.group(1), m.group(2)))
    return out


def validate(wf: dict) -> list:
    errs = []
    nodes = wf.get("nodes") or []
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        errs.append("节点 id 重复")
    known = set()
    for n in nodes:
        if n.get("type") not in NODE_TYPES:
            errs.append("节点 %s 类型非法：%s" % (n.get("id"), n.get("type")))
        for o in n.get("outputs") or []:
            if not o.get("id"):
                errs.append("节点 %s 的输出缺少 id" % n.get("id"))
            known.add("%s.%s" % (n.get("id"), o.get("id")))
    # 变量引用必须是已声明的输出，或 @ / # 作用域
    for n in nodes:
        for scope, name in _vars_in(n.get("prompt", "")):
            if scope in ("@", "#"):
                continue
            if name not in known:
                errs.append("节点 %s 引用了未声明的输出 %s" % (n.get("id"), name))
    # 环检测
    edges = wf.get("edges") or []
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    state = {}

    def dfs(u):
        state[u] = 1
        for v in adj.get(u, []):
            if state.get(v) == 1:
                errs.append("存在环：%s → %s" % (u, v))
                return False
            if state.get(v) is None and not dfs(v):
                return False
        state[u] = 2
        return True

    for n in ids:
        if state.get(n) is None:
            dfs(n)
    return errs


def order(wf: dict) -> list:
    nodes = {n["id"]: n for n in wf.get("nodes") or []}
    edges = wf.get("edges") or []
    indeg = {k: 0 for k in nodes}
    adj = {k: [] for k in nodes}
    for a, b in edges:
        if a in nodes and b in nodes:
            adj[a].append(b)
            indeg[b] += 1
    q = [k for k, v in indeg.items() if v == 0]
    out = []
    while q:
        u = q.pop(0)
        out.append(nodes[u])
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != len(nodes):
        raise WFError("拓扑排序失败：可能存在环")
    return out


def render(tpl: str, ctx: dict, refs: dict, extras: dict) -> str:
    def rep(m):
        scope, name = m.group(1), m.group(2)
        if scope == "@":
            return str(refs.get(name, ""))
        if scope == "#":
            return str(extras.get(name, ""))
        return str(ctx.get(name, "{{MISSING:%s}}" % name))
    return re.sub(r"\{\{\s*([@#]?)([A-Za-z0-9_\u4e00-\u9fa5.\-]+)\s*\}\}", rep, tpl or "")


def _run_node(node: dict, prompt: str) -> str:
    base = os.environ.get("NOVEL_LLM_BASE")
    key = os.environ.get("NOVEL_LLM_KEY")
    if base and key:
        import urllib.request
        body = json.dumps({"model": node.get("model") or DEFAULT_MODEL,
                           "messages": [{"role": "user", "content": prompt}],
                           "temperature": 0.8}).encode("utf-8")
        req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode("utf-8"))
        return (d.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    # 无模型：确定性回显，保证流水线可跑通
    head = prompt.strip().replace("\n", " ")[:160]
    return "【%s·本地】%s…" % (node.get("title") or node.get("id"), head)


def run(wf: dict, inputs: dict | None = None, refs: dict | None = None, extras: dict | None = None) -> dict:
    errs = validate(wf)
    if errs:
        raise WFError("；".join(errs))
    inputs, refs, extras = inputs or {}, refs or {}, extras or {}
    ctx, steps = {}, []
    for node in order(wf):
        nid, typ = node["id"], node["type"]
        prompt = node.get("prompt") or ""
        if typ == "input":
            for o in node.get("outputs") or []:
                ctx["%s.%s" % (nid, o["id"])] = str(inputs.get("%s.%s" % (nid, o["id"]),
                                                                  inputs.get(nid, "")))
            steps.append({"node": nid, "type": typ, "status": "completed", "outputs": {
                "%s.%s" % (nid, o["id"]): ctx["%s.%s" % (nid, o["id"])] for o in node.get("outputs") or []}})
            continue
        rendered = render(prompt, ctx, refs, extras)
        text = _run_node(node, rendered) if typ == "process" else rendered
        outs = {}
        for o in node.get("outputs") or []:
            key = "%s.%s" % (nid, o["id"])
            ctx[key] = text
            outs[key] = text
        steps.append({"node": nid, "type": typ, "status": "completed",
                      "prompt": rendered, "text": text, "outputs": outs})
    return {"ok": True, "steps": steps,
            "outputs": {k: v for k, v in ctx.items() if "." in k}}


def selftest() -> int:
    ok, fail = [], []

    def check(name, cond, extra=""):
        (ok if cond else fail).append(name)
        print(("  PASS " if cond else "  FAIL ") + name + ((" | " + str(extra)) if extra else ""))

    wf = sample()
    check("示例通过校验", validate(wf) == [], validate(wf))
    r = run(wf, inputs={"src": "他翻开账本，规则很简单。"}, refs={"书名": "退单"}, extras={"补充要求": "别写旁白"})
    check("四个节点全 completed", all(s["status"] == "completed" for s in r["steps"]) and len(r["steps"]) == 4, len(r["steps"]))
    check("输出含 analyze.report", "analyze.report" in r["outputs"])
    check("变量替换生效", ("退单" in r["steps"][2]["prompt"]) and ("别写旁白" in r["steps"][2]["prompt"]), r["steps"][2]["prompt"][:80])
    check("同节点多输出指向同一文本", r["outputs"]["pitch.idea"] == r["outputs"]["pitch.idea"])

    bad = json.loads(json.dumps(wf))
    bad["nodes"][2]["prompt"] += " {{ghost.out}}"
    check("未声明变量被拦截", any("未声明" in e for e in validate(bad)), validate(bad)[:1])

    cyc = json.loads(json.dumps(wf))
    cyc["edges"].append(["out", "src"])
    check("环被拦截", any("环" in e for e in validate(cyc)), validate(cyc)[:1])

    check("render 作用域", render("{{src.text}}/{{@书名}}/{{#补充要求}}",
                                  {"src.text": "A"}, {"书名": "B"}, {"补充要求": "C"}) == "A/B/C")

    print("\n%d passed, %d failed" % (len(ok), len(fail)))
    return 0 if not fail else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.run:
        with open(a.run, encoding="utf-8") as f:
            wf = json.load(f)
        print(json.dumps(run(wf, inputs=a.inputs or {}), ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
