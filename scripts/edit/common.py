# -*- coding: utf-8 -*-
"""Alan 剪辑管线共享工具。

设计约束：
- 只用标准库 + ffmpeg/ffprobe，重依赖（torch/whisper/scenedetect）全部可选；
- 所有中间产物落 JSON，可单步重跑，不重算上游；
- 中文老稿编码必须探测（SKILL.md 已记录的坑：GBK / UTF-8+BOM 混用）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

EDIT_DIR = Path(__file__).resolve().parent
ALAN_ROOT = EDIT_DIR.parents[1]
SCRIPTS_DIR = ALAN_ROOT / "scripts"
VENDOR_DIR = ALAN_ROOT / "vendor"
FILMS_DIR = ALAN_ROOT / "films"

FFMPEG_SKILL = VENDOR_DIR / "ffmpeg-skill" / "scripts"
MOVIE_NARRATOR = VENDOR_DIR / "movie-narrator"

TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

BUILD_DIRNAME = "build"


# ---------------------------------------------------------------- 文本

def read_text_any(path: str | Path) -> str:
    """按 BOM / UTF-8 / GB18030 顺序探测解码，永不抛编码异常。"""
    data = Path(path).read_bytes()
    for enc in TEXT_ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def write_text_utf8(path: str | Path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


# ---------------------------------------------------------------- JSON

def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: str | Path, obj: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_dir(work: str | Path) -> Path:
    return ensure_dir(Path(work) / BUILD_DIRNAME)


# ---------------------------------------------------------------- 进程

def _exe(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"找不到 {name}，请确认 ffmpeg 已安装并在 PATH 中")
    return found


def ffmpeg() -> str:
    return _exe("ffmpeg")


def ffprobe() -> str:
    return _exe("ffprobe")


def run(cmd: list[str], cwd: str | Path | None = None, timeout: int | None = None,
        quiet: bool = False) -> subprocess.CompletedProcess:
    """执行命令，失败时把 stderr 尾部带进异常信息。"""
    if not quiet:
        print("  $ " + " ".join(str(c) for c in cmd[:6]) + (" ..." if len(cmd) > 6 else ""))
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError(f"命令失败({proc.returncode}): {' '.join(cmd[:4])}\n" + "\n".join(tail))
    return proc


# ---------------------------------------------------------------- 媒体探测

def probe_media(path: str | Path) -> dict:
    proc = run([
        ffprobe(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ], quiet=True)
    return json.loads(proc.stdout or "{}")


def media_duration(path: str | Path) -> float:
    info = probe_media(path)
    dur = (info.get("format") or {}).get("duration")
    if dur:
        return float(dur)
    for s in info.get("streams") or []:
        if s.get("duration"):
            return float(s["duration"])
    return 0.0


def video_size(path: str | Path) -> tuple[int, int, float]:
    """返回 (width, height, fps)。"""
    info = probe_media(path)
    w = h = 0
    fps = 0.0
    for s in info.get("streams") or []:
        if s.get("codec_type") == "video":
            w = int(s.get("width") or 0)
            h = int(s.get("height") or 0)
            rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            try:
                num, _, den = rate.partition("/")
                fps = float(num) / float(den or 1)
            except (ValueError, ZeroDivisionError):
                fps = 0.0
            break
    return w, h, fps


# ---------------------------------------------------------------- 时间格式

def t_ff(seconds: float) -> str:
    """ffmpeg-skill 接受的时间写法：m:ss.mmm（毫秒三位）。"""
    seconds = max(0.0, float(seconds))
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}"


def t_human(seconds: float) -> str:
    m, s = divmod(max(0.0, float(seconds)), 60)
    return f"{int(m):02d}:{s:05.2f}"


def t_srt(seconds: float) -> str:
    ms = int(round(max(0.0, float(seconds)) * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------------------------------------------------------------- 文本清洗

_STRUCT_LINE = re.compile(r"^(\[|〔|【|<|\||!\[|```)")
_MD_HEADING = re.compile(r"^#{1,6}\s+")


def is_struct_line(line: str) -> bool:
    """结构行（片段标注 / 段落标记 / 代码块 / 标题）不参与 TTS 与匹配。"""
    s = line.strip()
    if not s:
        return False
    if _MD_HEADING.match(s):
        return True
    if s.startswith(">"):
        return True
    if re.fullmatch(r"〔[^〕]*〕", s) or re.fullmatch(r"【[^】]*】", s):
        return True
    if _STRUCT_LINE.match(s):
        return True
    return False


def clean_lines(text: str) -> list[str]:
    """去掉 front-matter、结构行、行内 markdown 强调，返回有效正文行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    # YAML front matter
    if lines and lines[0].strip() == "---":
        for i in range(1, min(len(lines), 80)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break

    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or is_struct_line(line):
            continue
        line = re.sub(r"\*\*|__|`", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.、]\s*", "", line)
        if line:
            out.append(line)
    return out


_SENT_END = re.compile(r"(?<=[。！？!?…])")


def split_sentences(line: str) -> list[str]:
    """按句末标点切句，保留标点；连续省略号不拆。"""
    parts = [p.strip() for p in _SENT_END.split(line)]
    merged: list[str] = []
    for p in parts:
        if not p:
            continue
        if merged and merged[-1].endswith("…") and p.startswith("…"):
            merged[-1] += p
            continue
        merged.append(p)
    # 没有句末标点的长尾也算一句
    return merged


def char_count(text: str) -> int:
    """计入语速的字数：去掉标点与空白。"""
    return len(re.sub(r"[\s，。！？、；：,.!?;:…—\-（）()“”‘’\"'《》<>\[\]【】]", "", text))
