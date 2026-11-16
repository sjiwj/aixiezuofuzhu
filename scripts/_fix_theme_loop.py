# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()

OLD = """\t\ttry {
\t\t\tfunction syncTheme() {
\t\t\t\ttry { document.documentElement.setAttribute("data-nvl-theme", "light"); } catch (e) { /* ignore */ }
\t\t\t\t/* 固定浅色：深色主题有 bug，先锁死 light。设置里的「外观」也已隐藏。 */
\t\t\tconst mine = "light";
\t\t\tconst src = "light";
\t\t\t\ttry {
\t\t\t\t\tif (document.documentElement.getAttribute("data-ds-theme-source") !== src) {
\t\t\t\t\t\tdocument.documentElement.setAttribute("data-ds-theme-source", src);
\t\t\t\t\t}
\t\t\t\t} catch (e) { /* ignore */ }
\t\t\t}
\t\t\tsyncTheme();
\t\t\t/* 用户改了我们的主题（设置面板里的浅色/深色）→ 立刻同步给宿主 */
\t\t\ttry {
\t\t\t\tnew MutationObserver(syncTheme).observe(document.documentElement, {
\t\t\t\t\tattributes: true, attributeFilter: ["data-nvl-theme"]
\t\t\t\t});
\t\t\t} catch (e) { /* ignore */ }
\t\t} catch (e) { /* ignore */ }"""

NEW = """\t\t/* 固定浅色：深色主题有 bug，锁死 light。设置里的「外观」也已隐藏。
\t\t   注意：不要用 MutationObserver 监听 data-nvl-theme —— 这里会改它，
\t\t   监听同一个属性会形成无限循环，把主线程卡死（App 卡在加载界面）。 */
\t\ttry {
\t\t\tdocument.documentElement.setAttribute("data-nvl-theme", "light");
\t\t\tdocument.documentElement.setAttribute("data-ds-theme-source", "light");
\t\t} catch (e) { /* ignore */ }"""

if OLD not in s:
    print("anchor missing")
    sys.exit(1)
s = s.replace(OLD, NEW, 1)

# 修 2491 行重复注释
s = s.replace('/* \u8bbe\u7f6e \u2192 \u901a\u7528 \u2192 \u5173\u4e8e\u4e0e\u8bb8\u53ef\uff1aMIT \u58f0\u660e + \u7248\u672c + AI \u6807\u8bc6\u8bf4\u660e */\t\t/* \u8bbe\u7f6e \u2192 \u901a\u7528 \u2192 \u5173\u4e8e\u4e0e\u8bb8\u53ef\uff1aMIT \u58f0\u660e + \u7248\u672c + AI \u6807\u8bc6\u8bf4\u660e */',
              '/* \u8bbe\u7f6e \u2192 \u901a\u7528 \u2192 \u5173\u4e8e\u4e0e\u8bb8\u53ef\uff1aMIT \u58f0\u660e + \u7248\u672c + AI \u6807\u8bc6\u8bf4\u660e */', 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("theme loop removed")