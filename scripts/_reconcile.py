import json, sqlite3, urllib.request, time

# 拿令牌
con = sqlite3.connect(r"D:\relay\data\new-api.db")
cur = con.cursor()
cur.execute("SELECT key FROM tokens WHERE id=1")
token = "sk-" + cur.fetchone()[0]
con.close()

# 固定 prompt（约 1000 字中文 ≈ 700 token）
prompt_text = "请把下面这段话改得更紧凑，只输出改后结果，不要解释：" + "雾没散。他从铺子门口退出来，米袋在肩上搭着。" * 50

print("=== 单次对账：deepseek-v4-pro ===")
body = json.dumps({
    "model": "deepseek-v4-pro",
    "messages": [{"role": "user", "content": prompt_text}],
    "max_tokens": 300,
    "temperature": 0.3,
    "thinking": {"type": "disabled"},
}).encode("utf-8")

req = urllib.request.Request("http://127.0.0.1:3000/v1/chat/completions", data=body,
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + token}, method="POST")

try:
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    u = d.get("usage") or {}
    p = u.get("prompt_tokens", 0)
    c = u.get("completion_tokens", 0)
    print("  prompt_tokens: %d" % p)
    print("  completion_tokens: %d" % c)
    print("  total_tokens: %d" % u.get("total_tokens", 0))
    print("  upstream_model: %s" % d.get("model"))

    # 查网关刚记的 quota
    time.sleep(1.5)
    con = sqlite3.connect(r"D:\relay\data\new-api.db")
    cur = con.cursor()
    cur.execute("SELECT model_name, quota, prompt_tokens, completion_tokens FROM logs WHERE type=2 ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    con.close()
    if row:
        m, q, lp, lc = row
        gw_cny = (q or 0) / 500000 * 7.3
        print()
        print("=== 网关记账 ===")
        print("  model_name: %s" % m)
        print("  prompt=%s completion=%s" % (lp, lc))
        print("  quota: %s" % q)
        print("  quota 折算: %.6f 元" % gw_cny)

        # 官方价（空闲时段，半价）
        official_in = 4.5 / 1e6   # 元/token
        official_out = 13.5 / 1e6
        official = p * official_in + c * official_out
        print()
        print("=== 官方成本（deepseek-v4-pro 空闲价 4.5/13.5 元/百万）===")
        print("  输入 %.6f 元 + 输出 %.6f 元 = %.6f 元" % (p*official_in, c*official_out, official))
        print()
        print("=== 我们的售价（+5%）===")
        print("  应为: %.6f 元" % (official * 1.05))
        print()
        print("=== 对比 ===")
        if official > 0:
            ratio = gw_cny / official
            print("  网关收 / 官方成本 = %.2f 倍" % ratio)
            if ratio < 0.95:
                print("  ❌ 少收（成本倒挂）")
            elif ratio > 1.15:
                print("  ⚠️ 多收")
            else:
                print("  ✅ 正常")
except Exception as e:
    print("  ERR:", type(e).__name__, str(e)[:200])
    if hasattr(e, "read"):
        try: print("  body:", e.read()[:400])
        except: pass