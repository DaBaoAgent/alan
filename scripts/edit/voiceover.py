# -*- coding: utf-8 -*-
"""配音：把配音稿送去外部 PeiYin 项目（默认），或退回 Alan 本地 GPT-SoVITS。

两个后端：
    peiyin —— D:\\@kaifa\\PeiYin\\scripts\\synthesize_dabao_paragraphs.py
               dabao 克隆音色 + 段落拼接，参数见其 argparse（默认段间 200ms）
    alan   —— scripts/synthesize_alan_cpu.py（本地 GPT-SoVITS，speed 1.0，
               呼吸消除 / 场景停顿按 references/voiceover-workflow.md）

为什么默认 PeiYin：Alan 只管内容与画面，音色工程（参考片段、停顿、呼吸门禁）
已经在 PeiYin 项目里成熟，重复维护一套没有收益。alan 后端留作离线/无 PeiYin 时的退路。

产物统一落到 <片目录>/配音.wav，后续 align_voice.py 不再关心是谁合成的。
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
        ALAN_ROOT, SCRIPTS_DIR, build_dir, media_duration, run, write_json,
    )
else:
    from .common import (  # noqa: E402
        ALAN_ROOT, SCRIPTS_DIR, build_dir, media_duration, run, write_json,
    )

PEIYIN_ROOT = Path(os.environ.get("PEIYIN_ROOT", r"D:\@kaifa\PeiYin"))
PEIYIN_SCRIPT = PEIYIN_ROOT / "scripts" / "synthesize_dabao_paragraphs.py"
PEIYIN_PYTHON = PEIYIN_ROOT / "GPT-SoVITS" / ".venv" / "Scripts" / "python.exe"
PEIYIN_CHECK = PEIYIN_ROOT / "scripts" / "check_dabao_audio.ps1"


def synth_peiyin(text_file: Path, out_wav: Path, args,
                 script: Path, python: Path, check: Path) -> None:
    if not script.exists():
        raise SystemExit(f"找不到 PeiYin：{script}（可用 --peiyin-root 或环境变量 PEIYIN_ROOT 指定）")
    if not Path(python).exists():
        raise SystemExit(f"PeiYin 的 GPT-SoVITS 环境不存在：{python}")

    cmd = [
        str(python), str(script),
        "--text-file", str(text_file),
        "--out", str(out_wav),
        "--paragraph-gap-ms", str(args.paragraph_gap_ms),
        "--keep-gap-ms", str(args.keep_gap_ms),
        "--min-gap-ms", str(args.min_gap_ms),
    ]
    if args.keep_temp:
        cmd.append("--keep-temp")
    run(cmd, cwd=str(PEIYIN_ROOT), timeout=None)

    if args.check and check.exists():
        try:
            run(["pwsh", "-NoProfile", "-File", str(check), "-Wav", str(out_wav)],
                timeout=1800, quiet=True)
            print("  审查门禁 check_dabao_audio.ps1 通过")
        except RuntimeError as exc:
            print(f"  [warn] 审查门禁未通过：{exc}")


def synth_alan(text_file: Path, out_wav: Path, work: Path, name: str, args) -> None:
    script = SCRIPTS_DIR / "synthesize_alan_cpu.py"
    if not script.exists():
        raise SystemExit(f"找不到 {script}")
    out_dir = build_dir(work) / "alan_tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(script),
        "--text", str(text_file),
        "--name", name,
        "--output-dir", str(out_dir),
        "--speed", str(args.speed),
    ]
    if args.scene_ends:
        cmd += ["--scene-ends", args.scene_ends]
    if args.scene_gap is not None:
        cmd += ["--scene-gap", str(args.scene_gap)]
    run(cmd, cwd=str(ALAN_ROOT), timeout=None)

    wavs = sorted(out_dir.rglob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not wavs:
        raise SystemExit(f"{out_dir} 下没有生成 wav")
    shutil.copy2(wavs[0], out_wav)
    print(f"  取最新段落合成结果：{wavs[0].name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="配音：PeiYin / Alan 本地")
    ap.add_argument("--work")
    ap.add_argument("--backend", choices=["peiyin", "alan", "none"], default="peiyin")
    ap.add_argument("--text", help="默认 <build>/配音稿.txt")
    ap.add_argument("--out", help="默认 <work>/配音.wav")
    ap.add_argument("--name", default=None)
    ap.add_argument("--peiyin-root", default=str(PEIYIN_ROOT))
    ap.add_argument("--peiyin-python", default=None)
    ap.add_argument("--paragraph-gap-ms", type=int, default=200)
    ap.add_argument("--keep-gap-ms", type=int, default=80)
    ap.add_argument("--min-gap-ms", type=int, default=150)
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--check", action="store_true", help="PeiYin 后端跑审查门禁")
    ap.add_argument("--speed", type=float, default=1.0, help="alan 后端语速")
    ap.add_argument("--scene-ends", default="", help="alan 后端：剧情场景边界段落号，如 7,16,32")
    ap.add_argument("--scene-gap", type=float, default=None)
    args = ap.parse_args(argv)

    root = Path(args.peiyin_root).resolve() if args.peiyin_root else PEIYIN_ROOT
    peiyin_script = root / "scripts" / "synthesize_dabao_paragraphs.py"
    peiyin_python = Path(args.peiyin_python) if args.peiyin_python else (
        root / "GPT-SoVITS" / ".venv" / "Scripts" / "python.exe")
    peiyin_check = root / "scripts" / "check_dabao_audio.ps1"

    work = Path(args.work).resolve() if args.work else None
    if not work:
        raise SystemExit("配音需要 --work（片目录）")
    build = build_dir(work)
    text = Path(args.text) if args.text else build / "配音稿.txt"
    out_wav = Path(args.out) if args.out else work / "配音.wav"
    name = args.name or work.name

    if args.backend != "none":
        if not text.exists():
            raise SystemExit(f"缺少配音稿 {text}：先跑 read_script.py")
        if args.backend == "peiyin":
            print(f"PeiYin 合成：{text.name} → {out_wav.name}")
            synth_peiyin(text, out_wav, args, peiyin_script, peiyin_python, peiyin_check)
        else:
            print(f"Alan 本地合成：{text.name} → {out_wav.name}")
            synth_alan(text, out_wav, work, name, args)

    if not out_wav.exists():
        raise SystemExit(f"没有配音文件 {out_wav}")

    # PeiYin 会在 wav 旁写一份同名 json（段落/质检元数据），挪进 build，别脏了片目录根
    side = out_wav.with_suffix(".json")
    if side.exists():
        shutil.move(str(side), str(build_dir(work) / "voice_peiyin.json"))

    dur = media_duration(out_wav)
    info = {
        "backend": args.backend,
        "audio": str(out_wav),
        "duration": round(dur, 3),
        "text": str(text),
        "params": {
            "paragraph_gap_ms": args.paragraph_gap_ms,
            "speed": args.speed,
        },
    }
    write_json(build / "voice.json", info)
    print(f"配音就绪：{out_wav}（{dur:.1f}s / {dur/60:.2f} 分钟）")
    if dur / 60 < 3:
        print("  [warn] 不足 3 分钟，Alan 成片通常 8~15 分钟，检查是否漏段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
