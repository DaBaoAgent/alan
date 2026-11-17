# -*- coding: utf-8 -*-
"""Alan 出片流水线统一入口：稿 → 配音 → 对齐 → 镜头表 → EDL → 渲染。

    python scripts/edit/alan_edit.py init  --name 某片 --script 稿.txt --video 原片.mp4
    python scripts/edit/alan_edit.py voice --work "D:\\@kaifa\\Alan\\films\\某片" --backend peiyin
    python scripts/edit/alan_edit.py shots --work ... --caption-backend openai
    python scripts/edit/alan_edit.py all   --work ... --run

每一步都能单独重跑：中间产物全在 build/，上游没变就不必重算。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import (  # noqa: E402
        ALAN_ROOT, FILMS_DIR, build_dir, ensure_dir, read_json, write_json,
    )
    import read_script, voiceover, align_voice, shot_table, match_edl, render_edl, publish  # noqa: E402
else:
    from .common import (  # noqa: E402
        ALAN_ROOT, FILMS_DIR, build_dir, ensure_dir, read_json, write_json,
    )
    from . import read_script, voiceover, align_voice, shot_table, match_edl, render_edl, publish  # noqa: E402

STEP_ORDER = ("script", "voice", "align", "shots", "match", "render", "cover")


def _place(src: Path, dst: Path) -> str:
    """优先硬链接（同盘、瞬时、不占空间），跨盘则复制。"""
    if dst.exists():
        return "exists"
    try:
        os.link(src, dst)
        return "linked"
    except OSError:
        shutil.copy2(src, dst)
        return "copied"


def cmd_init(args) -> int:
    films = Path(args.films).resolve() if args.films else FILMS_DIR
    work = ensure_dir(films / args.name)
    build = build_dir(work)

    if args.script:
        script = Path(args.script).resolve()
        if not script.exists():
            raise SystemExit(f"找不到稿子：{script}")
        dst = work / "口播稿_定稿.txt"
        if dst.exists() and dst.resolve() != script:
            print(f"  [note] 已存在 {dst.name}，保留原文件，未覆盖")
        elif dst.resolve() != script:
            print(f"  稿子 {_place(script, dst)} → {dst.name}")

    if args.video:
        video = Path(args.video).resolve()
        if not video.exists():
            raise SystemExit(f"找不到原片：{video}")
        dst = work / "原片.mp4"
        if dst.exists():
            print(f"  [note] 已存在 原片.mp4，未覆盖")
        else:
            print(f"  原片 {_place(video, dst)} → {dst.name}")

    if args.audio:
        audio = Path(args.audio).resolve()
        if not audio.exists():
            raise SystemExit(f"找不到配音：{audio}")
        dst = work / "配音.wav"
        if not dst.exists():
            print(f"  配音 {_place(audio, dst)} → {dst.name}")

    write_json(work / "film.json", {
        "name": args.name,
        "script": str(work / "口播稿_定稿.txt"),
        "video": str(work / "原片.mp4"),
        "audio": str(work / "配音.wav"),
    })
    print(f"片目录就绪：{work}")
    print(f"  build : {build}")
    return 0


def _has(work: Path, name: str) -> bool:
    return (work / "build" / name).exists()


def cmd_status(args) -> int:
    work = Path(args.work).resolve()
    build = work / "build"
    print(f"片目录 {work}")
    for fn, desc in (
        ("segments.json", "读稿"),
        ("配音稿.txt", "TTS 稿"),
        ("voice.json", "配音"),
        ("timeline.json", "对齐"),
        ("subtitle.srt", "字幕"),
        ("shots.json", "镜头表"),
        ("edl.json", "EDL"),
        ("project.json", "渲染工程"),
        ("final.mp4", "成片"),
    ):
        p = build / fn if fn != "final.mp4" else work / fn
        if p.exists():
            size = p.stat().st_size
            print(f"  [ok]   {fn:<16} {size/1e6:8.2f} MB  {desc}")
        else:
            print(f"  [--]   {fn:<16} {'':8}     {desc}")
    for fn in ("口播稿_定稿.txt", "配音.wav", "原片.mp4"):
        p = work / fn
        if not p.exists():
            print(f"  [!]    根目录缺 {fn}")
    return 0


def run_all(args) -> int:
    work = Path(args.work).resolve()
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    for s in steps:
        if s not in STEP_ORDER:
            raise SystemExit(f"未知步骤 {s}，可选 {STEP_ORDER}")

    for step in steps:
        print(f"\n===== {step} =====")
        if step == "script":
            read_script.main(["--work", str(work)])
        elif step == "voice":
            if args.backend == "none" or ((work / "配音.wav").exists() and not args.force_voice):
                print(f"  已有配音，跳过合成（--force-voice 可重跑）" if (work / "配音.wav").exists() else "  backend=none，跳过")
            else:
                voiceover.main(["--work", str(work), "--backend", args.backend])
        elif step == "align":
            align_voice.main(["--work", str(work), "--backend", args.align_backend])
        elif step == "shots":
            if _has(work, "shots.json") and not args.force_shots:
                print("  已有 shots.json，跳过镜头检测（--force-shots 可重跑）")
            else:
                argv = ["--work", str(work), "--caption-backend", args.caption_backend]
                if args.skip_intro:
                    argv += ["--skip-intro", str(args.skip_intro)]
                shot_table.main(argv)
        elif step == "match":
            match_edl.main(["--work", str(work), "--scorer", args.scorer, "--aspect", args.aspect])
        elif step == "render":
            argv = ["--work", str(work), "--aspect", args.aspect, "--csv"]
            if args.run:
                argv.append("--run")
            render_edl.main(argv)
        elif step == "cover":
            publish.main(["--work", str(work)])
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    cmd, rest = argv[0], argv[1:]
    if cmd == "init":
        ap = argparse.ArgumentParser(prog="alan_edit init")
        ap.add_argument("--name", required=True)
        ap.add_argument("--script")
        ap.add_argument("--video")
        ap.add_argument("--audio")
        ap.add_argument("--films")
        return cmd_init(ap.parse_args(rest))
    if cmd == "status":
        ap = argparse.ArgumentParser(prog="alan_edit status")
        ap.add_argument("--work", required=True)
        return cmd_status(ap.parse_args(rest))

    # 其余子命令直接透传给对应脚本，参数保持单一来源
    if cmd == "script":
        return read_script.main(rest)
    if cmd == "voice":
        return voiceover.main(rest)
    if cmd == "align":
        return align_voice.main(rest)
    if cmd == "shots":
        return shot_table.main(rest)
    if cmd == "match":
        return match_edl.main(rest)
    if cmd == "render":
        return render_edl.main(rest)
    if cmd == "cover":
        return publish.main(rest)
    if cmd == "all":
        ap = argparse.ArgumentParser(prog="alan_edit all")
        ap.add_argument("--work", required=True)
        ap.add_argument("--steps", default="script,voice,align,shots,match,render,cover")
        ap.add_argument("--backend", choices=["peiyin", "alan", "none"], default="peiyin")
        ap.add_argument("--align-backend", choices=["auto", "whisperx", "faster", "rough"], default="auto")
        ap.add_argument("--caption-backend", choices=["none", "openai"], default="none")
        ap.add_argument("--scorer", choices=["auto", "embed", "keyword", "temporal"], default="auto")
        ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"])
        ap.add_argument("--skip-intro", type=float, default=0.0)
        ap.add_argument("--force-voice", action="store_true")
        ap.add_argument("--force-shots", action="store_true")
        ap.add_argument("--run", action="store_true")
        return run_all(ap.parse_args(rest))

    raise SystemExit(f"未知命令 {cmd}，可用：init/script/voice/align/shots/match/render/cover/all/status")


if __name__ == "__main__":
    raise SystemExit(main())
