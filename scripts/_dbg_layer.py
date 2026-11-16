import sys, os, json
sys.path.insert(0, r"D:\NovelApp\core")
os.environ.setdefault("NOVELAPP_ROOT", r"D:\NovelApp")
import coordinator as CO

print("=== resolve_layer(writing) ===")
L = CO.resolve_layer("writing")
for k, v in L.items():
    print("  %-15s = %r  (type=%s)" % (k, v, type(v).__name__))

print()
print("=== 关键判断 ===")
t = L.get("thinking")
print("  thinking = %r (type=%s)" % (t, type(t).__name__))
print("  thinking is False -> %s" % (t is False))
print("  -> 会设 extra_body: %s" % (t is False))

print()
print("=== 如果 extra_body 设了，chat_stream 会怎么传 ===")
call_cfg = {"model": L.get("model"), "temperature": L.get("temperature", 0.8)}
if L.get("max_tokens"):
    call_cfg["max_tokens"] = int(L["max_tokens"])
if L.get("thinking") is False:
    call_cfg["extra_body"] = {"thinking": {"type": "disabled"}}
print("  call_cfg = %s" % json.dumps(call_cfg, ensure_ascii=False))