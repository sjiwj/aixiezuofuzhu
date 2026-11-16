# -*- coding: utf-8 -*-
"""小说工作台冒烟脚本（本地服务 18771）。

用法（工作目录不限，脚本自己定位项目根）：
    python scripts/smoke_novel.py              # 中文三色门 + 失败明细
    python scripts/smoke_novel.py --json       # 机读结果（同样只含真实观测）
    python scripts/smoke_novel.py --no-spawn   # 端口没起时不自启，直接报红
    python scripts/smoke_novel.py --keep       # 保留临时项目（排障用，门会降为黄）

覆盖：
    ① core/deai.py / core/workflow.py / core/ling.py 的 --selftest
    ② HTTP：GET /、/app.html、/legacy、/api/novel/projects、/api/novel/wizard/config
    ③ 写入链路：建临时项目 → 加章 → 保存 → 读回 → 删除（只碰自己建的临时项目）
    ④ data/novel/backups 存在且快照数不超过 20

退出码：0 = GREEN / YELLOW；1 = RED。

副作用边界：
    - 不改任何源码或页面；
    - 唯一写入是临时项目（默认结束时删除）以及写库自动产生的备份快照；
    - 已 Popen 的服务进程只在本次脚本自启时才会被关闭。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
DB_PATH = os.path.join(ROOT, "data", "novel", "db.json")
BAK_DIR = os.path.join(ROOT, "data", "novel", "backups")
DEFAULT_PORT = 18771
BAK_LIMIT = 20
SELFTEST_MODULES = ("deai", "workflow", "ling")

# 输出统一过一遍遮罩：界面与返回值里不出现计价类字样
MASK_WORDS = ("灵石", "积分", "价格", "预估", "token", "Token", "TOKEN", "tokens")

BASE = "http://127.0.0.1:%d" % DEFAULT_PORT

DELETE_SNIPPET = """
import sys
sys.path.insert(0, {core})
import novel_api as N
db = N.load_db()
hit = (db.get("projects") or {{}}).pop({pid}, None)
if hit is not None:
    N.save_db(db, "smoke")
print("DELETED" if hit is not None else "MISSING")
"""


class Result(object):
    """一条检查结果。"""

    __slots__ = ("group", "name", "ok", "detail")

    def __init__(self, group, name, ok, detail=""):
        self.group = group
        self.name = name
        self.ok = bool(ok)
        self.detail = detail or ""


def mask(text):
    s = "" if text is None else str(text)
    for w in MASK_WORDS:
        if w in s:
            s = s.replace(w, "*" * len(w))
    return s


def say(line=""):
    line = mask(line)
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("utf-8", "replace").decode("ascii", "backslashreplace"))


def decode(raw):
    if not raw:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def child_env():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def http(method, path, payload=None, timeout=20.0):
    """返回 (状态码, Content-Type, 原始字节)；HTTP 错误码也照常返回，不抛。"""
    url = BASE + path
    data = None
    headers = {"Accept": "application/json, text/html;q=0.9"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:
            pass
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, ctype, body


def as_json(raw):
    try:
        return json.loads(raw.decode("utf-8")), ""
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def port_open(port, timeout=0.4):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_ready(port, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if port_open(port, 0.3):
            try:
                status, _, _ = http("GET", "/api/novel/projects", timeout=3)
                if status == 200:
                    return True
            except Exception:
                pass
        time.sleep(0.3)
    return False


def spawn_server(port, log_path):
    env = child_env()
    env["NOVEL_PORT"] = str(port)
    log = open(log_path, "wb")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(CORE, "novel_http.py")],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return proc, log


def stop_server(proc, log_handle):
    try:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=6)
    finally:
        try:
            if log_handle is not None:
                log_handle.close()
        except Exception:
            pass


def read_tail(path, limit=1500):
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return decode(raw)[-limit:]
    except OSError:
        return ""


# ---------------- ① 模块自检 ----------------
def check_selftest(module, results):
    path = os.path.join(CORE, module + ".py")
    if not os.path.isfile(path):
        results.append(Result("① 模块自检", module + " --selftest", False, "文件不存在：" + path))
        return
    try:
        cp = subprocess.run(
            [sys.executable, path, "--selftest"],
            cwd=ROOT,
            env=child_env(),
            capture_output=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        results.append(Result("① 模块自检", module + " --selftest", False, "180 秒超时"))
        return
    except OSError as exc:
        results.append(Result("① 模块自检", module + " --selftest", False, "启动失败：" + str(exc)))
        return

    out = decode(cp.stdout) + decode(cp.stderr)
    m = re.search(r"(\d+)\s+passed,\s*(\d+)\s+failed", out)
    if m:
        passed, failed = int(m.group(1)), int(m.group(2))
        detail = "exit=%d；%d 通过 / %d 失败" % (cp.returncode, passed, failed)
        ok = cp.returncode == 0 and failed == 0
    else:
        detail = "exit=%d；没找到汇总行（输出可能被改动）" % cp.returncode
        ok = False
    if not ok:
        bad = [ln.strip() for ln in out.splitlines() if "FAIL" in ln][:5]
        if bad:
            detail += "；" + "；".join(bad)
        elif not m:
            detail += "；尾部：" + " / ".join(out.strip().splitlines()[-3:])
    results.append(Result("① 模块自检", module + " --selftest", ok, detail))


# ---------------- ② HTTP ----------------
def expect_html(path, results, label=None):
    try:
        status, ctype, raw = http("GET", path)
    except Exception as exc:
        results.append(Result("② HTTP 冒烟", label or path, False, "请求异常：%s" % exc))
        return
    low = raw[:4096].lower()
    ok = status == 200 and "text/html" in (ctype or "").lower() and len(raw) > 500 and b"<html" in low
    detail = "%d 字节 · %s" % (len(raw), ctype or "无 Content-Type")
    if not ok:
        detail = "status=%d · %s · 前 80 字节：%r" % (status, ctype or "无 Content-Type", raw[:80])
    results.append(Result("② HTTP 冒烟", label or path, ok, detail))


def expect_json(path, required, results, label=None):
    try:
        status, ctype, raw = http("GET", path)
    except Exception as exc:
        results.append(Result("② HTTP 冒烟", label or path, False, "请求异常：%s" % exc))
        return None
    obj, err = as_json(raw)
    if status != 200 or obj is None:
        results.append(Result("② HTTP 冒烟", label or path, False,
                              "status=%d；解析失败：%s；前 120 字节：%r" % (status, err, raw[:120])))
        return None
    if isinstance(obj, dict):
        missing = [k for k in required if k not in obj]
        ok = not missing
        detail = "200 · JSON · 键 %d 个" % len(obj)
        if missing:
            detail = "缺少字段：" + ", ".join(missing)
        results.append(Result("② HTTP 冒烟", label or path, ok, detail))
    else:
        results.append(Result("② HTTP 冒烟", label or path, False,
                              "顶层不是对象，而是 %s" % type(obj).__name__))
    return obj


# ---------------- ③ 写入链路 ----------------
def count_words(text):
    return len(re.sub(r"\s+", "", text or ""))


def delete_temp_project(pid):
    snippet = DELETE_SNIPPET.format(core=repr(CORE), pid=repr(pid))
    try:
        cp = subprocess.run(
            [sys.executable, "-c", snippet],
            cwd=ROOT,
            env=child_env(),
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "删除子进程 120 秒超时"
    except OSError as exc:
        return False, "删除子进程启动失败：" + str(exc)
    out = decode(cp.stdout).strip()
    err = decode(cp.stderr).strip()
    if cp.returncode != 0:
        return False, "exit=%d；%s" % (cp.returncode, err[-300:] or out[-300:])
    return out == "DELETED", out or err[-300:] or "无输出"


def check_write_path(results, keep=False):
    stamp = datetime.now().strftime("%m%d-%H%M%S")
    title = "冒烟临时项目-%s-%s" % (stamp, uuid.uuid4().hex[:6])
    pid = ""
    deleted = False

    try:
        payload = {"title": title, "channel": "男频", "genre": "都市", "word_goal": 20000}
        try:
            status, _, raw = http("POST", "/api/novel/projects", payload)
        except Exception as exc:
            results.append(Result("③ 写入链路", "建临时项目", False, "请求异常：%s" % exc))
            return
        obj, err = as_json(raw)
        if status != 200 or not isinstance(obj, dict) or not re.match(r"^[0-9a-f]{12}$", str(obj.get("id") or "")):
            results.append(Result("③ 写入链路", "建临时项目", False,
                                  "status=%d；返回异常：%s；前 120 字节：%r" % (status, err or "结构不符", raw[:120])))
            return
        pid = obj["id"]
        results.append(Result("③ 写入链路", "建临时项目", True, "pid=%s；标题=%s" % (pid, title)))

        content_a = "冒烟正文，第一段。\n\n第二段：这里只验证写入与读回，不承载业务数据。"
        try:
            status, _, raw = http("POST", "/api/novel/projects/%s/chapters" % pid,
                                  {"title": "第1章 冒烟", "content": content_a})
        except Exception as exc:
            results.append(Result("③ 写入链路", "加章", False, "请求异常：%s" % exc))
            return
        obj, err = as_json(raw)
        cid = str((obj or {}).get("id") or "") if isinstance(obj, dict) else ""
        if status != 200 or not cid:
            results.append(Result("③ 写入链路", "加章", False,
                                  "status=%d；%s；前 120 字节：%r" % (status, err or "没有章节 id", raw[:120])))
            return
        results.append(Result("③ 写入链路", "加章", True, "cid=%s；%s 字" % (cid, (obj or {}).get("words"))))

        content_b = "冒烟正文，修改后。\n\n第二段：保存后立即读回比对。"
        try:
            status, _, raw = http("POST", "/api/novel/chapters/%s" % cid, {"content": content_b})
        except Exception as exc:
            results.append(Result("③ 写入链路", "保存", False, "请求异常：%s" % exc))
            return
        obj, err = as_json(raw)
        saved_ok = (status == 200 and isinstance(obj, dict)
                    and obj.get("content") == content_b
                    and obj.get("words") == count_words(content_b))
        detail = "status=%d；%s 字" % (status, (obj or {}).get("words") if isinstance(obj, dict) else "?")
        if not saved_ok:
            detail += "；返回与提交正文不一致或字数不符"
        results.append(Result("③ 写入链路", "保存", saved_ok, detail))
        if not saved_ok:
            return

        try:
            status, _, raw = http("GET", "/api/novel/projects/%s" % pid)
        except Exception as exc:
            results.append(Result("③ 写入链路", "读回", False, "请求异常：%s" % exc))
            return
        obj, err = as_json(raw)
        chapters = (obj or {}).get("chapters") if isinstance(obj, dict) else None
        hit = None
        if isinstance(chapters, list):
            hit = next((c for c in chapters if c.get("id") == cid), None)
        read_ok = bool(hit) and hit.get("content") == content_b and hit.get("words") == count_words(content_b)
        if read_ok:
            detail = "项目 %s 下读回 1 章，正文与字数一致（%d 字）" % (pid, hit.get("words"))
        else:
            detail = "status=%d；%s；未找到刚保存的正文或不一致" % (status, err or "结构不符")
        results.append(Result("③ 写入链路", "读回", read_ok, detail))
        if not read_ok:
            return

        if keep:
            results.append(Result("③ 写入链路", "删除", True, "已按 --keep 跳过；临时项目 pid=%s 保留" % pid))
            return

        ok, detail = delete_temp_project(pid)
        deleted = ok
        results.append(Result("③ 写入链路", "删除", ok, ("pid=%s；%s" % (pid, detail)) if ok else detail))
        if not ok:
            return

        try:
            status, _, raw = http("GET", "/api/novel/projects/%s" % pid)
        except Exception as exc:
            results.append(Result("③ 写入链路", "删除后确认", False, "请求异常：%s" % exc))
            return
        obj, err = as_json(raw)
        gone = status == 404
        detail = "GET 返回 %d%s" % (status, "（已不存在）" if gone else "；仍可读到项目")
        results.append(Result("③ 写入链路", "删除后确认", gone, detail))
    finally:
        if pid and not deleted and not keep:
            # 检查中途失败也要清场，保证可重复运行
            ok, detail = delete_temp_project(pid)
            if not ok:
                results.append(Result("③ 写入链路", "失败清场", False,
                                      "临时项目 %s 未删除：%s（需手工处理）" % (pid, detail)))


# ---------------- ④ 备份 ----------------
def check_backups(results, warnings):
    if not os.path.isdir(BAK_DIR):
        results.append(Result("④ 备份快照", "目录存在", False, "缺少目录：" + BAK_DIR))
        return
    try:
        names = sorted(n for n in os.listdir(BAK_DIR) if n.startswith("db-") and n.endswith(".json"))
    except OSError as exc:
        results.append(Result("④ 备份快照", "目录可读", False, "读取失败：%s" % exc))
        return
    n = len(names)
    results.append(Result("④ 备份快照", "目录存在", True, BAK_DIR))
    ok = n <= BAK_LIMIT
    detail = "%d 份快照（上限 %d）" % (n, BAK_LIMIT)
    if names:
        detail += "；最新：" + names[-1]
    results.append(Result("④ 备份快照", "份数不超上限", ok, detail))
    if n == 0:
        warnings.append("备份目录为空：写入链路没有留下快照，回滚能力待确认")


def detect_generate_path(notes, gaps):
    """静态看一眼 generate() 的主路径，只做提示，不计入三色门。"""
    path = os.path.join(CORE, "novel_api.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as exc:
        notes.append("没能读取 novel_api.py：%s" % exc)
        return
    start = src.find("def generate(")
    if start < 0:
        notes.append("没找到 generate()，跳过静态提示")
        return
    end = src.find("\ndef ", start + 1)
    body = src[start:end if end > 0 else len(src)]
    if "_llm_text(" in body:
        notes.append("generate() 主路径已调用 _llm_text（真模型），本地模板只作兜底")
    elif "mock_prose(" in body:
        gaps.append("generate() 仍是本地模板占位文本，未接真模型")


# ---------------- 主流程 ----------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="小说工作台冒烟脚本（三色门）")
    ap.add_argument("--port", type=int, default=int(os.environ.get("NOVEL_PORT") or DEFAULT_PORT))
    ap.add_argument("--no-spawn", action="store_true", help="端口没监听时不自动拉起服务")
    ap.add_argument("--keep", action="store_true", help="保留临时项目（排障用）")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    args = ap.parse_args(argv)

    global BASE
    BASE = "http://127.0.0.1:%d" % args.port

    started = time.time()
    results = []
    warnings = []
    notes = []
    gaps = []

    proc = None
    log_handle = None
    log_path = os.path.join(tempfile.gettempdir(), "novel_smoke_%d.log" % os.getpid())

    try:
        # 0) 服务可达
        if port_open(args.port):
            notes.append("复用已在监听的服务：%s" % BASE)
            results.append(Result("⓪ 服务", "端口可连", True, BASE))
        elif args.no_spawn:
            results.append(Result("⓪ 服务", "端口可连", False,
                                  "%s 无监听；用 python core/novel_http.py 启动后重跑" % BASE))
        else:
            proc, log_handle = spawn_server(args.port, log_path)
            if wait_ready(args.port, 25):
                notes.append("本次由脚本冷启动服务（端口 %d），结束时关闭" % args.port)
                results.append(Result("⓪ 服务", "冷启动", True, BASE))
            else:
                tail = read_tail(log_path)
                results.append(Result("⓪ 服务", "冷启动", False,
                                      "25 秒内没就绪；日志尾部：" + (tail or "（空）")))

        service_up = all(r.ok for r in results if r.group == "⓪ 服务")
        if not service_up:
            # 服务都起不来，后面的检查没有意义，直接出红灯
            return finish(results, warnings, notes, gaps, started, args.json)

        # ① 模块自检
        for mod in SELFTEST_MODULES:
            check_selftest(mod, results)

        # ② HTTP
        expect_html("/", results, label="GET /")
        expect_html("/app.html", results, label="GET /app.html")
        expect_html("/legacy", results, label="GET /legacy")
        expect_json("/api/novel/projects", ("projects",), results, label="GET /api/novel/projects")
        expect_json("/api/novel/wizard/config", ("channels", "deck", "nine", "recipes"),
                    results, label="GET /api/novel/wizard/config")

        # ③ 写入链路
        check_write_path(results, keep=args.keep)
        if args.keep:
            warnings.append("--keep 生效：临时项目保留，删除步骤未验证")

        # ④ 备份
        check_backups(results, warnings)

        # 静态提示（不计入门）
        detect_generate_path(notes, gaps)

        return finish(results, warnings, notes, gaps, started, args.json)
    finally:
        stop_server(proc, log_handle)
        try:
            if proc is not None and os.path.isfile(log_path):
                os.remove(log_path)
        except OSError:
            pass


def finish(results, warnings, notes, gaps, started, as_json_mode):
    failures = [r for r in results if not r.ok]
    if failures:
        gate = "RED"
    elif warnings:
        gate = "YELLOW"
    else:
        gate = "GREEN"
    elapsed = time.time() - started

    if as_json_mode:
        payload = {
            "gate": gate,
            "passed": sum(1 for r in results if r.ok),
            "failed": len(failures),
            "elapsed_seconds": round(elapsed, 2),
            "checks": [{"group": r.group, "name": r.name, "ok": r.ok, "detail": mask(r.detail)}
                       for r in results],
            "failures": [{"group": r.group, "name": r.name, "detail": mask(r.detail)} for r in failures],
            "warnings": [mask(w) for w in warnings],
            "notes": [mask(n) for n in notes],
            "known_gaps": [mask(g) for g in gaps],
        }
        say(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if gate == "RED" else 0

    say("小说工作台冒烟 · %s · %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), BASE))
    if notes:
        for n in notes:
            say("提示：" + n)
    say("")

    current = None
    for r in results:
        if r.group != current:
            current = r.group
            say(current)
        say("  %s  %-22s %s" % ("PASS" if r.ok else "FAIL", r.name, r.detail))
    say("")

    if warnings:
        say("需要知道")
        for w in warnings:
            say("  - " + w)
        say("")
    if gaps:
        say("已知缺口（不计入三色门）")
        for g in gaps:
            say("  - " + g)
        say("")
    if failures:
        say("失败明细")
        for r in failures:
            say("  - [%s] %s：%s" % (r.group, r.name, r.detail))
        say("")

    total = len(results)
    passed = sum(1 for r in results if r.ok)
    if gate == "GREEN":
        say("【门】GREEN · %d/%d 项通过 · 用时 %.1fs" % (passed, total, elapsed))
    elif gate == "YELLOW":
        say("【门】YELLOW · %d/%d 项通过，另有 %d 条需注意 · 用时 %.1fs"
            % (passed, total, len(warnings), elapsed))
    else:
        say("【门】RED · %d/%d 项通过，%d 项失败 · 用时 %.1fs"
            % (passed, total, len(failures), elapsed))
    return 1 if gate == "RED" else 0


if __name__ == "__main__":
    sys.exit(main())
