# -*- coding: utf-8 -*-
"""配音：把配音稿送去 PeiYin 的 dianying 管线（默认），或退回 Alan 本地 GPT-SoVITS。

两个后端：
    peiyin —— 直接调用 dianying 管线的 GPT-SoVITS\\dabao_tts.py
               音色/采样/停顿/发音修正全部由 voices/dabao/preset.json 锁定
               （v5turbo、speed 1.0、temp 0.9、top_p 0.9、top_k 20、rep 1.3、
                max_chunk_chars 150、fragment_interval 0.2、句间 100ms / 静音门 -33dB）
               合成前自动去掉外国人名之间的「·」，人名连读不拆句
               加 --paragraph-gap-ms N 则退回 PeiYin 的段落模式（每段单跑再拼，段间留 N ms）
    alan   —— scripts/synthesize_alan_cpu.py（本地 GPT-SoVITS，speed 1.0，
               呼吸消除 / 场景停顿按 references/voiceover-workflow.md）

为什么默认 PeiYin：Alan 只管内容与画面，音色工程（参考片段、停顿、呼吸门禁）
已经在 PeiYin 项目里成熟，重复维护一套没有收益。alan 后端留作离线/无 PeiYin 时的退路。

产物统一落到 <片目录>/配音.wav，后续 align_voice.py 不再关心是谁合成的。
"""

from __future__ import annotations

import argparse
import json
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
PEIYIN_ENGINE = PEIYIN_ROOT / "GPT-SoVITS" / "dabao_tts.py"
PEIYIN_PYTHON = PEIYIN_ROOT / "GPT-SoVITS" / ".venv" / "Scripts" / "python.exe"
PEIYIN_PRESET = PEIYIN_ROOT / "GPT-SoVITS" / "voices" / "dabao" / "preset.json"
PEIYIN_PARAGRAPH_SCRIPT = PEIYIN_ROOT / "scripts" / "synthesize_dabao_paragraphs.py"
PEIYIN_CHECK = PEIYIN_ROOT / "scripts" / "check_dabao_audio.ps1"


def read_preset(preset: Path) -> dict:
    """读 dabao preset，用于把实际生效参数写进 build/voice.json（读不到不妨碍合成）。"""
    try:
        return json.loads(preset.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def synth_peiyin(text_file: Path, out_wav: Path, args,
                 engine: Path, python: Path, check: Path,
                 paragraph_script: Path, preset: Path) -> dict:
    if not engine.exists():
        raise SystemExit(f"找不到 PeiYin 配音引擎：{engine}（可用 --peiyin-root 或环境变量 PEIYIN_ROOT 指定）")
    if not Path(python).exists():
        raise SystemExit(f"PeiYin 的 GPT-SoVITS 环境不存在：{python}")

    if args.paragraph_gap_ms > 0:
        # 段落模式：每段单独合成再拼，段间留固定停顿（长片分节呼吸感更好）
        if not paragraph_script.exists():
            raise SystemExit(f"找不到段落模式脚本：{paragraph_script}")
        cmd = [
            str(python), "-X", "utf8", str(paragraph_script),
            "--text-file", str(text_file),
            "--out", str(out_wav),
            "--paragraph-gap-ms", str(args.paragraph_gap_ms),
            "--keep-gap-ms", str(args.keep_gap_ms if args.keep_gap_ms is not None else 100),
            "--min-gap-ms", str(args.min_gap_ms if args.min_gap_ms is not None else 150),
        ]
        if args.keep_temp:
            cmd.append("--keep-temp")
        mode = "paragraphs"
    else:
        # dianying 管线直连：一次成片，语速/停顿全走 preset
        cmd = [
            str(python), "-X", "utf8", str(engine),
            "--text-file", str(text_file),
            "--out", str(out_wav),
            "--force",
        ]
        if args.keep_gap_ms is not None:
            cmd += ["--keep-gap-ms", str(args.keep_gap_ms)]
        if args.min_gap_ms is not None:
            cmd += ["--min-gap-ms", str(args.min_gap_ms)]
        if args.speed is not None:
            cmd += ["--speed", str(args.speed)]
        mode = "dianying"

    run(cmd, cwd=str(PEIYIN_ROOT), timeout=None)

    if args.check and check.exists():
        try:
            run(["pwsh", "-NoProfile", "-File", str(check), "-Wav", str(out_wav)],
                timeout=1800, quiet=True)
            print("  审查门禁 check_dabao_audio.ps1 通过")
        except RuntimeError as exc:
            print(f"  [warn] 审查门禁未通过：{exc}")

    cfg = read_preset(preset)
    synth = cfg.get("synthesis", {})
    post = cfg.get("postprocess", {})
    return {
        "engine": mode,
        "model": synth.get("model", "gpt-sovits-v5turbo"),
        "voice": (cfg.get("voice") or {}).get("id", "dabao"),
        "speed": synth.get("speed_factor", 1.0),
        "temperature": synth.get("temperature"),
        "top_p": synth.get("top_p"),
        "top_k": synth.get("top_k"),
        "repetition_penalty": synth.get("repetition_penalty"),
        "fragment_interval": synth.get("fragment_interval"),
        "max_chunk_chars": synth.get("max_chunk_chars"),
        "keep_gap_ms": post.get("keep_gap_ms"),
        "min_gap_ms": post.get("min_gap_ms"),
        "gate_db": post.get("gate_db"),
        "paragraph_gap_ms": args.paragraph_gap_ms,
        "name_dot_strip": True,
    }


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
    ap.add_argument("--paragraph-gap-ms", type=int, default=0,
                    help="0=直连 dianying 管线（默认，参数全走 preset）；>0=段落模式，段间留该毫秒数")
    ap.add_argument("--keep-gap-ms", type=int, default=None,
                    help="覆盖句间保留静音（默认用 preset 的 100ms）")
    ap.add_argument("--min-gap-ms", type=int, default=None,
                    help="覆盖可压缩静音判定（默认用 preset 的 150ms）")
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--check", action="store_true", help="PeiYin 后端跑审查门禁")
    ap.add_argument("--speed", type=float, default=None,
                    help="语速；peiyin 后端默认用 preset 的 1.0，语速请优先改 preset 而不是这里")
    ap.add_argument("--scene-ends", default="", help="alan 后端：剧情场景边界段落号，如 7,16,32")
    ap.add_argument("--scene-gap", type=float, default=None)
    args = ap.parse_args(argv)

    root = Path(args.peiyin_root).resolve() if args.peiyin_root else PEIYIN_ROOT
    peiyin_engine = root / "GPT-SoVITS" / "dabao_tts.py"
    peiyin_python = Path(args.peiyin_python) if args.peiyin_python else (
        root / "GPT-SoVITS" / ".venv" / "Scripts" / "python.exe")
    peiyin_check = root / "scripts" / "check_dabao_audio.ps1"
    peiyin_paragraph_script = root / "scripts" / "synthesize_dabao_paragraphs.py"
    peiyin_preset = root / "GPT-SoVITS" / "voices" / "dabao" / "preset.json"

    work = Path(args.work).resolve() if args.work else None
    if not work:
        raise SystemExit("配音需要 --work（片目录）")
    build = build_dir(work)
    text = Path(args.text) if args.text else build / "配音稿.txt"
    out_wav = Path(args.out) if args.out else work / "配音.wav"
    name = args.name or work.name

    peiyin_info: dict = {}
    if args.backend != "none":
        if not text.exists():
            raise SystemExit(f"缺少配音稿 {text}：先跑 read_script.py")
        if args.backend == "peiyin":
            mode = "段落模式" if args.paragraph_gap_ms > 0 else "dianying 管线直连"
            print(f"PeiYin 合成（{mode}）：{text.name} → {out_wav.name}")
            peiyin_info = synth_peiyin(
                text, out_wav, args, peiyin_engine, peiyin_python, peiyin_check,
                peiyin_paragraph_script, peiyin_preset)
        else:
            print(f"Alan 本地合成：{text.name} → {out_wav.name}")
            synth_alan(text, out_wav, work, name, args)

    if not out_wav.exists():
        raise SystemExit(f"没有配音文件 {out_wav}")

    # PeiYin 会在 wav 旁写一份同名 json（分段/参数元数据），挪进 build，别脏了片目录根
    side = out_wav.with_suffix(".json")
    if side.exists():
        shutil.move(str(side), str(build_dir(work) / "voice_peiyin.json"))

    dur = media_duration(out_wav)
    params = peiyin_info or {"speed": args.speed, "paragraph_gap_ms": args.paragraph_gap_ms}
    info = {
        "backend": args.backend,
        "audio": str(out_wav),
        "duration": round(dur, 3),
        "text": str(text),
        "params": params,
    }
    write_json(build / "voice.json", info)
    print(f"配音就绪：{out_wav}（{dur:.1f}s / {dur/60:.2f} 分钟）")
    if dur / 60 < 3:
        print("  [warn] 不足 3 分钟，Alan 成片通常 8~15 分钟，检查是否漏段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
