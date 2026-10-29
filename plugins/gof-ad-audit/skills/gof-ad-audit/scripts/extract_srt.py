#!/usr/bin/env python3
"""从 analyze_video.py 的 report.md 里抽出 ```srt 代码块存成 srt，给 text_check.py 用。

用法: python3 extract_srt.py report.md subs.srt
"""
import re
import sys

if len(sys.argv) != 3:
    sys.exit("用法: extract_srt.py report.md subs.srt")
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"```srt\s*\n(.*?)```", text, re.S)
if not m:
    sys.exit("report.md 里没有 ```srt 代码块，Gemini 可能没按格式输出，重跑一次或手抄转写")
open(sys.argv[2], "w", encoding="utf-8").write(m.group(1))
print(f"写出 {sys.argv[2]}，{m.group(1).count('-->')} 条")
