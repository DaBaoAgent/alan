#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scene-aware automatic first-cut and render for movie commentary.

PySceneDetect finds shot boundaries.  The first cut keeps source chronology so
it matches a chronological commentary script, then requires a plan review before
rendering.  This deliberately avoids pretending an LLM can safely infer movie
semantics from arbitrary footage without a reviewable edit decision list.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"缺少 {name}，请先安装并加入 PATH。")
    return found


def execute(values: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(values, check=True, text=True, capture_output=True, encoding="utf-8", errors="replace")


def duration(path: Path) -> float:
    result = execute([executable("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)])
    return float(result.stdout.strip())


def detect(args: argparse.Namespace) -> None:
    if not args.video.is_file():
        raise SystemExit(f"找不到源片: {args.video}")
    try:
        from scenedetect import detect as scene_detect
        from scenedetect.detectors import AdaptiveDetector
    except ImportError:
        raise SystemExit("未安装 PySceneDetect。运行: python -m pip install -r requirements-movie-edit.txt")
    scenes = scene_detect(str(args.video), AdaptiveDetector(adaptive_threshold=args.threshold, min_scene_len=args.min_scene_len))
    payload = {
        "source_video": str(args.video.resolve()), "detector": "PySceneDetect AdaptiveDetector",
        "threshold": args.threshold, "min_scene_len_frames": args.min_scene_len,
        "duration": duration(args.video),
        "scenes": [{"start": scene[0].get_seconds(), "end": scene[1].get_seconds()} for scene in scenes],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenes": len(payload["scenes"]), "output": str(args.output)}, ensure_ascii=False))


def first_cut(args: argparse.Namespace) -> None:
    scenes_data = json.loads(args.scenes.read_text(encoding="utf-8"))
    scenes = scenes_data.get("scenes", [])
    if not scenes:
        raise SystemExit("镜头检测结果为空。")
    voice_duration = duration(args.narration)
    target = args.target_shot_seconds
    clips_needed = max(1, math.ceil(voice_duration / target))
    source_duration = float(scenes_data.get("duration") or duration(args.source_video))
    clips: list[dict] = []
    for index in range(clips_needed):
        narration_start = index * voice_duration / clips_needed
        narration_end = (index + 1) * voice_duration / clips_needed
        narration_length = narration_end - narration_start
        desired_source = (index + 0.5) * source_duration / clips_needed
        candidates = [item for item in scenes if float(item["start"]) + narration_length <= source_duration]
        if not candidates:
            raise SystemExit("原片时长不足以覆盖配音时长。")
        scene = min(candidates, key=lambda item: abs(float(item["start"]) - desired_source))
        source_start = float(scene["start"])
        source_end = source_start + narration_length
        if narration_length < args.minimum_shot_seconds:
            raise SystemExit("每段配音时长小于 --minimum-shot-seconds，请提高 --target-shot-seconds。")
        clips.append({
            "index": len(clips) + 1, "source_start": round(source_start, 3), "source_end": round(source_end, 3),
            "narration_start": round(narration_start, 3), "narration_end": round(narration_end, 3), "approved": False,
        })
    payload = {
        "version": 1, "status": "needs_review", "source_video": str(args.source_video.resolve()),
        "narration_audio": str(args.narration.resolve()), "narration_duration": voice_duration,
        "strategy": "chronological scene-aware first cut", "clips": clips,
        "review_note": "请按解说稿逐段确认镜头含义；确认后将每个 clip 的 approved 改为 true，或用 --allow-unreviewed 渲染初剪。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"clips": len(clips), "plan": str(args.output), "status": payload["status"]}, ensure_ascii=False))


def subtitle_filter(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"subtitles=filename='{value}':charenc=UTF-8"


def render(args: argparse.Namespace) -> None:
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    source = Path(plan["source_video"])
    narration = Path(plan["narration_audio"])
    if not source.is_file() or not narration.is_file():
        raise SystemExit("剪辑计划引用的源片或配音文件不存在。")
    clips = plan.get("clips", [])
    if not clips:
        raise SystemExit("剪辑计划没有 clip。")
    if not args.allow_unreviewed and any(not item.get("approved") for item in clips):
        raise SystemExit("剪辑计划尚未审核。逐段设 approved=true，或仅为试看使用 --allow-unreviewed。")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alan-edit-") as temp:
        temp_path = Path(temp)
        parts: list[Path] = []
        for item in clips:
            part = temp_path / f"clip-{int(item['index']):03d}.mp4"
            length = float(item["source_end"]) - float(item["source_start"])
            execute([
                executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(item["source_start"]),
                "-i", str(source), "-t", f"{length:.3f}", "-an", "-map", "0:v:0", "-c:v", "libx264", "-preset", args.preset,
                "-crf", str(args.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(part),
            ])
            parts.append(part)
        manifest = temp_path / "concat.txt"
        manifest.write_text("".join(f"file '{str(part).replace("'", "'\\''")}'\n" for part in parts), encoding="utf-8")
        visual = temp_path / "visual.mp4"
        execute([executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(visual)])
        command = [executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(visual), "-i", str(narration)]
        if args.subtitle:
            command.extend(["-vf", subtitle_filter(args.subtitle)])
        command.extend(["-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf), "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output)])
        execute(command)
    report = {"output": str(output), "duration": duration(output), "clips": len(clips), "reviewed": all(item.get("approved") for item in clips)}
    output.with_suffix(".render.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="基于 PySceneDetect + FFmpeg 的电影解说自动初剪")
    sub = root.add_subparsers(dest="action", required=True)
    scan = sub.add_parser("detect-scenes", help="检测镜头边界")
    scan.add_argument("--video", type=Path, required=True)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--threshold", type=float, default=3.0)
    scan.add_argument("--min-scene-len", type=int, default=24)
    scan.set_defaults(func=detect)
    plan = sub.add_parser("first-cut", help="生成按剧情时间顺序的可审核初剪计划")
    plan.add_argument("--source-video", type=Path, required=True)
    plan.add_argument("--narration", type=Path, required=True)
    plan.add_argument("--scenes", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--target-shot-seconds", type=float, default=4.2)
    plan.add_argument("--minimum-shot-seconds", type=float, default=1.2)
    plan.set_defaults(func=first_cut)
    make = sub.add_parser("render", help="从审核过的剪辑计划渲染成片")
    make.add_argument("--plan", type=Path, required=True)
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--subtitle", type=Path)
    make.add_argument("--allow-unreviewed", action="store_true")
    make.add_argument("--preset", default="medium")
    make.add_argument("--crf", type=int, default=18)
    make.set_defaults(func=render)
    return root


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
