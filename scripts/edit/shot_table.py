# -*- coding: utf-8 -*-
"""镜头表：原片 → shots.json（每镜 start/end/dur，可选画面描述）。

两个后端：
    pyscenedetect  —— ContentDetector，官方阈值 27（比 0~1 的 scene score 稳）
    ffmpeg         —— select='gt(scene,T)',showinfo，用帧 pts_time 当切点

后处理照搬 movie-narrator 的规则：
    _merge_short_scenes：<2.0s 的镜头并进邻居；
    再丢弃 <0.4s 的碎片（并完后通常不剩）。

--caption-backend openai 会抽每个镜头中点的一帧，让视觉模型写 40 字内的中文描述。
这一步是"精准匹配"的前提：没有描述，匹配层只剩剧情时序先验，精度约等于按比例猜。
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import build_dir, ffmpeg, media_duration, run, write_json  # noqa: E402
else:
    from .common import build_dir, ffmpeg, media_duration, run, write_json  # noqa: E402


def detect_pyscenedetect(video: Path, threshold: float) -> list[tuple[float, float]] | None:
    try:
        from scenedetect import ContentDetector, SceneManager, open_video  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    print(f"  pyscenedetect: ContentDetector(threshold={threshold})")
    cam = open_video(str(video))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold))
    sm.detect_scenes(cam, show_progress=False)
    scenes = sm.get_scene_list()
    return [(s[0].get_seconds(), s[1].get_seconds()) for s in scenes]


def detect_ffmpeg(video: Path, threshold: float) -> list[tuple[float, float]]:
    """scdet 的场景分数（0~100）直接当阈值，比 select 的归一化 scene 值可控。

    经验值：真实电影 10~15 能抓到主要剪辑点；纯色/静态卡段要降到 3~5，
    否则暗场之间的切换会漏检（漏了只会让镜头偏长，不会毁掉 EDL）。
    """
    print(f"  ffmpeg scdet: threshold={threshold}")
    proc = run([
        ffmpeg(), "-hide_banner", "-i", str(video),
        "-vf", f"scdet=threshold={threshold}",
        "-fps_mode", "passthrough", "-f", "null", "-",
    ], quiet=True)
    times = [float(x) for x in re.findall(r"lavfi\.scd\.time:\s*([0-9]+(?:\.[0-9]+)?)", proc.stderr or "")]
    times = sorted({round(x, 3) for x in times if x >= 0})
    total = media_duration(video)
    bounds = [0.0] + [x for x in times if 0.2 < x < total - 0.2] + [total]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def merge_short(shots: list[tuple[float, float]], min_dur: float = 2.0) -> list[tuple[float, float]]:
    """<min_dur 的镜头并到后一个；末尾的并到前一个。"""
    if not shots:
        return shots
    merged: list[tuple[float, float]] = []
    pending: tuple[float, float] | None = None
    for start, end in shots:
        if end - start >= min_dur:
            if pending:
                merged.append((pending[0], end))
                pending = None
            else:
                merged.append((start, end))
        else:
            pending = (pending[0], end) if pending else (start, end)
    if pending:
        if merged:
            merged[-1] = (merged[-1][0], pending[1])
        else:
            merged.append(pending)
    return merged


# ---------------------------------------------------------------- 画面描述

_CAPTION_PROMPT = (
    "你是电影镜头标注员。用一句中文（不超过40字）描述这一帧：谁在画面里、"
    "在做什么、在什么场景、景别与光线氛围。不要评价剧情，不要写镜头参数。"
)


def _encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def caption_one(frame: Path, base_url: str, api_key: str, model: str) -> str:
    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _CAPTION_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": "data:image/jpeg;base64," + _encode_image(frame)
                }},
            ],
        }],
        "temperature": 0.2,
        "max_tokens": 120,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data["choices"][0]["message"]["content"] or "").strip().replace("\n", " ")


def add_captions(video: Path, shots: list[dict], out_dir: Path, model: str,
                 base_url: str, api_key: str, workers: int = 4) -> list[str]:
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    def grab(shot: dict) -> Path:
        f = frames_dir / f"shot_{shot['index']:04d}.jpg"
        if not f.exists():
            run([
                ffmpeg(), "-hide_banner", "-ss", f"{shot['mid']:.3f}", "-i", str(video),
                "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", "-y", str(f),
            ], quiet=True)
        return f

    def work(shot: dict) -> tuple[int, str]:
        try:
            return shot["index"], caption_one(grab(shot), base_url, api_key, model)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"shot {shot['index']} 描述失败：{exc}")
            return shot["index"], ""

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, s) for s in shots]
        done = 0
        for fut in as_completed(futures):
            idx, text = fut.result()
            shots[idx]["caption"] = text
            done += 1
            if done % 20 == 0:
                print(f"  描述 {done}/{len(shots)}")
    return warnings


# ---------------------------------------------------------------- 主流程

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="镜头检测 → shots.json")
    ap.add_argument("--work")
    ap.add_argument("--video", help="默认 <work>/原片.mp4")
    ap.add_argument("--out", help="默认 <build>/shots.json")
    ap.add_argument("--backend", choices=["auto", "pyscenedetect", "ffmpeg"], default="auto")
    ap.add_argument("--threshold", type=float, default=27.0,
                    help="pyscenedetect 的 ContentDetector 阈值（默认 27）")
    ap.add_argument("--scd-threshold", type=float, default=12.0,
                    help="ffmpeg scdet 的场景分数阈值 0~100（真实电影 10~15，静态素材 3~5）")
    ap.add_argument("--min-shot", type=float, default=2.0)
    ap.add_argument("--drop", type=float, default=0.4)
    ap.add_argument("--skip-intro", type=float, default=0.0,
                    help="开头多少秒视为片头，不参与匹配")
    ap.add_argument("--caption-backend", choices=["none", "openai"], default="none")
    ap.add_argument("--caption-model", default=os.environ.get("ALAN_VLM_MODEL", "gpt-4o-mini"))
    ap.add_argument("--caption-base-url", default=os.environ.get("ALAN_VLM_BASE_URL", ""))
    ap.add_argument("--caption-key", default=os.environ.get("ALAN_VLM_KEY", ""))
    ap.add_argument("--caption-workers", type=int, default=4)
    args = ap.parse_args(argv)

    work = Path(args.work).resolve() if args.work else None
    build = build_dir(work) if work else build_dir(".")
    video = Path(args.video) if args.video else (work / "原片.mp4" if work else None)
    if not video or not video.exists():
        raise SystemExit("找不到原片：用 --video 指定，或放到片目录下的 原片.mp4")

    total = media_duration(video)
    print(f"原片 {video.name} 时长 {total/60:.1f} 分钟")

    raw = None
    if args.backend in ("auto", "pyscenedetect"):
        raw = detect_pyscenedetect(video, args.threshold)
        if raw is None and args.backend == "pyscenedetect":
            raise SystemExit("pyscenedetect 不可用：pip install scenedetect[opencv]")
    if raw is None:
        raw = detect_ffmpeg(video, args.scd_threshold)

    shots_raw = merge_short(raw, args.min_shot)
    if any(e - s < args.min_shot for s, e in shots_raw):
        print("  [warn] 合并后仍有短镜，说明原片切换极快")

    records: list[dict] = []
    for start, end in shots_raw:
        dur = end - start
        if dur < args.drop:
            continue
        records.append({
            "index": len(records),
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(dur, 3),
            "mid": round((start + end) / 2, 3),
            "usable": start >= args.skip_intro,
            "caption": "",
        })

    if not records:
        raise SystemExit("没有检测到任何镜头，检查阈值或片源")

    warnings: list[str] = []
    if args.caption_backend == "openai":
        if not args.caption_base_url or not args.caption_key:
            warnings.append("未配置 ALAN_VLM_BASE_URL / ALAN_VLM_KEY，跳过画面描述")
        else:
            warnings += add_captions(video, records, build, args.caption_model,
                                     args.caption_base_url, args.caption_key,
                                     args.caption_workers)

    captioned = sum(1 for r in records if r["caption"])
    payload = {
        "video": str(video),
        "duration": round(total, 3),
        "backend": "pyscenedetect" if args.backend == "pyscenedetect" else "ffmpeg",
        "params": {
            "threshold": args.threshold, "scd_threshold": args.scd_threshold,
            "min_shot": args.min_shot, "drop": args.drop, "skip_intro": args.skip_intro,
        },
        "shots": records,
        "stats": {
            "count": len(records),
            "captioned": captioned,
            "avg_dur": round(sum(r["dur"] for r in records) / len(records), 2),
            "min_dur": round(min(r["dur"] for r in records), 2),
            "max_dur": round(max(r["dur"] for r in records), 2),
        },
        "warnings": warnings,
    }
    out = Path(args.out) if args.out else build / "shots.json"
    write_json(out, payload)

    print(f"镜头 {len(records)} 个 / 均 {payload['stats']['avg_dur']}s / 已描述 {captioned}")
    print(f"  shots : {out}")
    if args.skip_intro:
        skipped = sum(1 for r in records if not r["usable"])
        print(f"  片头过滤 {skipped} 个镜头（前 {args.skip_intro}s）")
    for w in warnings[:8]:
        print(f"  [warn] {w}")
    if not captioned:
        print("  提示：未生成画面描述，匹配层将退化为剧情时序先验（--caption-backend openai 可开）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
