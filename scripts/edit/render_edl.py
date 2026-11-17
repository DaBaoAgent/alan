# -*- coding: utf-8 -*-
"""EDL → ffmpeg-skill 的 project.json，并可选择直接执行渲染。

契约对齐（读 vendor/ffmpeg-skill/scripts/render.py 的 OBJECT_KEYS）：
    clips[] : {src, in, out, speed}   speed 是播放倍速，内部 fit.py --duration 原长/speed
    audio   : {replace: 配音.wav}      audio.py 的 --replace = 整条音轨替换，按画面长度裁剪/补静音
    captions: {srt}                    caption.py 走 libass
    loudness: {lufs: -14, tp: -1}      Alan 交付口径
    export  : {preset, normalize:false} 避免二次归一化冲掉 loudness

不写 transition：默认 fade 0.5 会让每个切口吃掉 0.5s，画面总长就对不上配音了。
要转场就改 project.json 里 transition，或走 --transition 参数（默认 none）。
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import (  # noqa: E402
        ALAN_ROOT, FFMPEG_SKILL, build_dir, read_json, run, t_ff, write_json,
    )
else:
    from .common import (  # noqa: E402
        ALAN_ROOT, FFMPEG_SKILL, build_dir, read_json, run, t_ff, write_json,
    )


def project_from_edl(edl: dict, srt: Path | None, args) -> dict:
    video = edl["video"]
    clips = []
    for c in edl["clips"]:
        item = {"src": video, "in": t_ff(c["src_start"]), "out": t_ff(c["src_end"])}
        if abs(c["speed"] - 1.0) > 1e-6:
            item["speed"] = round(c["speed"], 4)
        clips.append(item)

    frame = edl.get("frame") or {"aspect": args.aspect, "width": 1920, "height": 1080, "fps": 30}
    if args.aspect != frame.get("aspect"):
        frame = dict(frame, aspect=args.aspect)
        frame["width"], frame["height"] = (1920, 1080) if args.aspect == "16:9" else (1080, 1920)

    preset = args.preset or ("reels" if frame.get("aspect") == "9:16" else "youtube")

    proj: dict = {
        "output": str(args.output or "final.mp4"),
        "frame": {
            "aspect": frame.get("aspect", "16:9"),
            "width": int(frame.get("width", 1920)),
            "height": int(frame.get("height", 1080)),
            "fps": int(frame.get("fps", 30)),
        },
        "clips": clips,
        "transition": {"type": args.transition, "duration": args.transition_duration},
        "audio": {"replace": edl["audio"]},
        "loudness": {"lufs": args.lufs, "tp": args.tp},
        "export": {"preset": preset, "normalize": False},
        "check": {"platform": preset},
    }
    if srt and Path(srt).exists():
        proj["captions"] = {
            "srt": str(srt),
            "font": args.font,
            "size": args.font_size,
            "position": "bottom",
            "margin": args.margin,
            "max_lines": 2,
        }
    return proj


def write_edl_csv(edl: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["n", "seg", "sub", "narr_start", "narr_end", "narr_dur",
                    "src_start", "src_end", "speed", "shot", "score", "source", "text"])
        for c in edl["clips"]:
            w.writerow([c["n"], c["seg"], c["sub"], c["narr_start"], c["narr_end"],
                        c["narr_dur"], c["src_start"], c["src_end"], c["speed"],
                        c["shot"], c["score"], c["source"], c["text"]])


def _loudness_ok(mp4: Path, lufs: float, preset: str) -> bool:
    """直接读 check.py 的完整输出：只有 loudness 行 FAIL 才算不通过。"""
    proc = subprocess.run(
        [sys.executable, str(FFMPEG_SKILL / "check.py"), str(mp4),
         "--platform", preset, "--lufs", str(lufs)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode == 0:
        return True
    return not re.search(r"FAIL[^\n]*loudness|loudness[^\n]*FAIL", out)


def _repair_loudness(mp4: Path, lufs: float, tp: float, build: Path) -> None:
    """loudnorm 的 linear 模式在真峰值受限时会欠调 1~2dB，再跑一遍通常能进 ±2 容差。"""
    tmp = build / (mp4.stem + "_loud.mp4")
    run([sys.executable, str(FFMPEG_SKILL / "loudness.py"), str(mp4), "-o", str(tmp),
         "-I", str(lufs), "--tp", str(tp), "--timeout", "1800"], quiet=False)
    shutil.move(str(tmp), str(mp4))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="EDL → ffmpeg-skill project.json")
    ap.add_argument("--work")
    ap.add_argument("--edl", help="默认 <build>/edl.json")
    ap.add_argument("--srt", help="默认 <build>/subtitle.srt；传 none 不烧字幕")
    ap.add_argument("--out", help="默认 <build>/project.json")
    ap.add_argument("--output", help="成片文件名，默认 final.mp4")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"])
    ap.add_argument("--preset", default=None, help="youtube/reels/shorts/tiktok，默认按画幅")
    ap.add_argument("--transition", default="none", choices=["none", "fade", "dissolve", "slide"])
    ap.add_argument("--transition-duration", type=float, default=0.3)
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.0)
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--font-size", type=int, default=20,
                    help="ASS points，按 288p 脚本缩放：1080p 实际字高≈size×3.75，20≈75px")
    ap.add_argument("--margin", type=int, default=60,
                    help="字幕底边距（像素，caption.py 的 --margin 是整数不是比例）")
    ap.add_argument("--csv", action="store_true", help="同时导出 edl.csv 供人工核对")
    ap.add_argument("--run", action="store_true", help="生成后立刻调 render.py 渲染")
    ap.add_argument("--no-overwrite", action="store_true",
                    help="目标成片已存在时拒绝覆盖（默认覆盖，流水线重跑是常态）")
    ap.add_argument("--no-loudness-fix", action="store_true",
                    help="不做事后音量复核（默认复核，loudnorm 欠调时自动补一次）")
    ap.add_argument("--export-timeline", default=None,
                    help="同时导出 fcpxml/otio 时间线，进 Premiere/Resolve 返工")
    ap.add_argument("--render-work", default=None, help="渲染中间目录，默认 <build>/render_work")
    args = ap.parse_args(argv)

    work = Path(args.work).resolve() if args.work else None
    build = build_dir(work) if work else build_dir(".")
    edl_p = Path(args.edl) if args.edl else build / "edl.json"
    if not edl_p.exists():
        raise SystemExit(f"缺少 {edl_p}，先跑 match_edl.py")
    edl = read_json(edl_p)

    srt = None if args.srt == "none" else Path(args.srt) if args.srt else build / "subtitle.srt"
    proj = project_from_edl(edl, srt, args)

    out = Path(args.out) if args.out else build / "project.json"
    write_json(out, proj)

    if args.csv:
        write_edl_csv(edl, build / "edl.csv")
        print(f"  csv : {build / 'edl.csv'}")

    total = sum(c["narr_dur"] for c in edl["clips"])
    print(f"project 生成：{len(proj['clips'])} clip / 画面总长 {total:.1f}s / 配音 {edl['duration']:.1f}s")
    print(f"  project : {out}")
    print(f"  audio.replace = {Path(edl['audio']).name}")
    if srt and srt.exists():
        print(f"  captions.srt = {srt}")
    else:
        print("  [note] 没有 SRT，成片不带硬字幕")

    if not args.run:
        print("  下一步：python vendor/ffmpeg-skill/scripts/render.py "
              f"\"{out}\" --work \"{args.render_work or build / 'render_work'}\"")
        return 0

    argv_cmd = [
        sys.executable, str(FFMPEG_SKILL / "render.py"), str(out),
        "--work", str(args.render_work or build / "render_work"),
    ]
    if args.export_timeline:
        argv_cmd += ["--export-timeline", str(args.export_timeline)]
    if not args.no_overwrite:
        argv_cmd.append("--overwrite")
    print("开始渲染（ffmpeg-skill）...")
    produced = build / str(proj["output"])
    ok = True
    try:
        run(argv_cmd, cwd=str(build), timeout=None, quiet=False)
    except RuntimeError as exc:
        # ffmpeg-skill 的 check 阶段不合格时也返回非零，但成片往往已经写出来了。
        # 成片存在就继续，不把已完成的渲染丢掉。
        ok = False
        if not produced.exists():
            for cand in build.glob("*.mp4"):
                produced = cand
                break
        if not produced.exists():
            raise
        print("[warn] ffmpeg-skill 质量检查未通过：")
        print("\n".join(str(exc).strip().splitlines()[-3:]))

    preset = (proj.get("check") or {}).get("platform", "youtube")
    if produced.exists() and not args.no_loudness_fix:
        if not _loudness_ok(produced, args.lufs, preset):
            print("  音量欠调，补一次 loudness 校准...")
            _repair_loudness(produced, args.lufs, args.tp, build)
            ok = _loudness_ok(produced, args.lufs, preset)

    # 片目录根只放最终交付物：把成片从 build/ 挪出去
    if produced.exists() and work and produced.parent == build:
        target = work / produced.name
        if target.exists():
            target.unlink()
        shutil.move(str(produced), str(target))
        produced = target

    if produced.exists() and ok:
        print(f"渲染完成：{produced}")
        return 0
    if produced.exists():
        print(f"[warn] 成片已生成但未全部通过质检：{produced}")
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
