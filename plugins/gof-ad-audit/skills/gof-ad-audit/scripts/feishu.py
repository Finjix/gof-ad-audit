#!/usr/bin/env python3
"""飞书交给 feishu 插件：找到它的 feishu.mjs，用 node 原样运行。

子进程继承这个进程的环境（lark-agent 给的用户目录、Open ID、飞书应用），所以用的就是这个用户自己的飞书登录。
命令和输出都是 feishu 插件的（每个命令一行 JSON，拒绝或没登录时退出码 2）。

用法:
  python3 feishu.py doc fetch --url <飞书链接> --output 脚本.md     # 文档、知识库、表格读成 Markdown
  python3 feishu.py login check                                    # 登录还有效吗
  python3 feishu.py login start                                    # 没登录：发起授权（链接自己留着）
  python3 feishu.py authorize --qr feishu-login.png                # 生成二维码发给用户扫
  python3 feishu.py authorize                                      # 用户扫完码后
  python3 feishu.py login poll                                     # 收登录

找 feishu.mjs 的顺序和 feishu 插件 docs/for-plugins.md 一致：环境变量 FEISHU_PLUGIN（feishu.mjs 的绝对路径），
否则从本文件往上逐级找并排的 feishu 插件文件夹、Codex 插件缓存（同一个或别的 marketplace）、开发时并排的 feishu-plugin 仓库。
lark-agent 的 plugins/ 里文件夹叫 feishu-plugin，并排找不到；它启动时装进 Codex 插件缓存，从缓存找到。
依赖: Python 3.8+ 标准库 + Node.js 24+。
"""
import json
import os
import re
import shutil
import subprocess
import sys

ENTRY = os.path.join("server", "dist", "feishu.mjs")
MISSING = ("没有找到 feishu 插件（读飞书文档要用它）：lark-agent 里把 feishu 插件文件夹放进 plugins/ 并重启；"
           "Codex 桌面版里安装 feishu@feishu（见 gof-ad-audit 的 README）")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _version_key(name):
    return [(0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.+-]", name)]


def _dirs(path):
    try:
        return [e.name for e in os.scandir(path) if e.is_dir()]
    except OSError:
        return []


def _newest(plugin_dir):
    for version in sorted(_dirs(plugin_dir), key=_version_key, reverse=True):
        entry = os.path.join(plugin_dir, version, ENTRY)
        if os.path.isfile(entry):
            return entry
    return None


def locate(env=os.environ, start=os.path.dirname(os.path.abspath(__file__))):
    named = env.get("FEISHU_PLUGIN", "").strip()
    if named:
        if os.path.isabs(named) and os.path.isfile(named):
            return named
        raise SystemExit(json.dumps({"status": "blocked", "reason": "FEISHU_PLUGIN 不是 feishu.mjs 的绝对路径"}, ensure_ascii=False))
    here = start
    for _ in range(9):
        sibling = os.path.join(here, "feishu", ENTRY)                 # 并排的 feishu 插件文件夹
        dev = os.path.join(here, "feishu-plugin", "plugins", "feishu", ENTRY)  # 并排的 feishu-plugin 仓库
        found = ((sibling if os.path.isfile(sibling) else None)
                 or _newest(os.path.join(here, "feishu"))                 # Codex 插件缓存，同一个 marketplace
                 or next(filter(None, (_newest(os.path.join(here, m, "feishu")) for m in _dirs(here))), None)  # 别的 marketplace
                 or (dev if os.path.isfile(dev) else None))
        if found:
            return found
        up = os.path.dirname(here)
        if up == here:
            break
        here = up
    return None


def main(argv):
    entry = locate()
    if not entry:
        print(json.dumps({"status": "blocked", "reason": MISSING}, ensure_ascii=False))
        return 2
    node = shutil.which("node")
    if not node:
        print(json.dumps({"status": "blocked", "reason": "没有找到 Node.js（feishu 插件需要 Node.js 24+）"}, ensure_ascii=False))
        return 2
    return subprocess.run([node, entry, *argv]).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
