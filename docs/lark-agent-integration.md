# 放进 lark-agent

lark-agent（`D:\project\lark-agent`）把 `plugins/` 下的插件文件夹在启动时装进它自己的 Codex。gof-ad-audit 读飞书文档要用 feishu 插件，两个一起放。

## 怎么放

在 lark-agent 目录里：

```bat
start.cmd stop
robocopy D:\project\feishu-plugin\plugins\feishu plugins\feishu-plugin /MIR
robocopy D:\project\gof-ad-audit\plugins\gof-ad-audit plugins\gof-ad-audit /MIR
start.cmd
```

- `robocopy` 返回 1 到 7 都是成功。之后更新也用 `/MIR`（镜像），覆盖粘贴会把旧版里已删除的文件留下。
- 日志里出现 `已安装插件`，`http://127.0.0.1:8765/health` 的 `plugins.loaded` 里有 `gof-ad-audit` 和 `feishu`，就是装好了。`start.cmd doctor` 只看不改。
- 服务运行中复制没有效果，只在启动时扫描。

用户在飞书里发来视频、图片、文案或飞书脚本链接，说要审素材时，Codex 按技能描述选用 `gof-ad-audit:gof-ad-audit`。

## 约定

| 项目 | 内容 |
|---|---|
| 插件在 Codex 里的名字 | `gof-ad-audit@lark-agent`；技能 `gof-ad-audit:gof-ad-audit` |
| 运行环境 | 机器人那台电脑的 Python 3.8+（`python`）、ffmpeg/ffprobe 在服务进程的 `PATH` 上（装好后要重启 lark-agent，新 `PATH` 才进得了服务进程）、Node.js 24+（feishu 插件） |
| Winky key | 运行机器人的 Windows 账号的 `~/.config/winky/key`，所有用户共用。审视频必须有：没有的话机器人直接回复还没配 key，不审 |
| 飞书 | `scripts/feishu.py` 找到 feishu 插件（Codex 插件缓存里同一个 marketplace 的 `feishu/<版本>/server/dist/feishu.mjs`）并用 `node` 原样运行；子进程继承宿主每轮给的 `LARK_AGENT_USER_DIR`、`LARK_AGENT_USER_OPEN_ID`、`FEISHU_APP_ID`、`FEISHU_APP_SECRET`，所以是这个用户自己的飞书登录（`user/<名>/feishu/`），和 requirement-auto 共用 |
| 数据位置 | 工作文件在 `user/<名>/gof-ad-audit/work/<时间>_<片名>/`（`scripts/workdir.py`），7 天没动过的在下次审核时删掉。不放在 `workspace/`：lark-agent 会把工作目录里新出现的文件都发给用户 |
| 交付 | 审核结论写在回复里；飞书登录二维码写在工作目录，随回复发给用户 |
| 附件 | 用户发来的视频、图片在 `user/<名>/workspace/input/`，技能只读不改 |

## 验证过什么

- 本机（2026-10-29）：插件结构检查、`python -m unittest discover -s dev`（含用 ffmpeg 生成的测试视频抽帧）、`feishu.py` 在 Codex 插件缓存的布局里找到 feishu 插件。
- lark-agent 安装：见 lark-agent 的提交记录和 `/health`。

没有验证：真实模型回合里走一遍完整审核（需要真实素材和 Winky key）。
