# 无尽冬日素材审核（gof-ad-audit，Codex 插件）

装好以后在 Codex 里直接说「审一下这条素材」「这句文案能不能过审」，它会按无尽冬日国内送审标准（2026-10-21 版）出带时间码的问题清单和改法。Codex 桌面版和 lark-agent（飞书机器人）都能加载。

## 目录

```
.agents/plugins/marketplace.json     本仓库就是一个 marketplace（名字 gof-ad-audit）
plugins/gof-ad-audit/                插件本体，安装和打包的就是这个目录
  plugin.json                        可移植插件清单（Agent Plugins 1.0.0）
  skills/gof-ad-audit/
    SKILL.md                         Codex 读的流程
    agents/openai.yaml               技能在 Codex 里的名字和简介
    references/standard.md           审核标准全文（A1 到 F3）
    references/video_prompt.md       给 Gemini 的看片要求
    scripts/text_check.py            文字初筛
    scripts/analyze_video.py         调 Gemini 看整条视频
    scripts/extract_srt.py           从 Gemini 报告里抽字幕
    scripts/frames.py                抽帧，给 Codex 逐帧看图核细节
    scripts/feishu.py                读飞书文档：交给 feishu 插件
    scripts/workdir.py               每次审核的工作文件夹
dev/                                 开发专用，不进入发布包
  tests/bad.txt, good.txt            text_check 的样例
  test_scripts.py                    脚本的自检
  package_plugin.mjs                 插件结构检查和打包
docs/lark-agent-integration.md       放进 lark-agent
```

## 一、装插件

在这个文件夹里打开终端，运行

```
codex plugin marketplace add .
codex plugin add gof-ad-audit@gof-ad-audit
```

装完重开 Codex 就能用。没有 `codex` 命令时，在 Codex 的插件设置里添加插件市场，选这个文件夹，再安装 gof-ad-audit。读飞书文档还要装 [feishu 插件](https://github.com/Finjix/feishu-plugin)。

lark-agent：见 [docs/lark-agent-integration.md](docs/lark-agent-integration.md)。

## 二、要装的软件

- Python 3.8 以上（Windows 上命令是 `python`）
- ffmpeg（Mac：`brew install ffmpeg`；Windows：从 [ffmpeg.org 的下载页](https://ffmpeg.org/download.html) 进 Windows 构建（gyan.dev 的 `ffmpeg-release-essentials.zip`），解压到比如 `%LOCALAPPDATA%\Programs\ffmpeg`，把里面的 `bin` 加进用户环境变量 `Path`，重开终端后 `ffmpeg -version` 能出版本号就好）
- 读飞书文档：[feishu 插件](https://github.com/Finjix/feishu-plugin)（Node.js 24+）。登录是它管的，用户用飞书手机端扫一次码，和其他插件共用

不需要装任何 Python 包。

## 三、Winky key（审视频强烈建议配）

审视频时插件会调公司 Winky 上的 Gemini 看整条片子，它能听口播和背景音乐。没有 key 也能用，只是只能抽帧看画面，听不到声音。

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

为什么不用环境变量：Codex 默认会把名字里带 KEY 的环境变量过滤掉，不传给它跑的命令，设了也读不到。

key 只放在自己电脑上，别发群里，别提交进仓库。lark-agent 里所有用户共用运行机器人那个 Windows 账号的 key 文件。

## 四、Codex 联网

调 Gemini 要联网。Codex 沙箱默认不联网，第一次审视频时它会申请放行，同意就行。不想每次点，在 `~/.codex/config.toml` 里加

```
[sandbox_workspace_write]
network_access = true
```

## 五、怎么用

- 审视频：「审一下 /路径/xxx.mp4，投腾讯小程序」（lark-agent 里直接把视频发给机器人）
- 审文案：「这句口播能不能过审：……」
- 审飞书脚本：把飞书文档链接发给它（新版文档、知识库、电子表格都行；第一次会让你扫码登录飞书）
- 审封面或截图：把图片给它

它先看一眼素材（时长、有没有声音、文件名和几帧画面），只问看不出来的（投哪些渠道：字节、腾讯、星广，小程序还是 APP；有没有原始字幕或脚本），只发问题，然后停下等你回复；回答问题或回「开始」就开审，一直审完再出报告，中间不再问。没回答的按默认来（渠道没说就按三个渠道、小程序和 APP 都审）。没什么要问的、说「直接审」、或只贴几句文案，都当场就审。

审核的中间文件（Gemini 报告、抽出的字幕、抽帧、拉下来的脚本）放在 `scripts/workdir.py` 给的文件夹：lark-agent 里是 `user/<名>/gof-ad-audit/work/`，7 天没动过的自动删掉；桌面版是当前目录下的 `审核_<片名>`。

## 六、几件要知道的事

- 只管合规，不管好不好看
- 机器初筛会漏也会误报，红线和拿不准的最后还是要人看，报告里会写清哪些是看图核过的，哪些只是初筛
- 人数只说全球 3 亿，付费只说不用氪金，这两条是定死的口径，有新说法先找汤泽洋确认
- 标准统一由汤泽洋维护，别改自己本地的副本。遇到新的拒审案例发给他，更新后重新发包
- 素材是公司内部的，插件只走 Winky、飞书和 Codex 本身，别让它传到别的网站

## 开发与测试

```
python -m unittest discover -s dev -p "test_*.py"     # 脚本自检（frames 要本机有 ffmpeg）
node dev/package_plugin.mjs --check                     # 插件结构检查
node dev/package_plugin.mjs --output dev/dist/gof-ad-audit.zip   # 打包（附 SHA-256）
```

改了 standard.md 或 text_check.py 以后一定跑一遍：bad.txt 每行是一个真拒审过的写法（必改应 ≥ 26），good.txt 是合规写法（必改应为 0）。插件运行需要的脚本和资料放在 `plugins/gof-ad-audit/`，测试和工具放在 `dev/`。

读飞书文档以前用公司的 lark-cli（`lark-cli docs +fetch --as user`，要先另装它并单独登录），现在改成 feishu 插件（飞书官方 Node SDK，`scripts/feishu.py` 找到它并原样运行），登录和 requirement-auto 共用。
