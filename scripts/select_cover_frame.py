#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面选帧: 从源片抽候选帧, 用图像统计打分排序, 供封面底图挑选。

打分 = 对比度*1.7 + 信息熵*7.0 + 边缘强度*1.2 - 过暗/过曝惩罚 (评分公式继承 AutoYY)。
注意: 打分只保证"画面有信息量、不过黑不过曝", 人物是否合适(女主/颜值/构图)必须再逐帧识图复核,
详见 references/cover-publish.md。

用法:
  python scripts/select_cover_frame.py <源视频> --times 1620,2320,4350
  python scripts/select_cover_frame.py <源视频> --samples 14 [--range 0.10-0.95]
  [--top 5] [--outdir 封面帧] [--ffmpeg <ffmpeg路径>]

输出:
  <outdir>/候选帧-t<秒>.jpg (全部候选) + stdout 打分排行。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageFilter, ImageOps, ImageStat

WINDOWS_FFMPEG_HINTS = (
    r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe",
    r"D:\@佳康顺矩阵\@工具\ffmpeg\ffmpeg.exe",
)


def find_ffmpeg(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    for hint in WINDOWS_FFMPEG_HINTS:
        if os.path.isfile(hint):
            return hint
    raise SystemExit("找不到 ffmpeg, 请用 --ffmpeg 指定路径")


def duration_seconds(ffmpeg: str, video: str) -> float:
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", video],
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        raise SystemExit(f"读不到视频时长: {video}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def frame_score(path: str) -> float:
    image = Image.open(path).convert("RGB").resize((320, 180))
    gray = ImageOps.grayscale(image)
    stat = ImageStat.Stat(gray)
    mean = stat.mean[0]
    contrast = stat.stddev[0]
    entropy = gray.entropy()
    edge = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
    exposure_penalty = abs(mean - 112) * 0.20
    black_penalty = max(0, 42 - mean) * 1.8
    white_penalty = max(0, mean - 215) * 1.8
    return (contrast * 1.7 + entropy * 7.0 + edge * 1.2
            - exposure_penalty - black_penalty - white_penalty)


def extract(ffmpeg: str, video: str, t: float, out: str) -> None:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
           "-i", video, "-frames:v", "1", "-q:v", "1", "-y", out]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def parse_times(spec: str) -> list[float]:
    return [float(x) for x in spec.replace("，", ",").split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="封面选帧: 抽候选帧并按图像统计打分")
    ap.add_argument("video", help="源视频路径")
    ap.add_argument("--times", help="指定秒数, 逗号分隔, 如 1620,2320,4350")
    ap.add_argument("--samples", type=int, help="均匀采样帧数(与 --times 二选一)")
    ap.add_argument("--range", default="0.12-0.94", help="采样区间的时长比例, 默认 0.12-0.94")
    ap.add_argument("--top", type=int, default=5, help="排行里建议优先复看的帧数, 默认 5")
    ap.add_argument("--outdir", default="封面帧", help="输出目录")
    ap.add_argument("--ffmpeg", help="ffmpeg 路径(默认自动查找)")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg(args.ffmpeg)
    if not os.path.isfile(args.video):
        raise SystemExit(f"源视频不存在: {args.video}")

    if args.times:
        times = parse_times(args.times)
    elif args.samples:
        duration = duration_seconds(ffmpeg, args.video)
        lo_s, hi_s = (float(x) for x in args.range.split("-"))
        lo, hi = duration * lo_s, duration * hi_s
        step = (hi - lo) / max(args.samples - 1, 1)
        times = [lo + i * step for i in range(args.samples)]
    else:
        raise SystemExit("需要 --times 或 --samples")

    os.makedirs(args.outdir, exist_ok=True)
    scored: list[tuple[float, str]] = []
    for t in times:
        out = os.path.join(args.outdir, f"候选帧-t{int(round(t))}.jpg")
        extract(ffmpeg, args.video, t, out)
        scored.append((frame_score(out), out))

    scored.sort(key=lambda item: item[0], reverse=True)
    print(f"共 {len(scored)} 帧, 按画面信息量排行:")
    for i, (score, path) in enumerate(scored, 1):
        mark = "◆ 建议复看" if i <= args.top else "  "
        print(f"{mark} {score:7.2f}  t={os.path.basename(path)}")
    print("\n下一步: 对前几帧做识图复核(女主颜值/姿态/标题留白), 人工确认最佳帧后导出高清底图。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
