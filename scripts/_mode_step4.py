# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\index.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "MODE.onChange" in s:
    print("ALREADY"); sys.exit(0)

# 在 apply() 结尾（最后一个 '})' + '
}' ）之前插入
ANCHOR = "  })\n}\n\nexport default { name, inject, apply }"
if ANCHOR not in s:
    print("anchor missing"); sys.exit(1)

BLOCK = """  })

  // ---------- 首次注册 + 监听模式切换 ----------
  applyTools(MODE.get())
  MODE.onChange(function (mode) {
    applyTools(mode)
    try { ctx.logger?.info?.('[novelapp] 模式切换 ' + mode + '，工具已重新注册') } catch (e) { /* ignore */ }
  })
}

export default { name, inject, apply }"""
s = s.replace(ANCHOR, BLOCK, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("apply + onChange added")