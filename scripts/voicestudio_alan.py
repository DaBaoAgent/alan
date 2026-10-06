#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VoiceStudio adapter for Alan movie-commentary narration.

The adapter uses VoiceStudio's local API only.  It never copies a voice
reference into this repository or stores a local VoiceStudio profile ID in
source control.  Create a profile once, then pass its ID when synthesizing.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:3900/v1"
DEFAULT_REFERENCE = Path(r"D:\BaiduSyncdisk\4 @数字人剪辑\大宝Agent\大宝1.1.mp3")
DEFAULT_INSTRUCT = "沉稳自然的中文男性电影解说，口语化、清晰、有悬疑张力；不要播音腔，不要夸张情绪。"


def fail(message: str) -> None:
    raise SystemExit(message)


def command(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        fail(f"缺少 {name}，请先安装并加入 PATH。")
    return executable


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, encoding="utf-8", errors="replace")


def api_url(base_url: str, route: str) -> str:
    return f"{base_url.rstrip('/')}/{route.lstrip('/')}"


def health(base_url: str) -> dict:
    parsed = urllib.parse.urlsplit(base_url)
    root_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    try:
        response = requests.get(f"{root_url}/health", timeout=5)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        fail("VoiceStudio 未运行。请先启动桌面应用，再重试。")


def audio_probe(path: Path) -> dict:
    probe = run([
        command("ffprobe"), "-v", "error", "-show_entries",
        "format=duration:stream=codec_name,sample_rate,channels", "-of", "json", str(path),
    ])
    return json.loads(probe.stdout)


def audio_peak_db(path: Path) -> float | None:
    result = subprocess.run(
        [command("ffmpeg"), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "NUL"],
        text=True, capture_output=True, encoding="utf-8", errors="replace",
    )
    match = re.search(r"max_volume:\s*(-?[\d.]+) dB", result.stderr)
    return float(match.group(1)) if match else None


def prepare_reference(source: Path, output: Path, clean: bool) -> dict:
    if not source.is_file():
        fail(f"找不到参考音频: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = "highpass=f=70,lowpass=f=12000,loudnorm=I=-20:TP=-2:LRA=7" if clean else "anull"
    run([
        command("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vn", "-af", filters, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ])
    record = {"source": str(source), "prepared": str(output), "cleaned": clean, "probe": audio_probe(output)}
    output.with_suffix(".quality.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def profile_id(payload: object) -> str:
    if isinstance(payload, dict):
        for key in ("id", "profile_id", "voice_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        for key in ("profile", "voice", "data"):
            nested = payload.get(key)
            if nested is not None:
                try:
                    return profile_id(nested)
                except ValueError:
                    pass
    raise ValueError("response did not include a profile ID")


def create_profile(args: argparse.Namespace) -> None:
    health(args.base_url)
    reference = args.reference.resolve()
    prepared = args.work_dir.resolve() / "dabao-voice-reference-48k.wav"
    record = prepare_reference(reference, prepared, not args.no_clean_reference)
    with prepared.open("rb") as handle:
        response = requests.post(
            api_url(args.base_url, "profiles"), timeout=120,
            data={
                "name": args.name,
                "ref_text": args.reference_text,
                "instruct": args.instruct,
                "language": "Chinese",
                "seed": str(args.seed),
                "kind": "clone",
            },
            files={"ref_audio": (prepared.name, handle, "audio/wav")},
        )
    try:
        response.raise_for_status()
        payload = response.json()
        identifier = profile_id(payload)
    except (requests.RequestException, ValueError) as error:
        detail = response.text[:500] if "response" in locals() else ""
        fail(f"创建 VoiceStudio 音色失败: {detail or error}")
    record.update({"profile_id": identifier, "profile_name": args.name, "instruct": args.instruct, "seed": args.seed})
    profile_file = args.work_dir.resolve() / "voicestudio-profile.json"
    profile_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"profile_id": identifier, "record": str(profile_file)}, ensure_ascii=False))


def paragraphs(path: Path, maximum: int) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    units = [re.sub(r"\s*\n\s*", "", item).strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    result: list[str] = []
    for unit in units:
        while len(unit) > maximum:
            boundary = max(unit.rfind(mark, 0, maximum) for mark in "。！？；，")
            boundary = boundary + 1 if boundary > maximum // 2 else maximum
            result.append(unit[:boundary])
            unit = unit[boundary:]
        if unit:
            result.append(unit)
    return result


def concat_wavs(parts: list[Path], output: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as handle:
        manifest = Path(handle.name)
        for part in parts:
            escaped = str(part.resolve()).replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    try:
        run([
            command("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
            "-i", str(manifest), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output),
        ])
    finally:
        manifest.unlink(missing_ok=True)


def synthesize(args: argparse.Namespace) -> None:
    health(args.base_url)
    if not args.text.is_file():
        fail(f"找不到解说稿: {args.text}")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    chunks = paragraphs(args.text, args.max_chars)
    if not chunks:
        fail("解说稿为空。")
    segment_dir = output.parent / f"{output.stem}_segments"
    segment_dir.mkdir(exist_ok=True)
    headers = {"Authorization": "Bearer local", "Content-Type": "application/json"}
    parts: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        part = segment_dir / f"{index:03d}.wav"
        payload = {"model": args.model, "voice": args.voice, "input": chunk, "response_format": "wav", "speed": args.speed}
        try:
            response = requests.post(api_url(args.base_url, "audio/speech"), headers=headers, json=payload, timeout=240)
            response.raise_for_status()
        except requests.RequestException as error:
            fail(f"第 {index}/{len(chunks)} 段 VoiceStudio 配音失败: {error}")
        part.write_bytes(response.content)
        if not part.exists() or part.stat().st_size < 512:
            fail(f"第 {index}/{len(chunks)} 段没有生成可用音频。")
        parts.append(part)
    concat_wavs(parts, output)
    probe = audio_probe(output)
    stream = next((item for item in probe.get("streams", []) if item.get("codec_name")), {})
    peak = audio_peak_db(output)
    quality = {
        "voice": args.voice, "text": str(args.text.resolve()), "audio": str(output), "chunks": len(chunks),
        "speed": args.speed, "probe": probe, "peak_db": peak,
        "passed": stream.get("codec_name") == "pcm_s16le" and stream.get("sample_rate") == "48000" and stream.get("channels") == 1 and (peak is None or peak <= -0.05),
    }
    quality_path = output.with_suffix(".quality.json")
    quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    if not quality["passed"]:
        fail(f"配音质量门禁未通过，详见: {quality_path}")
    print(json.dumps({"audio": str(output), "quality": str(quality_path), "chunks": len(chunks)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Alan 的 VoiceStudio 本地克隆音色适配器")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="VoiceStudio 本地 API，默认 http://127.0.0.1:3900/v1")
    sub = parser.add_subparsers(dest="action", required=True)
    check = sub.add_parser("health", help="检查 VoiceStudio 是否已启动")
    check.set_defaults(func=lambda args: print(json.dumps(health(args.base_url), ensure_ascii=False)))
    clone = sub.add_parser("clone", help="准备参考音频并创建可复用克隆 profile")
    clone.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    clone.add_argument("--work-dir", type=Path, required=True)
    clone.add_argument("--name", default="大宝电影解说")
    clone.add_argument("--reference-text", default="")
    clone.add_argument("--instruct", default=DEFAULT_INSTRUCT)
    clone.add_argument("--seed", type=int, default=20261005)
    clone.add_argument("--no-clean-reference", action="store_true")
    clone.set_defaults(func=create_profile)
    tts = sub.add_parser("synthesize", help="用已创建 profile 分段配音并合并为 48k 单声道 WAV")
    tts.add_argument("--voice", required=True, help="VoiceStudio profile ID，不要提交到 Git")
    tts.add_argument("--text", required=True, type=Path)
    tts.add_argument("--output", required=True, type=Path)
    tts.add_argument("--model", default="tts-1")
    tts.add_argument("--speed", type=float, default=1.0)
    tts.add_argument("--max-chars", type=int, default=260)
    tts.set_defaults(func=synthesize)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if getattr(args, "speed", 1.0) <= 0:
        fail("--speed 必须大于 0")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
