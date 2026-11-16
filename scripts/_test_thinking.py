import json, sqlite3, urllib.request

con = sqlite3.connect(r"D:\relay\data\new-api.db")
cur = con.cursor()
cur.execute("SELECT key FROM tokens WHERE id=1")
token = "sk-" + cur.fetchone()[0]
con.close()

def test(model, extra, label):
    body = {"model": model, "messages": [{"role": "user", "content": "写一段 200 字的雪景描写。"}],
            "max_tokens": 500, "stream": True, "stream_options": {"include_usage": True}}
    body.update(extra)
    req = urllib.request.Request("http://127.0.0.1:3000/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST")
    rn = 0
    cn = 0
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            for line in r:
                s = line.decode("utf-8", "replace").strip()
                if not s.startswith("data:"):
                    continue
                p = s[5:].strip()
                if p == "[DONE]":
                    break
                try:
                    d = json.loads(p)
                except Exception:
                    continue
                ch = (d.get("choices") or [{}])[0].get("delta") or {}
                if ch.get("reasoning_content"):
                    rn += 1
                if ch.get("content"):
                    cn += 1
    except Exception as e:
        print("  %-40s ERR %s" % (label, str(e)[:60]))
        return
    print("  %-40s reasoning块=%-4d 正文块=%-4d" % (label, rn, cn))

print("=== deepseek-flash 不同参数下会不会思考 ===")
test("deepseek-flash", {}, "不带参数")
test("deepseek-flash", {"thinking": {"type": "disabled"}}, "thinking:disabled")
test("deepseek-flash", {"reasoning_effort": "low"}, "reasoning_effort:low")

print()
print("=== deepseek-v4-pro 对照 ===")
test("deepseek-v4-pro", {}, "不带参数")
test("deepseek-v4-pro", {"thinking": {"type": "disabled"}}, "thinking:disabled")