#!/usr/bin/env python3
"""把视频的一段抽成带时间戳文件名的 JPG，给 Codex 逐帧看图核细节。

审核里要逐字核的东西（提示语、温度和资源数字里的 64/648、闪一下的手指图标、
小字水印）用这个抽帧再看图。一次只抽一小段，闪现的东西用高帧率。

用法:
  python3 frames.py 片.mp4 --start 12 --end 18                 # 默认 3fps
  python3 frames.py 片.mp4 --start 15.7 --end 16.4 --fps 30     # 逐帧，抓闪现数字
  python3 frames.py 片.mp4 --start 40 --end 45 --crop 0,0,540,300   # 只看左上角并放大
  python3 frames.py 片.mp4 --fps 1                              # 整条每秒一帧，没有 Winky key 时通看用

输出: <out>/f_0015.97s.jpg ...，最后打印文件列表。时间戳按抽帧间隔推算，误差在一帧以内。
依赖: Python 3.8+ 标准库 + ffmpeg/ffprobe。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description="抽帧给 Codex 看图")
    ap.add_argument("video")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, help="结束秒，不传到片尾")
    ap.add_argument("--fps", type=float, default=3.0, help="默认 3；闪现的数字和图标用 30")
    ap.add_argument("--crop", help="x,y,w,h（原片像素），只看这一块并放大到至少 1024 宽")
    ap.add_argument("--max-frames", type=int, default=60, help="超过就报错，缩短时间段或降帧率")
    ap.add_argument("--out", help="输出目录，默认 ./frames_<起>-<止>")
    a = ap.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("错误: 找不到 ffmpeg/ffprobe，先装（mac: brew install ffmpeg；Windows: 从 ffmpeg.org 的 Windows 构建下载，把 bin 加进 PATH，见 README）")
    if not os.path.isfile(a.video):
        sys.exit(f"错误: 找不到视频 {a.video}")

    end = a.end if a.end is not None else duration(a.video)
    if end is None or end <= a.start:
        sys.exit("错误: 结束时间不对，或读不到视频时长")
    n = int((end - a.start) * a.fps + 0.999)
    if n > a.max_frames:
        sys.exit(f"错误: 要抽 {n} 帧，超过 --max-frames {a.max_frames}。缩短时间段或降 --fps")

    vf = [f"fps={a.fps}"]
    if a.crop:
        x, y, w, h = [int(v) for v in a.crop.split(",")]
        vf.append(f"crop={w}:{h}:{x}:{y}")
        vf.append("scale='if(lt(iw,1024),1024,iw)':-2:flags=lanczos")
    else:
        vf.append("scale='if(gt(ih,1600),-2,iw)':'if(gt(ih,1600),1600,ih)'")

    out = a.out or f"frames_{a.start:g}-{end:g}"
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="frames_")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{a.start}", "-i", a.video,
           "-t", f"{end - a.start}", "-vf", ",".join(vf), "-q:v", "2",
           os.path.join(tmp, "%05d.jpg")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg 出错: {r.stderr[:500]}")

    files = sorted(os.listdir(tmp))
    written = []
    for i, name in enumerate(files):
        t = a.start + i / a.fps
        dst = os.path.join(out, f"f_{t:07.2f}s.jpg")
        shutil.move(os.path.join(tmp, name), dst)
        written.append(dst)
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"[抽帧] {a.start:g}s - {end:g}s，{a.fps:g}fps，共 {len(written)} 帧 → {out}")
    for w in written:
        print(w)


if __name__ == "__main__":
    main()
