#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验发布信息文件(移植自 AutoYY, 适配艾伦频道)。

规则(每个 发布信息.txt):
  - 恰好两行非空内容: 第一行标题(默认 ≤25 字, 不要写"标题："之类字段名, 无 emoji),
    第二行恰好 5 个话题词(#开头, 空格分隔);
  - 不允许出现旧版字段标记(爆款标题：/匹配标签：/发布建议：/版权提醒：/封面正标题/封面副标题)。

用法:
  python scripts/validate_publication_info.py <根目录> [--json-out report.json] [--max-title 25]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LEGACY_FIELDS = (
    "爆款标题：", "爆款标题:", "匹配标签：", "匹配标签:", "发布建议：", "发布建议:",
    "版权提醒：", "版权提醒:", "封面正标题", "封面副标题",
)
EMOJI_RE = re.compile("[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF]")
HASHTAG_RE = re.compile(r"#[^\s#]+")


def validate_file(path: Path, root: Path, max_title: int) -> dict:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [l for l in text.splitlines()]

    non_empty = [l for l in lines if l.strip()]
    if len(non_empty) != 2:
        issues.append(f"非空行数为 {len(non_empty)}, 应为 2 行(标题 + 话题词)")
    if any(not line.strip() for line in lines) and len(lines) > len(non_empty):
        issues.append("存在空行")

    title = non_empty[0].strip() if non_empty else ""
    tag_line = non_empty[1].strip() if len(non_empty) >= 2 else ""

    if not title:
        issues.append("标题缺失")
    if len(title) > max_title:
        issues.append(f"标题长度 {len(title)}, 超过 {max_title} 字")
    if re.match(r"^(?:爆款)?标题[:：]", title):
        issues.append("标题行包含字段名")
    if EMOJI_RE.search(text):
        issues.append("含 emoji")

    tag_tokens = tag_line.split()
    valid_tags = [t for t in tag_tokens if HASHTAG_RE.fullmatch(t)]
    if len(valid_tags) != 5:
        issues.append(f"有效话题词 {len(valid_tags)} 个, 应恰好 5 个")

    found_legacy = [f for f in LEGACY_FIELDS if f in text]
    if found_legacy:
        issues.append("出现旧版字段: " + ", ".join(found_legacy))

    return {
        "file": str(path.relative_to(root)),
        "valid": not issues,
        "title": title,
        "title_length": len(title),
        "hashtag_count": len(valid_tags),
        "issues": issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 发布信息.txt(标题 + 5个话题词)")
    ap.add_argument("root", type=Path)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--max-title", type=int, default=25)
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
        return 2

    files = sorted(root.rglob("发布信息.txt"))
    results = [validate_file(p, root, args.max_title) for p in files]
    summary = {
        "root": str(root),
        "file_count": len(results),
        "valid_count": sum(1 for r in results if r["valid"]),
        "invalid_count": sum(1 for r in results if not r["valid"]),
        "results": results,
    }
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if results and summary["invalid_count"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
