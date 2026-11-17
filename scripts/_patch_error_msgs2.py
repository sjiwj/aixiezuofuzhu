#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误普通话化补丁（第二批，幂等）：处理正则覆盖不到的 9 处出口。

这些不是 `'%s: %s' % (type(e).__name__, e)` 的单引号统一形状，逐条锚定：
  - 双引号写法 {"error": "%s: %s"}
  - f-string / 单引号里带别的前缀与参数
  - setup 探测把异常类名当 hint

用法：python scripts/_patch_error_msgs2.py [--dry-run]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, 'core', 'server.py')

PAIRS = [
    # 1) probe_ollama：error 直接给界面
    ("        info['error'] = '%s' % (getattr(e, 'reason', None) or type(e).__name__)\n",
     "        info['error'] = report(e, where='probe_ollama')\n"),

    # 2) setup_test：hint 是异常类名，detail 是英文原文 -> 都不外露
    ("                'hint': type(e).__name__, 'detail': str(e)[:300]}\n",
     "                'hint': report(e, where='setup_test'), 'detail': ''}\n"),

    # 3) 写章失败（40 字摘要路径）
    ("            reason = (str(e)[:40] if auth else '写章失败：%s' % (str(e)[:40] or type(e).__name__))\n",
     "            reason = (str(e)[:40] if auth else '写章失败：' + human(e))\n"),

    # 4) 写章失败（30 字摘要路径，出现两次）
    ("            reason = '写章失败：%s' % (str(e)[:30] or type(e).__name__)\n",
     "            reason = '写章失败：' + human(e)\n"),

    # 5) /api/debt
    ('            lib = _script_lib("debt_view")\n            rep = lib.build_debt(book, chapter or None)\n'
     '        except Exception as e:\n'
     '            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)\n',
     '            lib = _script_lib("debt_view")\n            rep = lib.build_debt(book, chapter or None)\n'
     '        except Exception as e:\n'
     '            self._json({"ok": False, "error": report(e)}, 500)\n'),

    # 6) /api/completion
    ('            self._json({"ok": True, "report": rep, "text": _c.report(rep)}, 200)\n'
     '        except Exception as e:\n'
     '            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)\n',
     '            self._json({"ok": True, "report": rep, "text": _c.report(rep)}, 200)\n'
     '        except Exception as e:\n'
     '            self._json({"ok": False, "error": report(e)}, 500)\n'),

    # 7) 附带给模型的附带文件提示
    ("            return '', '[附带文件读不了] %s（%s: %s）' % (full, type(e).__name__, e), []\n",
     "            return '', '[附带文件读不了] %s（%s）' % (full, report(e)), []\n"),

    # 8) 子任务工具异常
    ("                out = '[工具异常] %s: %s: %s' % (name, type(e).__name__, e)\n",
     "                out = '[工具异常] %s：%s' % (name, report(e))\n"),

    # 9) _run_script 返回值（会进界面的错误串）
    ("        return None, '%s: %s' % (type(ex).__name__, str(ex)[:120])\n",
     "        return None, report(ex, where='run_script')\n"),
]


def main():
    dry = '--dry-run' in sys.argv
    src = open(SERVER, encoding='utf-8', newline='').read()
    out = src
    ok = skip = fail = 0
    for old, new in PAIRS:
        probe = old if old != new else new
        if new in out and old not in out:
            print('SKIP  已应用  %s' % new.strip()[:90])
            skip += 1
            continue
        hits = out.count(old)
        if hits == 0:
            print('FAIL  锚点未命中  %s' % old.strip().replace('\n', ' ')[:90])
            fail += 1
            continue
        out = out.replace(old, new)
        print('OK    x%d  %s' % (hits, new.strip()[:90]))
        ok += 1

    print('\n结果: applied=%d skipped=%d failed=%d%s' % (ok, skip, fail, '（dry-run）' if dry else ''))
    if dry or out == src:
        if not dry:
            print('内容无变化（幂等）')
        return 1 if fail else 0
    tmp = SERVER + '.tmp-patch'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(out)
    os.replace(tmp, SERVER)
    print('已写入 core/server.py')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
