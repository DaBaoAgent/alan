#!/usr/bin/env python3
"""Alan 解说配音：GPT-SoVITS CPU 克隆音色合成（艾伦音色）。

流程：读稿 → 精修参考音色（自动裁剪/单声道/32k）→ cut0 大段落推理 →
句间停顿压缩 → 拼接成品。默认语速 1.0（2026-09-12 用户定版）。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

DEFAULT_ROOT = Path(r"D:\@佳康顺矩阵\@工具\GPT-SoVITS")
# 参考音色源（2026-09-12 用户定版）：原始 14.1s 44.1k 立体声 WAV
DEFAULT_REFERENCE = Path(r"D:\BaiduSyncdisk\18 艾伦全自动解说\克隆音色\dabao3.wav")
# 干净参考片段范围：silencedetect 实测 6.48-13.96s 为连续无停顿语音，起止各留缓冲
DEFAULT_REF_START = 6.45
DEFAULT_REF_END = 13.98
# 与该片段逐字匹配的提示文本（用户亲笔转写，勿改；ASR 转写不能当准）
DEFAULT_PROMPT = "准备迎接最大挑战，理论上斯大林仍是希特勒的盟友，罗马尼亚、保加利亚和匈牙利是德国的坚定盟友。"
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*]')


def safe_name(value: str) -> str:
    cleaned = INVALID_WINDOWS_CHARS.sub("_", value).strip(" .")
    return cleaned or "艾伦配音"


def split_long_paragraph(paragraph: str, max_chars: int = 240) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?；;])", paragraph) if item.strip()]
    if len(sentences) == 1:
        return [paragraph[i : i + max_chars] for i in range(0, len(paragraph), max_chars)]
    result: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            result.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        result.append(current)
    return result


def load_paragraphs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    source = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    paragraphs: list[str] = []
    for paragraph in source:
        normalized = re.sub(r"\s*\n\s*", "", paragraph)
        paragraphs.extend(split_long_paragraph(normalized))
    return paragraphs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CPU-only Alan narration with the cloned dabao3 voice.")
    parser.add_argument("--text", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Working-files dir (RAW/segments); defaults to 配音 beside the text. Also receives the final WAV when set.",
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--gpt-sovits-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--prompt-text", default=DEFAULT_PROMPT)
    parser.add_argument("--ref-start", type=float, default=DEFAULT_REF_START,
                        help="参考片段起点秒；传入已裁剪片段且时长短于 ref-end 时自动整段使用")
    parser.add_argument("--ref-end", type=float, default=DEFAULT_REF_END,
                        help="参考片段终点秒；None=整段")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--seed-base", type=int, default=20260912)
    parser.add_argument("--threads", type=int, default=min(os.cpu_count() or 1, 16))
    parser.add_argument("--silence-threshold-db", type=float, default=-46.0,
                        help="首尾修剪用的静音阈值")
    parser.add_argument("--breath-threshold-db", type=float, default=-40.0,
                        help="语句边界检测阈值;低于它的间隙内容视为呼吸/静音")
    parser.add_argument("--min-speech-sec", type=float, default=0.10)
    parser.add_argument("--merge-gap-sec", type=float, default=0.08,
                        help="小于此秒数的能量凹陷并入当前语句(保护爆破音闭合期不被切洞)")
    parser.add_argument("--min-long-pause", type=float, default=0.05,
                        help="≥此秒数的语句间隙整段替换为纯静音(呼吸消除);更短的词内停顿原样保留")
    parser.add_argument("--target-pause", type=float, default=0.18)
    parser.add_argument("--paragraph-gap", type=float, default=1.0,
                        help="自然段落之间静音秒数(2026-09-12 用户定版 1.0)")
    return parser


def prepare_reference(reference: Path, work_dir: Path, ref_start: float | None, ref_end: float | None, log) -> Path:
    """把参考音频精修为 32k/单声道/PCM16 片段；已是精修片段（时长<=ref_end）则原样通过。"""
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    audio, sr = sf.read(str(reference), always_2d=True, dtype="float32")
    duration = len(audio) / sr
    if ref_start is None and ref_end is None:
        start, end = 0.0, duration
    elif duration <= (ref_end or duration):
        # 文件本身不比请求的片段长 → 已经是裁剪过的片段，整段使用
        start, end = 0.0, duration
    else:
        start = 0.0 if ref_start is None else max(0.0, ref_start)
        end = duration if ref_end is None else min(duration, ref_end)
    if start >= end:
        raise SystemExit(f"Invalid reference clip range [{start}, {end}] for {reference}")
    segment = audio[int(start * sr) : int(end * sr)]
    mono = segment.mean(axis=1) if segment.shape[1] > 1 else segment[:, 0]
    if sr != 32000:
        divisor = math.gcd(sr, 32000)
        mono = resample_poly(mono, 32000 // divisor, sr // divisor)
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    if peak >= 1.0:
        raise SystemExit(f"Reference clip peak {peak:.3f} >= 1.0; select a cleaner segment")
    pcm = np.clip(mono * 32767.0, -32768.0, 32767.0).astype(np.int16)
    out = work_dir / "alan_ref_32k.wav"
    sf.write(str(out), pcm, 32000, subtype="PCM_16")
    log(
        f"Reference prepared: {reference.name} [{start:.2f}-{end:.2f}s/{duration:.2f}s] "
        f"-> {out.name} {len(pcm) / 32000:.2f}s peak={peak:.3f}"
    )
    return out


def main() -> int:
    args = build_parser().parse_args()
    root = args.gpt_sovits_root.resolve()
    text_path = args.text.resolve()
    output_dir = (args.output_dir or (text_path.parent / "配音")).resolve()
    final_dir = (args.output_dir or text_path.parent).resolve()
    reference = args.reference.resolve()
    if not root.is_dir():
        raise SystemExit(f"GPT-SoVITS root does not exist: {root}")
    if not text_path.is_file():
        raise SystemExit(f"Narration text does not exist: {text_path}")
    if not reference.is_file():
        raise SystemExit(f"Reference audio does not exist: {reference}")
    if args.speed <= 0:
        raise SystemExit("--speed must be positive")
    if args.target_pause <= 0:
        raise SystemExit("--target-pause must be positive")

    os.chdir(root)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "GPT_SoVITS"))

    import numpy as np
    import soundfile as sf
    import torch
    from scipy.ndimage import uniform_filter1d

    from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

    output_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = output_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "progress.log"
    progress_path.write_text("", encoding="utf-8")
    topic = safe_name(args.name)
    raw_path = output_dir / f"{topic}_艾伦音色_CPU_大段落_{args.speed:.1f}倍速_RAW.wav"
    final_path = final_dir / f"{topic}_艾伦音色_CPU_大段落_{args.speed:.1f}倍速_句间停顿缩短.wav"

    def log(message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line, flush=True)
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    reference_clip = prepare_reference(reference, output_dir, args.ref_start, args.ref_end, log)

    def silence_envelope(audio_pcm16: np.ndarray, sample_rate: int) -> np.ndarray:
        data = audio_pcm16.astype(np.float32) / 32768.0
        window = max(1, int(sample_rate * 0.015))
        return np.sqrt(uniform_filter1d(data * data, size=window))

    def speech_boundaries(audio: np.ndarray, sample_rate: int, threshold_db: float,
                          min_speech_sec: float, merge_gap_sec: float) -> list[tuple[int, int]]:
        """按能量阈值切出语句区,合并近邻;返回 [(start_sample, end_sample), ...]。"""
        envelope = silence_envelope(audio, sample_rate)
        mask = envelope >= 10 ** (threshold_db / 20)
        changes = np.diff(np.r_[False, mask, False].astype(np.int8))
        starts = np.where(changes == 1)[0]
        ends = np.where(changes == -1)[0]
        # 合并被 <merge_gap_sec 间隙隔开的语句区(呼吸尾/头不拆成两句)
        merged: list[list[int]] = []
        min_speech = int(min_speech_sec * sample_rate)
        merge_gap = int(merge_gap_sec * sample_rate)
        for start, end in zip(starts, ends):
            if end - start < min_speech:
                continue
            if merged and start - merged[-1][1] < merge_gap:
                merged[-1][1] = end
            else:
                merged.append([start, end])
        return [(start, end) for start, end in merged]

    def remove_breaths(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int, float]:
        """句间间隙处理:≥min_long_pause 的间隙整段替换为 target_pause 纯静音(消除呼吸),
        更短的气口原样保留;首尾按 silence-threshold 修剪。"""
        bounds = speech_boundaries(
            audio, sample_rate, args.breath_threshold_db,
            args.min_speech_sec, args.merge_gap_sec,
        )
        if not bounds:
            return audio, 0, 0.0
        target_samples = int(args.target_pause * sample_rate)
        gap = int(args.min_long_pause * sample_rate)
        pieces: list[np.ndarray] = []
        replaced = 0
        removed_samples = 0
        first_start, _ = bounds[0]
        pieces.append(audio[max(0, first_start - int(0.04 * sample_rate)) : bounds[0][0]])
        fade = max(1, int(0.005 * sample_rate))
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float64)
        for index, (start, end) in enumerate(bounds):
            piece = audio[start:end].astype(np.float64)
            piece[:fade] *= ramp
            piece[-fade:] *= ramp[::-1]
            pieces.append(piece.astype(np.int16))
            if index < len(bounds) - 1:
                next_start = bounds[index + 1][0]
                if next_start - end >= gap:
                    pieces.append(np.zeros(target_samples, dtype=np.int16))
                    removed_samples += next_start - end - target_samples
                    replaced += 1
                else:
                    pieces.append(audio[end:next_start])
        _, last_end = bounds[-1]
        pieces.append(audio[last_end : last_end + int(0.08 * sample_rate)])
        result = np.concatenate(pieces)
        return result, replaced, removed_samples / sample_rate

    paragraphs = load_paragraphs(text_path)
    if not paragraphs:
        raise SystemExit("Narration text contains no paragraphs")
    normalized_path = output_dir / "配音稿_大段落.txt"
    normalized_path.write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")
    config_record = {
        "text": str(text_path),
        "normalized_text": str(normalized_path),
        "reference": str(reference),
        "reference_clip": str(reference_clip),
        "ref_start_sec": args.ref_start,
        "ref_end_sec": args.ref_end,
        "prompt_text": args.prompt_text,
        "cpu_only": True,
        "speed_factor": args.speed,
        "text_split_method": "cut0",
        "paragraph_count": len(paragraphs),
        "silence_threshold_db": args.silence_threshold_db,
        "breath_threshold_db": args.breath_threshold_db,
        "min_speech_sec": args.min_speech_sec,
        "merge_gap_sec": args.merge_gap_sec,
        "min_long_pause_sec": args.min_long_pause,
        "target_pause_sec": args.target_pause,
        "paragraph_gap_sec": args.paragraph_gap,
        "breath_removal": "replace_gap_with_silence",
        "tone_beautification": False,
    }
    (output_dir / "配音配置.json").write_text(
        json.dumps(config_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    threads = max(1, min(args.threads, os.cpu_count() or 1))
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(max(1, min(4, threads)))
    log(f"CPU-only; speed={args.speed:.2f}; no tone post-processing; threads={threads}")
    log(f"Loaded {len(paragraphs)} paragraphs; lengths={[len(p) for p in paragraphs]}")

    config = TTS_Config(str(root / "GPT_SoVITS" / "configs" / "tts_infer.yaml"))
    if str(config.device) != "cpu":
        raise RuntimeError(f"Expected CPU config, got {config.device}")
    pipeline = TTS(config)
    log(f"Models loaded on {config.device}; version={config.version}")

    raw_paragraphs: list[np.ndarray] = []
    processed_paragraphs: list[np.ndarray] = []
    sample_rate = 0
    total_shortened = 0
    total_removed = 0.0
    started = time.time()
    for index, paragraph in enumerate(paragraphs, start=1):
        log(f"Paragraph {index}/{len(paragraphs)} synthesis started ({len(paragraph)} characters)")
        request = {
            "text": paragraph,
            "text_lang": "zh",
            "ref_audio_path": str(reference_clip),
            "prompt_lang": "zh",
            "prompt_text": args.prompt_text,
            "top_k": 15,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut0",
            "batch_size": 1,
            "batch_threshold": 0.75,
            "split_bucket": False,
            "speed_factor": args.speed,
            "fragment_interval": 0.10,
            "seed": args.seed_base + index,
            "parallel_infer": False,
            "repetition_penalty": 1.35,
            "return_fragment": False,
            "streaming_mode": False,
        }
        current_rate, audio = next(pipeline.run(request))
        if sample_rate == 0:
            sample_rate = current_rate
        elif sample_rate != current_rate:
            raise RuntimeError("Sample rate mismatch")
        audio = np.asarray(audio)
        if not np.issubdtype(audio.dtype, np.integer):
            raise RuntimeError(f"Expected PCM integer output, got {audio.dtype}")

        sf.write(segments_dir / f"paragraph_{index:02d}_raw.wav", audio, sample_rate, subtype="PCM_16")
        raw_paragraphs.append(audio)
        processed, changed, removed = remove_breaths(audio, sample_rate)
        sf.write(
            segments_dir / f"paragraph_{index:02d}_processed.wav",
            processed,
            sample_rate,
            subtype="PCM_16",
        )
        processed_paragraphs.append(processed)
        total_shortened += changed
        total_removed += removed
        log(
            f"Paragraph {index}/{len(paragraphs)} completed; raw={len(audio) / sample_rate:.1f}s; "
            f"final={len(processed) / sample_rate:.1f}s; shortened={changed}; "
            f"elapsed={(time.time() - started) / 60:.1f}min"
        )

    raw_gap = np.zeros(int(0.26 * sample_rate), dtype=np.int16)
    final_gap = np.zeros(int(args.paragraph_gap * sample_rate), dtype=np.int16)
    raw_pieces: list[np.ndarray] = []
    final_pieces: list[np.ndarray] = []
    for index in range(len(paragraphs)):
        raw_pieces.append(raw_paragraphs[index])
        final_pieces.append(processed_paragraphs[index])
        if index < len(paragraphs) - 1:
            raw_pieces.append(raw_gap)
            final_pieces.append(final_gap)

    raw_audio = np.concatenate(raw_pieces)
    final_audio = np.concatenate(final_pieces)
    sf.write(raw_path, raw_audio, sample_rate, subtype="PCM_16")
    sf.write(final_path, final_audio, sample_rate, subtype="PCM_16")
    meter = final_audio.astype(np.float32) / 32768.0
    clipped = int(np.sum(np.abs(final_audio) >= 32767))
    log(
        f"FINAL completed; shortened={total_shortened}; removed={total_removed:.1f}s; "
        f"duration={len(final_audio) / sample_rate:.1f}s; peak={np.max(np.abs(meter)):.3f}; "
        f"clipped_samples={clipped}; path={final_path}"
    )
    if sample_rate != 32000 or final_audio.ndim != 1 or clipped != 0:
        raise RuntimeError("Final audio failed deterministic quality checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
