#!/bin/bash
# 把 gof-ad-audit 装进 ~/.codex/skills/
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/.codex/skills/gof-ad-audit"
mkdir -p "$HOME/.codex/skills"
if [ -d "$DST" ]; then
  BAK="$DST.bak-$(date +%Y%m%d%H%M%S)"
  mv "$DST" "$BAK"
  echo "旧版已备份到 $BAK"
fi
cp -R "$HERE/gof-ad-audit" "$DST"
command -v ffmpeg >/dev/null || echo "提醒：没找到 ffmpeg，审视频前先 brew install ffmpeg"
[ -s "$HOME/.config/winky/key" ] || echo "提醒：没配 Winky key，审视频只能抽帧看画面，配法见README 第三节"
python3 "$DST/scripts/text_check.py" "$DST/tests/bad.txt" | head -1
echo "装好了：$DST，重开 Codex 生效"
