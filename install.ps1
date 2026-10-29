# 把 gof-ad-audit 装进 %USERPROFILE%\.codex\skills\
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$skills = Join-Path $HOME ".codex\skills"
$dst = Join-Path $skills "gof-ad-audit"
New-Item -ItemType Directory -Force $skills | Out-Null
if (Test-Path $dst) {
  $bak = "$dst.bak-" + (Get-Date -Format "yyyyMMddHHmmss")
  Move-Item $dst $bak
  Write-Host "旧版已备份到 $bak"
}
Copy-Item -Recurse (Join-Path $here "gof-ad-audit") $dst
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host "提醒：没找到 ffmpeg，审视频前先 winget install ffmpeg" }
if (-not (Test-Path (Join-Path $HOME ".config\winky\key"))) { Write-Host "提醒：没配 Winky key，审视频只能抽帧看画面，配法见README 第三节" }
$env:PYTHONIOENCODING = "utf-8"
python (Join-Path $dst "scripts\text_check.py") (Join-Path $dst "tests\bad.txt") | Select-Object -First 1
Write-Host "装好了：$dst，重开 Codex 生效"
