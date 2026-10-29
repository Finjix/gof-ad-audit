#!/bin/bash
# 把 gof-ad-audit 装成 Codex 插件（旁边有 feishu 仓库时把读飞书文档用的 feishu 插件也装上）
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
# 旧版是直接拷进 ~/.codex/skills 的技能；装成插件后还留着它，Codex 里就有两份同名技能
OLD="$HOME/.codex/skills/gof-ad-audit"
if [ -d "$OLD" ]; then
  BAK="$OLD.bak-$(date +%Y%m%d%H%M%S)"
  mv "$OLD" "$BAK"
  echo "旧版技能已移到 $BAK"
fi
if ! command -v codex >/dev/null; then
  echo "没找到 codex 命令：在 Codex 里添加插件市场，选这个文件夹（$HERE），再安装 gof-ad-audit"
  exit 1
fi
codex plugin marketplace add "$HERE"
codex plugin add gof-ad-audit@gof-ad-audit
FEISHU="$(dirname "$HERE")/feishu"
if [ -f "$FEISHU/.agents/plugins/marketplace.json" ]; then
  codex plugin marketplace add "$FEISHU"
  codex plugin add feishu@feishu
else
  echo "提醒：读飞书文档还要装 feishu 插件（https://github.com/Finjix/feishu，放在这个文件夹旁边再运行一次本脚本）"
fi
command -v ffmpeg >/dev/null || echo "提醒：没找到 ffmpeg，审视频前先 brew install ffmpeg"
[ -s "$HOME/.config/winky/key" ] || echo "提醒：没配 Winky key，审视频只能抽帧看画面，配法见 README 第三节"
python3 "$HERE/plugins/gof-ad-audit/skills/gof-ad-audit/scripts/text_check.py" "$HERE/dev/tests/bad.txt" | head -1
echo "装好了，重开 Codex 生效"
