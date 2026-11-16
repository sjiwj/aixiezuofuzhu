# -*- coding: utf-8 -*-
"""把 5 处 ctx.tools.register 改成 regTool，收集定义后按模式注册。"""
import io, os, sys

P = r"D:\NovelApp\plugin\lib\index.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "function regTool" in s:
    print("ALREADY"); sys.exit(0)

# 1) 5 处改成 regTool
n = s.count("  ctx.tools.register({\n")
print("found register calls:", n)
s = s.replace("  ctx.tools.register({\n", "  regTool({\n")

# 2) 在第一处 regTool 之前插入定义
ANCHOR = "  // ---------- 1. \u5217\u7ae0\u8282 ----------"
i = s.find(ANCHOR)
if i < 0:
    print("anchor missing"); sys.exit(1)

BLOCK = """
  // ---------- 工具按模式注册 ----------
  // dsh-tools 的 register() 返回注销器，所以能切模式时动态增减。
  // 通用模式保留：质检（看格式用）+ 本地 API 地址（通道，无害）
  const KEEP_IN_GENERAL = ['novel_qc_run', 'novel_app_api']
  const TOOL_DEFS = []
  let toolDisposers = []

  function regTool(def) {
    TOOL_DEFS.push(def)
  }

  function applyTools(mode) {
    for (const d of toolDisposers) {
      try { if (typeof d === 'function') d() } catch (e) { /* 注销失败不阻断 */ }
    }
    toolDisposers = []
    for (const def of TOOL_DEFS) {
      const keep = mode === 'writing' || KEEP_IN_GENERAL.includes(def.name)
      if (!keep) continue
      try {
        const d = ctx.tools.register(def)
        if (typeof d === 'function') toolDisposers.push(d)
      } catch (e) {
        if (!String(e && e.message).includes('already registered')) {
          try { ctx.logger?.warn?.('[novelapp] 注册工具失败 ' + def.name + ': ' + e) } catch (e2) { /* ignore */ }
        }
      }
    }
  }

"""
s = s[:i] + BLOCK + s[i:]

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("regTool added, chars =", len(s))
