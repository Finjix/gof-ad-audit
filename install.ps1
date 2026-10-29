# 把 gof-ad-audit 装成 Codex 插件（旁边有 feishu 仓库时把读飞书文档用的 feishu 插件也装上）
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# 旧版是直接拷进 ~/.codex/skills 的技能；装成插件后还留着它，Codex 里就有两份同名技能
$old = Join-Path $HOME ".codex\skills\gof-ad-audit"
if (Test-Path $old) {
  $bak = "$old.bak-" + (Get-Date -Format "yyyyMMddHHmmss")
  Move-Item $old $bak
  Write-Host "旧版技能已移到 $bak"
}
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
  Write-Host "没找到 codex 命令：在 Codex 里添加插件市场，选这个文件夹（$here），再安装 gof-ad-audit"
  exit 1
}
codex plugin marketplace add $here
codex plugin add gof-ad-audit@gof-ad-audit
$feishu = Join-Path (Split-Path -Parent $here) "feishu"
if (Test-Path (Join-Path $feishu ".agents\plugins\marketplace.json")) {
  codex plugin marketplace add $feishu
  codex plugin add feishu@feishu
} else { Write-Host "提醒：读飞书文档还要装 feishu 插件（https://github.com/Finjix/feishu，放在这个文件夹旁边再运行一次本脚本）" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host "提醒：没找到 ffmpeg，审视频前先装，见 README 第二节" }
if (-not (Test-Path (Join-Path $HOME ".config\winky\key"))) { Write-Host "提醒：没配 Winky key，审视频只能抽帧看画面，配法见 README 第三节" }
$env:PYTHONIOENCODING = "utf-8"
python (Join-Path $here "plugins\gof-ad-audit\skills\gof-ad-audit\scripts\text_check.py") (Join-Path $here "dev\tests\bad.txt") | Select-Object -First 1
Write-Host "装好了，重开 Codex 生效"
