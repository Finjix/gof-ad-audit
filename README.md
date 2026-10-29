# 无尽冬日素材审核 skill（Codex 版）安装说明

装好以后在 Codex 里直接说「审一下这条素材」「这句文案能不能过审」，它会按无尽冬日国内送审标准（2026-10-21 版）出带时间码的问题清单和改法

## 一、装 skill

Mac：在这个文件夹里打开终端，运行

```
bash install.sh
```

Windows：在这个文件夹里打开 PowerShell，运行

```
powershell -ExecutionPolicy Bypass -File install.ps1
```

两个脚本做的事一样，把 gof-ad-audit 文件夹拷到 `~/.codex/skills/` 下面（已经有旧版会先备份） 装完重开 Codex 就能用

手动装也行，把 gof-ad-audit 整个文件夹放进 `~/.codex/skills/`（Windows 是 `C:\Users\你的用户名\.codex\skills\`）

## 二、要装的软件

- Python 3.8 以上
- ffmpeg（Mac：`brew install ffmpeg`，Windows：`winget install ffmpeg`）

不需要装任何 Python 包

## 三、Winky key（审视频强烈建议配）

审视频时 skill 会调公司 Winky 上的 Gemini 看整条片子，它能听口播和背景音乐 没有 key 也能用，只是只能抽帧看画面，听不到声音

配法：把自己的 Winky（lumos）key 写进一个文件，只写一行

Mac
```
mkdir -p ~/.config/winky && printf '%s' '你的key' > ~/.config/winky/key && chmod 600 ~/.config/winky/key
```

Windows PowerShell
```
New-Item -ItemType Directory -Force $HOME\.config\winky | Out-Null
Set-Content -NoNewline -Encoding ascii $HOME\.config\winky\key '你的key'
```

为什么不用环境变量：Codex 默认会把名字里带 KEY 的环境变量过滤掉，不传给它跑的命令，设了也读不到

key 只放在自己电脑上，别发群里，别提交进仓库

## 四、Codex 联网

调 Gemini 要联网 Codex 沙箱默认不联网，第一次审视频时它会申请放行，同意就行 不想每次点，在 `~/.codex/config.toml` 里加

```
[sandbox_workspace_write]
network_access = true
```

## 五、怎么用

- 审视频：「审一下 /路径/xxx.mp4，投腾讯小程序」
- 审文案：「这句口播能不能过审：……」
- 审飞书脚本：把飞书文档链接发给它（要先装公司的 lark-cli skill）
- 审封面或截图：把图片路径给它

先告诉它素材类型（3D 玩法、解说、真人、AI、明星）和投哪个渠道，审得更准

## 六、几件要知道的事

- 只管合规，不管好不好看
- 机器初筛会漏也会误报，红线和拿不准的最后还是要人看，报告里会写清哪些是看图核过的，哪些只是初筛
- 人数只说全球 3 亿，付费只说不用氪金，这两条是定死的口径，有新说法先找汤泽洋确认
- 标准统一由汤泽洋维护，别改自己本地的副本 遇到新的拒审案例发给他，更新后重新发包
- 素材是公司内部的，skill 只走 Winky 和 Codex 本身，别让它传到别的网站

## 包里有什么

```
gof-ad-audit/
  SKILL.md                    Codex 读的流程
  references/standard.md      审核标准全文（A1 到 F3）
  references/video_prompt.md  给 Gemini 的看片要求
  scripts/text_check.py       文字初筛
  scripts/analyze_video.py    调 Gemini 看整条视频
  scripts/extract_srt.py      从 Gemini 报告里抽字幕
  scripts/frames.py           抽帧，给 Codex 逐帧看图核细节
  tests/bad.txt, good.txt     自检用
```

装完想确认没坏，在终端跑

```
python3 ~/.codex/skills/gof-ad-audit/scripts/text_check.py ~/.codex/skills/gof-ad-audit/tests/bad.txt
```

第一行显示「必改 26」就是好的（Windows 用 `python`）
