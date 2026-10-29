#!/usr/bin/env python3
"""
analyze_video.py — 经公司 Winky 代理调 Gemini 真·看视频(画面+声音),gof-ad-audit 用它出逐条转写和风险清单。

用法:
  python3 analyze_video.py <视频> --model gemini-4-argon --keep-audio --prompt-file ../references/video_prompt.md > report.md
  可选 --start S --end E 只看一段;--fps / --low-res 手动控制采样
  python3 analyze_video.py <视频> --probe    定计划用,不联网:时长、有没有音轨、有没有 Winky key

依赖: Python 3.8+ 标准库 + ffmpeg/ffprobe(压缩、截段用)。certifi 可选。
Key(Winky/Lumos key,按顺序找,找到即用):
  1. 环境变量 WINKY_API_KEY(注意 Codex 默认会过滤名字带 KEY 的环境变量,在 Codex 里多半读不到)
  2. 文件 ~/.config/winky/key(只放一行 key,推荐)
  3. ~/.claude/settings.json 里的 ANTHROPIC_API_KEY(装了公司 Claude Code 环境的机器)
"""
import base64, json, os, sys, ssl, subprocess, tempfile, urllib.request, argparse

WINKY_GEMINI_URL = "https://lumos.diandian.info/winky/gemini/v1/models/{model}:generateContent"
SETTINGS = os.path.expanduser("~/.claude/settings.json")
KEY_FILE = os.path.expanduser("~/.config/winky/key")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ANALYSIS_PROMPT = """你是顶级影视分析师 + AI视频提示词专家。请极其精确地【逐秒/逐镜】分析这段视频,输出一份可用于精确复现的结构化报告。必须完全基于你真实看到的画面与镜头运动,不要编造、不要泛泛而谈。用中文分节输出:

1.【整体】媒介质感(实拍/CG/引擎渲染?最像什么,如UE5过场/概念动画/真人)、画幅比例与黑边、整体色调、剪辑节奏(快切/长镜头/一镜到底)、总镜头数(切了几次)。

2.【逐秒时间轴】按时间段(0-2s,2-4s...)精确描述每段:
   - 画面内容(主体、配角、环境、道具,带在画面中的位置)
   - **镜头运动**(推/拉/横移/上下摇/跟随/环绕/手持?方向?速度快慢匀速否?)——这是最重要的,务必精确,这是静态截图看不出的关键
   - 主体的具体动作
   - 转场/切镜的位置与方式(硬切/叠化/淡入淡出/无缝)
   - 光线方向与色温

3.【主体】外貌/服装/道具的超细节(颜色、款式、材质),运动方向,在画面中的固定位置。用于锁一致性。

4.【色温/氛围演进】画面基调随时间如何变化(精确到秒),分几个阶段。

5.【运镜总结】全片主导镜头语言、速度节奏、以及导演用了什么技巧(如前景视差、逆光剪影、景深)。

6.【音频推断】背景音乐类型/情绪、关键音效。

7.【一致性锚点】提炼一组中文关键词 + 一组英文关键词,是每个复现镜头都该重复、用来锁死本片统一视觉与主体身份的词。

请具体、可操作。这份报告会直接用于撰写复现该视频的 AI 视频提示词(Seedance/可灵/Midjourney)。"""

def find_key():
    if os.environ.get("WINKY_API_KEY"):
        return os.environ["WINKY_API_KEY"].strip()
    if os.path.isfile(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            k = f.read().strip()
        if k:
            return k
    if os.path.isfile(SETTINGS):
        with open(SETTINGS, encoding="utf-8") as f:
            cfg = json.load(f)
        k = cfg.get("env", {}).get("ANTHROPIC_API_KEY") or cfg.get("ANTHROPIC_API_KEY")
        if k:
            return k
    return None

def get_key():
    k = find_key()
    if k:
        return k
    print("错误: 找不到 Winky key。把 key 写进 ~/.config/winky/key(一行),或设环境变量 WINKY_API_KEY。")
    print("没有 key 就跳过本脚本,改用 frames.py 抽帧自己看(听不到声音,口播要另找字幕或脚本)。")
    sys.exit(4)

def ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

def compress(src, max_mb, keep_audio=False, sample_fps=None):
    """降级方案:原文件过大时逐级降分辨率/画质,尽量塞进内联上限。
    注意:必须用 force_original_aspect_ratio,否则竖版视频(1080x1920)会被
    scale=1280:-2 放大成 1280x2276,越压越大。
    Gemini 只看按 sample_fps 抽到的帧,编码帧率降到采样率的 2 倍不丢信息,长片体积能小好几倍。"""
    dst = tempfile.mktemp(suffix="_v2p.mp4")
    rate = f",fps={2 * sample_fps:g}" if sample_fps and 2 * sample_fps < 24 else ""
    for side, crf in ((1280, 28), (1280, 32), (960, 32), (854, 34), (640, 36)):
        # min() 防止把小视频放大；force_divisible_by=2 防止奇数宽度让 libx264 报错（408x734 曾被放成 711x1280）
        vf = (f"scale=w='min({side},iw)':h='min({side},ih)':force_original_aspect_ratio=decrease:"
              f"force_divisible_by=2{rate}")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-i", src, "-vf", vf, "-c:v", "libx264",
               "-crf", str(crf), "-preset", "fast"]
        cmd += ["-c:a", "aac", "-b:a", "64k", "-ac", "1"] if keep_audio else ["-an"]
        subprocess.run(cmd + [dst], check=True)
        if os.path.getsize(dst) <= max_mb * 1024 * 1024:
            return dst, side, crf
    return dst, side, crf  # 尽力而为

def probe_duration(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return None

def has_audio(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                              "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
        return bool(out.stdout.strip())
    except Exception:
        return None

def probe(path):
    """审核前定计划用:时长、有没有音轨、有没有 Winky key、会怎么采样。不联网。"""
    duration = probe_duration(path)
    return {"duration": round(duration, 1) if duration else None,
            "size_mb": round(os.path.getsize(path) / 1024 / 1024, 1),
            "audio": has_audio(path),
            "winky_key": bool(find_key()),
            "sampling": plan_sampling(duration, None, None)[2]}

def trim(src, start, end):
    """切出 [start, end) 一段重编码(不用 -c copy,那样只能切在关键帧上)。"""
    dst = tempfile.mktemp(suffix="_v2p_seg.mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start or 0)]
    if end is not None:
        cmd += ["-t", str(end - (start or 0))]
    cmd += ["-i", src, "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "aac", "-b:a", "128k", dst]
    subprocess.run(cmd, check=True)
    return dst

# gemini-4-argon 上下文实测 1M。留 30 万给 prompt 和输出,视频+音频按 70 万算。
TOKEN_BUDGET = 700_000

def plan_sampling(duration, fps, hi_res):
    """没显式指定的项按时长自动定:默认 4fps + 高分辨率;长片先降帧率,
    降到 1fps 以下再改低分辨率换回帧率。每帧约 258 token(高)/ 66(低),音频约 32 token/秒。"""
    if not duration:
        return fps or 4, hi_res is not False, "读不到时长,按默认 4fps 高分辨率"
    budget = TOKEN_BUDGET - 32 * duration
    cap = lambda tpf: budget / (duration * tpf)
    if hi_res is None:
        hi_res = fps * 258 * duration <= budget if fps else cap(258) >= 1
    tpf = 258 if hi_res else 66
    if fps is None:
        fps = max(0.1, min(4, int(cap(tpf) * 100) / 100))
    est = duration * (fps * tpf + 32)
    plan = f"{duration:.0f}s → {fps:g}fps {'高' if hi_res else '低'}分辨率,预计约 {est / 1000:.0f}k token"
    if est > TOKEN_BUDGET:
        plan += " (超出预算,可能报上下文超限,建议 --start/--end 分段)"
    return fps, hi_res, plan

def analyze(video_path, model, max_mb, force_compress, prompt=None, fps=None,
            keep_audio=False, media_resolution=None):
    key = get_key()
    size_mb = os.path.getsize(video_path) / 1024 / 1024
    used = video_path
    note = f"原文件 {size_mb:.1f}MB,原画质上传"
    # 原画质优先;超内联上限或强制则压缩
    if force_compress or size_mb > max_mb:
        used, side, crf = compress(video_path, max_mb, keep_audio, fps)
        out_mb = os.path.getsize(used) / 1024 / 1024
        note = (f"原文件 {size_mb:.1f}MB 超过 {max_mb}MB 内联上限,已压到 "
                f"{out_mb:.1f}MB(长边{side},crf{crf},"
                f"{'含音轨' if keep_audio else '无音轨'})再上传")
        if out_mb > max_mb:
            note += f"。仍超上限,大概率失败,请用 --start/--end 分段"
    with open(used, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    video_part = {"inline_data": {"mime_type": "video/mp4", "data": b64}}
    # Gemini 默认按 1fps 采样视频。要看清快切/微动作必须调高,代价是 token 线性增长。
    if fps:
        video_part["video_metadata"] = {"fps": fps}
    payload = {"contents": [{"role": "user", "parts": [
        video_part,
        {"text": prompt or ANALYSIS_PROMPT}]}]}
    # Gemini 3 默认低清采样视频(约 66 token/帧),看不清小物件、UI 数字、武器形制。
    # 调 HIGH 后约 258 token/帧。实测同一段 s1:默认答"拿着弓、UI 显示 1",
    # HIGH 答"拿着剑、UI 显示 10",后者才是对的。要细节就必须开。
    # 注意只能放 generationConfig,放在 part 里会 400。
    if media_resolution:
        payload["generationConfig"] = {"mediaResolution": media_resolution}
    req = urllib.request.Request(
        WINKY_GEMINI_URL.format(model=model),
        data=json.dumps(payload).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=600, context=ssl_ctx()) as resp:
        data = json.load(resp)
    text = data["candidates"][0]["content"]["parts"][-1]["text"]
    tokens = data.get("usageMetadata", {}).get("totalTokenCount")
    return note, text, tokens

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--model", default="gemini-4-argon")
    ap.add_argument("--max-mb", type=float, default=18)
    ap.add_argument("--force-compress", action="store_true")
    ap.add_argument("--prompt-file", help="自定义分析 prompt 的文本文件路径,不传则用内置通用 prompt")
    ap.add_argument("--fps", type=float,
                    help="视频采样帧率。不传则默认 4(Gemini 自身默认 1,快切/闪帧/旋转方向会看错),"
                         "长片按 token 预算自动降")
    ap.add_argument("--keep-audio", action="store_true", help="压缩时保留音轨(要听台词/音效时必开)")
    ap.add_argument("--hi-res", dest="hi_res", action="store_true", default=None,
                    help="强制高分辨率采样(258 token/帧)。不传时默认就是高分辨率,只有超长片才自动改低")
    ap.add_argument("--low-res", dest="hi_res", action="store_false",
                    help="关掉高分辨率采样(约 66 token/帧),省 token 但小字/UI 数字会看不清")
    ap.add_argument("--start", type=float, help="只分析从这一秒开始的片段(长片分段看);报告里的时间从片段开头算")
    ap.add_argument("--end", type=float, help="片段结束秒")
    ap.add_argument("--probe", action="store_true",
                    help="不调 Gemini,只打印 JSON:时长、有没有音轨、有没有 Winky key、采样计划")
    a = ap.parse_args()
    if not os.path.isfile(a.video):
        print(f"错误: 找不到视频 {a.video}"); sys.exit(1)
    if a.probe:
        print(json.dumps(probe(a.video), ensure_ascii=False)); return
    prompt = None
    if a.prompt_file:
        with open(a.prompt_file, encoding="utf-8") as f:
            prompt = f.read()
    src = a.video
    if a.start is not None or a.end is not None:
        src = trim(a.video, a.start, a.end)
        print(f"[分段] {a.start or 0}s - {a.end if a.end is not None else '结尾'},报告时间 0 = 原片 {a.start or 0}s")
    fps, hi_res, plan = plan_sampling(probe_duration(src), a.fps, a.hi_res)
    print(f"[采样] {plan}")
    try:
        note, text, tokens = analyze(src, a.model, a.max_mb, a.force_compress,
                                     prompt, fps, a.keep_audio,
                                     "MEDIA_RESOLUTION_HIGH" if hi_res else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:1500]
        # 若因体积/inline失败,提示降级
        print(f"HTTP错误 {e.code}: {body}")
        if not a.force_compress:
            print("\n提示: 若为体积/内联限制导致,请加 --force-compress 重试(自动压到720p)。")
        sys.exit(2)
    except Exception as e:
        print(f"错误: {type(e).__name__}: {str(e)[:400]}")
        print("提示: SSL 问题可 pip install certifi;连通性可先用 curl 测 Winky Gemini 接口。")
        sys.exit(3)
    print(f"[视频处理] {note}")
    print(f"[模型] {a.model}   [tokens] {tokens}")
    print("=" * 60)
    print(text)

if __name__ == "__main__":
    main()
