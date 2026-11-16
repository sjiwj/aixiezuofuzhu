# -*- coding: utf-8 -*-
"""NovelApp 桌面壳

双击启动 → 原生窗口（WebView2）→ 不是浏览器
内部起本地 HTTP 服务，窗口加载它。
"""
import os, sys, time, socket, threading, subprocess, atexit

if getattr(sys, 'frozen', False):
    ROOT = os.path.dirname(sys.executable)
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get('NOVELAPP_PORT', '8770'))


def port_free(p):
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', p)) != 0


def wait_ready(p, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not port_free(p):
            return True
        time.sleep(0.2)
    return False


def start_server():
    """在子进程里起服务，桌面壳退出时一并清理"""
    if not port_free(PORT):
        return None  # 已经在跑，直接用
    # 服务跑在本进程的 daemon 线程里：打包后没有独立 python.exe，也不想去起子进程
    os.environ['NOVELAPP_ROOT'] = ROOT
    sys.path.insert(0, os.path.join(ROOT, 'core'))
    import importlib
    srv_mod = importlib.import_module('server')
    th = threading.Thread(target=srv_mod.serve, args=(PORT, False), daemon=True)
    th.start()
    return th


def main():
    import webview

    srv_thread = start_server()
    if not wait_ready(PORT):
        import tkinter.messagebox as mb
        mb.showerror('NovelApp', f'服务启动失败（端口 {PORT}）\n请检查 logs/ 目录')
        return 1

    # 按屏幕大小自适应：小屏别把右侧栏挤到屏幕外
    try:
        import ctypes
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        sw, sh = 1440, 900
    w = max(1000, min(1440, sw - 40))
    h = max(680, min(920, sh - 80))

    win = webview.create_window(
        '小说创作工作台',
        f'http://127.0.0.1:{PORT}/?v={int(time.time())}',
        width=w, height=h,
        min_size=(900, 600),
        text_select=True,
    )
    webview.start(gui='edgechromium', debug=('--dev' in sys.argv))

    # 服务跑在 daemon 线程里，主进程退出时自动结束
    return 0


if __name__ == '__main__':
    sys.exit(main())
