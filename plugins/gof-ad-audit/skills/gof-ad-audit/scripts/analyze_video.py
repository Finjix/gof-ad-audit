#!/usr/bin/env python3
"""
analyze_video.py — 经公司 Winky 代理调 Gemini 真·看视频(画面+声音),gof-ad-audit 用它出逐条转写和风险清单。

用法:
  python3 analyze_video.py <视频> --model gemini-4-argon --keep-audio > report.md
  默认用 ../references/video_prompt.md 当 prompt,--prompt-file 换别的
  可选 --start S --end E 只看一段;--fps / --low-res 手动控制采样
  python3 analyze_video.py <视频> --probe    审核前用,不联网:时长、有没有音轨、有没有 Winky key
  报告写 stdout;出错信息写 stderr,退出码非 0,重定向到 report.md 时错误照样看得到。

依赖: Python 3.8+ 标准库 + ffmpeg/ffprobe(压缩、截段用)。certifi 可选。
Key(Winky/Lumos key,审视频必须有,按顺序找,找到即用):
  1. 环境变量 WINKY_API_KEY(注意 Codex 默认会过滤名字带 KEY 的环境变量,在 Codex 里多半读不到)
  2. 文件 ~/.config/winky/key(只放一行 key,推荐)
  3. ~/.claude/settings.json 里的 ANTHROPIC_API_KEY,只在同一份配置的 ANTHROPIC_BASE_URL 指向 Winky(lumos)时用,
     免得把真正的 Anthropic key 发给代理
"""
import base64, json, os, sys, ssl, subprocess, tempfile, urllib.error, urllib.request, argparse

WINKY_HOST = "lumos.diandian.info"
WINKY_GEMINI_URL = f"https://{WINKY_HOST}/winky/gemini/v1/models/{{model}}:generateContent"
SETTINGS = os.path.expanduser("~/.claude/settings.json")
KEY_FILE = os.path.expanduser("~/.config/winky/key")
DEFAULT_PROMPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "video_prompt.md")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


class Incomplete(Exception):
    """Gemini 回了,但报告不完整(被截断、被拦、没有正文)。"""


def fail(code, *lines):
    for line in lines:
        print(line, file=sys.stderr)
    sys.exit(code)

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
        env = cfg.get("env", {})
        k = env.get("ANTHROPIC_API_KEY") or cfg.get("ANTHROPIC_API_KEY")
        base = env.get("ANTHROPIC_BASE_URL") or cfg.get("ANTHROPIC_BASE_URL") or ""
        if k and WINKY_HOST in base:
            return k
    return None

def get_key():
    k = find_key()
    if k:
        return k
    fail(4, "错误: 找不到 Winky key,审视频必须有。把 key 写进 ~/.config/winky/key(一行),或设环境变量 WINKY_API_KEY。")

def ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

def compress(src, max_mb, tmp, keep_audio=False, sample_fps=None):
    """降级方案:原文件过大时逐级降分辨率/画质,尽量塞进内联上限。
    注意:必须用 force_original_aspect_ratio,否则竖版视频(1080x1920)会被
    scale=1280:-2 放大成 1280x2276,越压越大。
    Gemini 只看按 sample_fps 抽到的帧,编码帧率降到采样率的 2 倍不丢信息,长片体积能小好几倍。"""
    dst = os.path.join(tmp, "compressed.mp4")
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
    """审核前用:时长、有没有音轨、有没有 Winky key、会怎么采样。不联网。"""
    duration = probe_duration(path)
    return {"duration": round(duration, 1) if duration else None,
            "size_mb": round(os.path.getsize(path) / 1024 / 1024, 1),
            "audio": has_audio(path),
            "winky_key": bool(find_key()),
            "sampling": plan_sampling(duration, None, None)[2]}

def trim(src, start, end, tmp):
    """切出 [start, end) 一段重编码(不用 -c copy,那样只能切在关键帧上)。"""
    dst = os.path.join(tmp, "segment.mp4")
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

def report_text(data):
    """从 generateContent 的返回里取报告正文;不完整就抛 Incomplete,不把半份报告当整份。"""
    candidate = (data.get("candidates") or [{}])[0]
    reason = candidate.get("finishReason")
    parts = candidate.get("content", {}).get("parts") or []
    text = next((p["text"] for p in reversed(parts) if p.get("text")), None)
    if reason == "MAX_TOKENS":
        raise Incomplete("Gemini 输出到上限被截断,转写不全。用 --start/--end 分段重跑")
    if reason != "STOP" or not text:
        blocked = data.get("promptFeedback", {}).get("blockReason")
        raise Incomplete(f"Gemini 没有给出完整报告(finishReason={reason}, blockReason={blocked})。重跑一次,还不行就分段重跑")
    return text

def analyze(video_path, model, max_mb, force_compress, prompt, tmp, fps=None,
            keep_audio=False, media_resolution=None):
    key = get_key()
    size_mb = os.path.getsize(video_path) / 1024 / 1024
    used = video_path
    note = f"原文件 {size_mb:.1f}MB,原画质上传"
    # 原画质优先;超内联上限或强制则压缩
    if force_compress or size_mb > max_mb:
        used, side, crf = compress(video_path, max_mb, tmp, keep_audio, fps)
        out_mb = os.path.getsize(used) / 1024 / 1024
        why = "按 --force-compress" if size_mb <= max_mb else f"超过 {max_mb}MB 内联上限,"
        note = (f"原文件 {size_mb:.1f}MB {why}已压到 "
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
    payload = {"contents": [{"role": "user", "parts": [video_part, {"text": prompt}]}]}
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
    tokens = data.get("usageMetadata", {}).get("totalTokenCount")
    return note, report_text(data), tokens

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--model", default="gemini-4-argon")
    ap.add_argument("--max-mb", type=float, default=18)
    ap.add_argument("--force-compress", action="store_true")
    ap.add_argument("--prompt-file", default=DEFAULT_PROMPT, help="分析 prompt 的文本文件,默认 references/video_prompt.md")
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
        fail(1, f"错误: 找不到视频 {a.video}")
    if a.probe:
        print(json.dumps(probe(a.video), ensure_ascii=False)); return
    if a.start is not None and a.end is not None and a.end <= a.start:
        fail(1, "错误: --end 要大于 --start")
    with open(a.prompt_file, encoding="utf-8") as f:
        prompt = f.read()
    get_key()  # 先查 key,没有就不白压视频
    # 压缩、截段出来的是素材副本:放临时文件夹,跑完就删(素材是公司内部的,不留在电脑上)
    with tempfile.TemporaryDirectory(prefix="gof_video_") as tmp:
        src = a.video
        if a.start is not None or a.end is not None:
            src = trim(a.video, a.start, a.end, tmp)
            print(f"[分段] {a.start or 0}s - {a.end if a.end is not None else '结尾'},报告时间 0 = 原片 {a.start or 0}s")
        fps, hi_res, plan = plan_sampling(probe_duration(src), a.fps, a.hi_res)
        print(f"[采样] {plan}")
        try:
            note, text, tokens = analyze(src, a.model, a.max_mb, a.force_compress,
                                         prompt, tmp, fps, a.keep_audio,
                                         "MEDIA_RESOLUTION_HIGH" if hi_res else None)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:1500]
            # 若因体积/inline失败,提示降级
            hint = [] if a.force_compress else ["提示: 若为体积/内联限制导致,请加 --force-compress 重试(自动压到720p)。"]
            fail(2, f"HTTP错误 {e.code}: {body}", *hint)
        except Incomplete as e:
            fail(5, f"错误: {e}")
        except Exception as e:
            fail(3, f"错误: {type(e).__name__}: {str(e)[:400]}",
                 "提示: SSL 问题可 pip install certifi;连通性可先用 curl 测 Winky Gemini 接口。")
    print(f"[视频处理] {note}")
    print(f"[模型] {a.model}   [tokens] {tokens}")
    print("=" * 60)
    print(text)

if __name__ == "__main__":
    main()
