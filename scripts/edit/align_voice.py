# -*- coding: utf-8 -*-
"""配音对齐：已有配音 wav → 每句起止时间 timeline.json。

和"字幕转录"的区别：
    字幕转录是"听写出文本"，允许错字；这里是"已知文稿对到音频"，要做的是
    forced alignment。所以主路径不是直接采信 ASR 文本，而是把 ASR 的词时间
    与稿子字符流做一次全局比对（SequenceMatcher），把每个稿子字符映射到音频时间。

后端优先级：
    whisperx  >  faster-whisper  >  rough（按字数比例切，标注 backend=rough）

rough 不是失败兜底的花架子：它能保证 EDL 结构完整、可先跑通镜头匹配，
但 ±0.5s 以上的漂移会让画面提前/滞后，正式出片必须用前两种。
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import (  # noqa: E402
        build_dir, media_duration, read_json, t_srt, write_json, write_text_utf8,
    )
else:
    from .common import (  # noqa: E402
        build_dir, media_duration, read_json, t_srt, write_json, write_text_utf8,
    )

_PUNCT = re.compile(r"[\s，。！？、；：,.!?;:…—\-（）()“”‘’\"'《》<>\[\]【】·]")


def norm_chars(text: str) -> list[str]:
    return [c for c in text if not _PUNCT.match(c)]


# ---------------------------------------------------------------- ASR

def transcribe_words(audio: Path, backend: str, model_size: str, lang: str,
                     device: str = "cpu") -> tuple[list[dict], str] | None:
    """返回 ([{word,start,end}], backend_name)；不可用时返回 None。"""
    if backend in ("auto", "faster"):
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:  # noqa: BLE001
            if backend == "faster":
                raise SystemExit(f"faster-whisper 不可用：{exc}")
        else:
            print(f"  faster-whisper: model={model_size} device={device}")
            model = WhisperModel(model_size, device=device, compute_type="int8")
            segments, _info = model.transcribe(
                str(audio), language=lang, word_timestamps=True, vad_filter=True,
            )
            words: list[dict] = []
            for seg in segments:
                for w in (seg.words or []):
                    words.append({"word": w.word, "start": float(w.start), "end": float(w.end)})
            if words:
                return words, f"faster-whisper:{model_size}"
            print("  [warn] faster-whisper 没有产出词时间，降级")

    if backend in ("auto", "whisperx"):
        try:
            import whisperx  # type: ignore
        except Exception as exc:  # noqa: BLE001
            if backend == "whisperx":
                raise SystemExit(f"whisperx 不可用：{exc}")
            return None
        print(f"  whisperx: model={model_size} device={device}")
        model = whisperx.load_model(model_size, device, compute_type="int8", language=lang)
        audio_data = whisperx.load_audio(str(audio))
        result = model.transcribe(audio_data, batch_size=8, language=lang)
        align_model, meta = whisperx.load_align_model(language_code=lang, device=device)
        aligned = whisperx.align(result["segments"], align_model, meta, audio_data, device)
        words = [
            {"word": w["word"], "start": float(w["start"]), "end": float(w["end"])}
            for seg in aligned["segments"] for w in seg.get("words", [])
            if w.get("start") is not None
        ]
        return (words, "whisperx") if words else None

    return None


# ---------------------------------------------------------------- 对齐

def align_by_chars(sentences: list[dict], words: list[dict]) -> tuple[list[dict], list[str]]:
    """稿子字符流 ↔ ASR 字符流全局比对，返回句级时间。"""
    warnings: list[str] = []

    # 稿：字符 + 所属句
    sc: list[str] = []
    sc_sent: list[int] = []
    for s in sentences:
        for c in norm_chars(s["text"]):
            sc.append(c)
            sc_sent.append(s["index"])
    if not sc:
        raise SystemExit("稿子规范化后为空")

    # ASR：字符 + 时间（词内按字符均分）
    ac: list[str] = []
    ac_t: list[tuple[float, float]] = []
    for w in words:
        wc = norm_chars(w["word"])
        if not wc:
            continue
        dur = max(0.0, w["end"] - w["start"])
        step = dur / len(wc)
        for k, c in enumerate(wc):
            ac.append(c)
            ac_t.append((w["start"] + step * k, w["start"] + step * (k + 1)))
    if not ac:
        raise SystemExit("ASR 没有产出可对齐字符")

    # 全局映射：稿索引 → ASR 索引
    mapping: list[int | None] = [None] * len(sc)
    sm = difflib.SequenceMatcher(None, sc, ac, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapping[i1 + k] = j1 + k
        elif tag == "replace":
            span_s = max(1, i2 - i1)
            span_a = max(1, j2 - j1)
            for k in range(span_s):
                mapping[i1 + k] = min(len(ac) - 1, j1 + int(round(k * span_a / span_s)))
        elif tag == "delete":
            for k in range(i1, i2):
                mapping[k] = min(len(ac) - 1, j1)
        # insert：ASR 多出来的字，跳过

    # 填充空洞
    last = 0
    for i in range(len(mapping)):
        if mapping[i] is None:
            mapping[i] = last
        last = mapping[i]  # type: ignore[assignment]

    # 句边界
    result: list[dict] = []
    cursor = 0
    for s in sentences:
        n = len(norm_chars(s["text"]))
        if n == 0:
            continue
        start_i = cursor
        end_i = min(len(sc) - 1, cursor + n - 1)
        a0 = mapping[start_i] or 0
        a1 = mapping[end_i] or a0
        start = ac_t[a0][0]
        end = ac_t[a1][1]
        if end <= start:
            end = start + max(0.4, n / 4.5)
        rate = n / max(0.01, end - start)
        if rate < 2.0 or rate > 7.5:
            warnings.append(f"句 {s['index']} 语速 {rate:.1f} 字/秒异常，疑似错位：{s['text'][:18]}")
        result.append({
            "index": s["index"], "para": s["para"], "text": s["text"],
            "chars": n, "start": round(start, 3), "end": round(end, 3),
            "dur": round(end - start, 3),
        })
        cursor += n

    # 单调性修正：允许极小回退，明显倒挂就顺延
    for i in range(1, len(result)):
        if result[i]["start"] < result[i - 1]["end"] - 0.05:
            shift = result[i - 1]["end"] - result[i]["start"]
            result[i]["start"] = round(result[i]["start"] + shift, 3)
            result[i]["end"] = round(max(result[i]["end"], result[i]["start"] + 0.3), 3)
            result[i]["dur"] = round(result[i]["end"] - result[i]["start"], 3)
            warnings.append(f"句 {result[i]['index']} 与上句重叠，顺延 {shift:.2f}s")
    return result, warnings


def align_rough(sentences: list[dict], duration: float, gap: float = 0.18) -> tuple[list[dict], list[str]]:
    """无 ASR 时按字数比例切分，句间留 gap。"""
    total_chars = sum(len(norm_chars(s["text"])) for s in sentences) or 1
    usable = max(1.0, duration - gap * max(0, len(sentences) - 1))
    result: list[dict] = []
    t = 0.0
    for s in sentences:
        n = len(norm_chars(s["text"]))
        d = usable * n / total_chars
        result.append({
            "index": s["index"], "para": s["para"], "text": s["text"], "chars": n,
            "start": round(t, 3), "end": round(t + d, 3), "dur": round(d, 3),
        })
        t += d + gap
    return result, ["backend=rough：按字数比例估算，画面会漂移，正式出片前必须换成 ASR 对齐"]


# ---------------------------------------------------------------- SRT

def to_srt(sentences: list[dict]) -> str:
    blocks = []
    for i, s in enumerate(sentences, start=1):
        blocks.append(
            f"{i}\n{t_srt(s['start'])} --> {t_srt(s['end'])}\n{s['text'].strip()}\n"
        )
    return "\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="配音对齐 → timeline.json")
    ap.add_argument("--work")
    ap.add_argument("--segments", help="默认 <build>/segments.json")
    ap.add_argument("--audio", help="默认 <work>/配音.wav")
    ap.add_argument("--out", help="默认 <build>/timeline.json")
    ap.add_argument("--backend", choices=["auto", "whisperx", "faster", "rough"], default="auto")
    ap.add_argument("--model", default="medium", help="ASR 模型，中文解说建议 medium 起")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    ap.add_argument("--gap", type=float, default=0.18, help="rough 模式的句间停顿")
    ap.add_argument("--srt", default=None, help="同时输出 SRT，默认 <build>/subtitle.srt；传 none 关闭")
    args = ap.parse_args(argv)

    work = Path(args.work).resolve() if args.work else None
    build = build_dir(work) if work else build_dir(".")
    seg_path = Path(args.segments) if args.segments else build / "segments.json"
    audio = Path(args.audio) if args.audio else (work / "配音.wav" if work else None)
    if not seg_path.exists():
        raise SystemExit(f"缺少 {seg_path}，先跑 read_script.py")
    if not audio or not audio.exists():
        raise SystemExit("找不到配音文件：用 --audio 指定，或放到片目录下的 配音.wav")

    sentences = read_json(seg_path)["sentences"]
    duration = media_duration(audio)
    print(f"配音时长 {duration:.2f}s，{len(sentences)} 句")

    words_info = None
    if args.backend != "rough":
        words_info = transcribe_words(audio, args.backend, args.model, args.lang, args.device)

    if words_info:
        words, backend_name = words_info
        timeline, warnings = align_by_chars(sentences, words)
    else:
        timeline, warnings = align_rough(sentences, duration, args.gap)
        backend_name = "rough"

    # 覆盖度检查
    covered = timeline[0]["start"] if timeline else 0.0
    tail = duration - (timeline[-1]["end"] if timeline else 0.0)
    if covered > 0.6:
        warnings.append(f"配音开头有 {covered:.1f}s 未覆盖（可能是片头空白或漏句）")
    if tail > 0.6:
        warnings.append(f"配音结尾有 {tail:.1f}s 未覆盖（可能是尾静音）")

    payload = {
        "audio": str(audio),
        "duration": round(duration, 3),
        "backend": backend_name,
        "sentences": timeline,
        "warnings": warnings,
    }
    out = Path(args.out) if args.out else build / "timeline.json"
    write_json(out, payload)

    srt_path = None
    if args.srt != "none":
        srt_path = Path(args.srt) if args.srt else build / "subtitle.srt"
        write_text_utf8(srt_path, to_srt(timeline))

    # 报告
    rates = [s["chars"] / max(0.01, s["dur"]) for s in timeline]
    print(f"对齐完成 backend={backend_name}")
    print(f"  语速  min={min(rates):.1f} avg={sum(rates)/len(rates):.1f} max={max(rates):.1f} 字/秒")
    print(f"  timeline : {out}")
    if srt_path:
        print(f"  subtitle : {srt_path}")
    for w in warnings[:12]:
        print(f"  [warn] {w}")
    if len(warnings) > 12:
        print(f"  ... 另有 {len(warnings)-12} 条警告见 timeline.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
