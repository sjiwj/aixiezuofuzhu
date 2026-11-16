import json, os
f = os.path.join(os.environ["APPDATA"], "novelapp-desktop", "data", "projects", "<书名>", "章节", ".stages.json")
with open(f, encoding="utf-8") as fh:
    d = json.load(fh)

print("=== 修前 ===")
for k in sorted(d):
    print("  %s: %s" % (k, d[k].get("stage")))

# 004 和 006 是 AI 写完但卡在 working，改成 awaiting
for k in ("004", "006"):
    if k in d and d[k].get("stage") == "working":
        d[k]["stage"] = "awaiting"
        d[k]["reason"] = "已完成四层流水线（状态从 working 纠正）"
        d[k]["updated"] = "2026-11-07 04:05:00"
        print()
        print("  %s: working -> awaiting" % k)

with open(f, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=1)

print()
print("=== 修后 ===")
for k in sorted(d):
    print("  %s: %s" % (k, d[k].get("stage")))