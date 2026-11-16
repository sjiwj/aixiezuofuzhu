# -*- coding: utf-8 -*-
"""交付前自检 —— 只说机器能判定的那两件事

用法:
  python scripts/selfcheck.py              # 最近 20 个代码文件
  python scripts/selfcheck.py --file X     # 单个文件
  python scripts/selfcheck.py --all        # 全部（慢）

查两样（都是可机械判定的）:
  1. 语法错误（py / json）
  2. 代码里的 TODO / FIXME / XXX（不含中文占位符，那些是正常的模板）

不查「不确定词」——那是人判断的事，脚本查不准（会把提示词里的正常用法也扫出来）。
"""
import os
import sys
import json
import ast

ROOT = r"D:\NovelApp"
SELF = os.path.basename(__file__)

# 代码里的未完成标记（只认英文，中文「待填」是正常模板）
TODO_MARKS = ["TODO", "FIXME", "XXX:"]


def check_syntax(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".py":
            with open(path, "r", encoding="utf-8") as f:
                ast.parse(f.read())
            return None
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
            return None
    except SyntaxError as e:
        return "%s:%s %s" % (os.path.basename(path), e.lineno, e.msg)
    except json.JSONDecodeError as e:
        return "%s:%s %s" % (os.path.basename(path), e.lineno, e.msg)
    except Exception as e:
        return "%s %s" % (os.path.basename(path), str(e)[:60])
    return None


def check_todo(path):
    out = []
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".py", ".js"):
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                s = line.strip()
                for m in TODO_MARKS:
                    if m in s:
                        out.append("%s:%d %s" % (os.path.basename(path), i, s[:70]))
                        break
    except Exception:
        pass
    return out


def recent_files(root, n=20):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (
            "node_modules", "__pycache__", ".git", "_asar_edit", "_learn",
            "dsh-src", "build", ".desktop-build", "runtime", "dist", "projects")]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in (".py", ".js", ".json", ".yaml", ".yml"):
                continue
            if fn == SELF:
                continue
            p = os.path.join(dirpath, fn)
            try:
                out.append((os.path.getmtime(p), p))
            except Exception:
                pass
    out.sort(reverse=True)
    return [p for _, p in out[:n]]


def all_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (
            "node_modules", "__pycache__", ".git", "_asar_edit", "_learn",
            "dsh-src", "build", ".desktop-build", "runtime", "dist", "projects")]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in (".py", ".js", ".json", ".yaml", ".yml"):
                continue
            if fn == SELF:
                continue
            out.append(os.path.join(dirpath, fn))
    return out


def main():
    if "--file" in sys.argv:
        i = sys.argv.index("--file")
        files = [sys.argv[i + 1]]
    elif "--all" in sys.argv:
        files = all_files(ROOT)
    else:
        files = recent_files(ROOT)

    print("=== 自检（%d 个代码文件）===" % len(files))

    syn_issues = []
    todo_issues = []
    for f in files:
        s = check_syntax(f)
        if s:
            syn_issues.append(s)
        todo_issues.extend(check_todo(f))

    print()
    if syn_issues:
        print("语法错误 %d 个:" % len(syn_issues))
        for x in syn_issues:
            print("  ✗ " + x)
    else:
        print("✓ 语法全过")

    if todo_issues:
        print()
        print("未完成标记 %d 处:" % len(todo_issues))
        for x in todo_issues[:15]:
            print("  · " + x)
        if len(todo_issues) > 15:
            print("  ... 还有 %d 处" % (len(todo_issues) - 15))

    print()
    if syn_issues:
        sys.exit(1)
    print("可以交付（语法过了；有 TODO 的话在交付里说明）")


if __name__ == "__main__":
    main()