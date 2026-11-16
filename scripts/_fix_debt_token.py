# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
s = io.open(p, encoding="utf-8").read()
old = 'fetch(apiBase().replace(/\\/+$/, "") + "/api/debt?book=" + encodeURIComponent(info.book) + "&chapter=" + encodeURIComponent(info.key || "001"), { headers: authHeaders() })'
if old not in s:
    print("anchor missing");
    i = s.find('/api/debt?book=')
    print(repr(s[max(0,i-200):i+260]))
    raise SystemExit(1)
new = ('nvlToken().then(function (tk) {' + chr(10) +
       chr(9)*5 + 'return fetch(apiBase().replace(/\\/+$/, "") + "/api/debt?book=" + encodeURIComponent(info.book) + "&chapter=" + encodeURIComponent(info.key || "001"),' + chr(10) +
       chr(9)*6 + '{ headers: tk ? { "X-Novelapp-Token": tk } : {} });' + chr(10) +
       chr(9)*4 + '})')
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("fixed -> nvlToken")