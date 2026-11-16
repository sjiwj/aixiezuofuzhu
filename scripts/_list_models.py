import sqlite3
con = sqlite3.connect(r"D:\relay\data\new-api.db")
cur = con.cursor()
cur.execute("SELECT DISTINCT model FROM abilities WHERE enabled=1 ORDER BY model")
models = [r[0] for r in cur.fetchall()]
con.close()

print("=== 网关所有可用模型 ===")
for m in models:
    print("  " + m)

print()
print("=== 含 flash 的 ===")
for m in models:
    if "flash" in m.lower():
        print("  " + m)

print()
print("=== 含 v4.1 的 ===")
hit = [m for m in models if "v4.1" in m]
print("  " + (", ".join(hit) if hit else "❌ 一个都没有"))