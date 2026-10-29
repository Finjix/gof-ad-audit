#!/usr/bin/env python3
"""给一次审核建一个工作文件夹（Gemini 报告、抽出的字幕、抽帧、拉下来的脚本都放这里），打印它的路径。

lark-agent 里（有 LARK_AGENT_USER_DIR）放在这个用户自己的 <用户目录>/gof-ad-audit/work/ 下：
lark-agent 会把 Codex 工作目录里新出现的文件都发给用户，中间文件不能放在那里。
这里 7 天没动过的文件夹会在下次运行时删掉（素材是公司内部的，不留在电脑上）。
没有 LARK_AGENT_USER_DIR（Codex 桌面版）时就是当前目录下的 审核_<片名>，不清理。

用法: python3 workdir.py <片名>    → {"dir": "<绝对路径>"}
依赖: Python 3.8+ 标准库。
"""
import json
import os
import re
import shutil
import sys
import time

KEEP_DAYS = 7

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def safe(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:60] or "素材"


def newest(path):
    """一个文件夹里最近一次创建、修改的时间；读不了的当成刚动过，不删。"""
    latest = os.stat(path).st_mtime
    try:
        for root, dirs, files in os.walk(path):
            for n in dirs + files:
                st = os.lstat(os.path.join(root, n))
                latest = max(latest, st.st_mtime, st.st_ctime)
    except OSError:
        return time.time()
    return latest


def prune(work, now):
    for name in os.listdir(work):
        target = os.path.join(work, name)
        if os.path.islink(target) or not os.path.isdir(target):
            continue
        try:
            if now - newest(target) > KEEP_DAYS * 86400:
                shutil.rmtree(target)
        except OSError:
            pass  # 正被占用：下次再删


def main(argv):
    if len(argv) != 1 or not argv[0].strip():
        print("用法: workdir.py <片名>", file=sys.stderr)
        return 2
    name = safe(argv[0])
    user = os.environ.get("LARK_AGENT_USER_DIR", "").strip()
    if user:
        if not os.path.isabs(user):
            print(json.dumps({"status": "blocked", "reason": "LARK_AGENT_USER_DIR 必须是绝对路径"}, ensure_ascii=False))
            return 2
        work = os.path.join(user, "gof-ad-audit", "work")
        os.makedirs(work, exist_ok=True)
        prune(work, time.time())
        target = os.path.join(work, f"{time.strftime('%Y%m%d-%H%M%S')}_{name}")
    else:
        target = os.path.abspath(f"审核_{name}")
    os.makedirs(target, exist_ok=True)
    print(json.dumps({"dir": target}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
