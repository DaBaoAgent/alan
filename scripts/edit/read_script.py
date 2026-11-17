# -*- coding: utf-8 -*-
"""读稿：口播稿 → 句级 segments.json + 可直接送 TTS 的配音稿。

为什么句级是单位：
    匹配层要把"一句解说"对上"1~3 个镜头"，配音虽然有整条 wav，但句边界才是
    语义与画面对齐的最小刻度。段只用于 TTS 分段（GPT-SoVITS 长段会截断）。

用法：
    python scripts/edit/read_script.py --work D:\\@kaifa\\Alan\\films\\某片
    python scripts/edit/read_script.py --script 稿.txt --name 某片 --out 目录
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if not __package__:  # 允许直接 python 运行
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import (  # noqa: E402
        build_dir, char_count, clean_lines, read_text_any, split_sentences,
        write_json, write_text_utf8, ALAN_ROOT,
    )
else:
    from .common import (  # noqa: E402
        build_dir, char_count, clean_lines, read_text_any, split_sentences,
        write_json, write_text_utf8, ALAN_ROOT,
    )


DEFAULT_SCRIPT_NAMES = ("口播稿_定稿.txt", "口播稿_定稿.md", "配音稿.txt", "口播稿.txt")


def find_script(work: Path) -> Path | None:
    for name in DEFAULT_SCRIPT_NAMES:
        p = work / name
        if p.exists():
            return p
    return None


def build_voice_text(sentences: list[dict], max_chars: int = 120) -> str:
    """把句子合成 TTS 段落：≤max_chars 字、2~4 句一段，段间空行。

    PeiYin 的 synthesize_dabao_paragraphs.py 按空行切段，段落过长会被引擎截断，
    过短则语气断裂。120 字 / 2~4 句是实测比较稳的区间。
    """
    paras: list[list[dict]] = []
    cur: list[dict] = []
    cur_chars = 0
    for s in sentences:
        if cur and (cur_chars + s["chars"] > max_chars or len(cur) >= 4):
            paras.append(cur)
            cur, cur_chars = [], 0
        cur.append(s)
        cur_chars += s["chars"]
    if cur:
        paras.append(cur)
    return "\n\n".join("".join(s["text"] for s in p) for p in paras) + "\n"


def parse_script(text: str, chars_per_sec: float = 4.5) -> tuple[list[dict], list[dict]]:
    lines = clean_lines(text)
    sentences: list[dict] = []
    paragraphs: list[dict] = []

    # 段落：原稿有连续行则视为同段；每段再切句
    for line_no, line in enumerate(lines, start=1):
        para_sents: list[int] = []
        for piece in split_sentences(line):
            chars = char_count(piece)
            if chars < 2:  # "好。" "是啊。" 单独成句在解说里不成立，丢弃
                continue
            idx = len(sentences)
            sentences.append({
                "index": idx,
                "para": len(paragraphs),
                "line": line_no,
                "text": piece,
                "chars": chars,
                "est_sec": round(max(0.8, chars / chars_per_sec), 2),
            })
            para_sents.append(idx)
        if para_sents:
            paragraphs.append({
                "index": len(paragraphs),
                "sentences": para_sents,
                "text": "".join(sentences[i]["text"] for i in para_sents),
            })
    return sentences, paragraphs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="读口播稿 → segments.json")
    ap.add_argument("--work", help="片目录（默认读其下 口播稿_定稿.txt）")
    ap.add_argument("--script", help="显式指定口播稿路径")
    ap.add_argument("--name", help="片名，默认取目录名")
    ap.add_argument("--out", help="输出目录，默认 <work>/build")
    ap.add_argument("--chars-per-sec", type=float, default=4.5,
                    help="仅用于预估总时长，实际以配音对齐为准（默认 4.5 字/秒）")
    ap.add_argument("--voice-text", default=None,
                    help="配音稿输出路径，默认 <build>/配音稿.txt；传 none 则不生成")
    args = ap.parse_args(argv)

    work = Path(args.work).resolve() if args.work else None
    script = Path(args.script).resolve() if args.script else (find_script(work) if work else None)
    if not script or not script.exists():
        raise SystemExit("找不到口播稿：请用 --script 指定，或放到片目录下的 口播稿_定稿.txt")

    text = read_text_any(script)
    sentences, paragraphs = parse_script(text, args.chars_per_sec)
    if not sentences:
        raise SystemExit("稿子里没有解析出任何句子，检查是否全是结构行")

    name = args.name or (work.name if work else script.stem)
    out_dir = Path(args.out).resolve() if args.out else build_dir(work or script.parent)

    total_chars = sum(s["chars"] for s in sentences)
    est_total = round(sum(s["est_sec"] for s in sentences), 2)

    payload = {
        "name": name,
        "script": str(script),
        "chars": total_chars,
        "sentences": sentences,
        "paragraphs": paragraphs,
        "est_total_sec": est_total,
    }
    seg_path = write_json(out_dir / "segments.json", payload)

    voice_path = None
    if args.voice_text != "none":
        voice_path = Path(args.voice_text) if args.voice_text else out_dir / "配音稿.txt"
        write_text_utf8(voice_path, build_voice_text(sentences))

    print(f"读稿完成：{len(sentences)} 句 / {len(paragraphs)} 段 / {total_chars} 字 / 预估 {est_total:.1f}s")
    print(f"  segments : {seg_path}")
    if voice_path:
        print(f"  配音稿   : {voice_path}")
    if total_chars < 800:
        print("  [warn] 字数偏少，检查是否误把结构行当正文清了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
