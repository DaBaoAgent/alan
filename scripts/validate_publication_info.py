#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验发布信息文件(移植自 AutoYY, 适配艾伦频道)。

规则(每个 发布信息.txt):
  - 恰好 N 块(默认 1 块, 多平台各留一份时传 --blocks N): 每块两行非空内容,
    第一行标题(默认 ≤25 字, 不要写"标题："之类字段名, 无 emoji),
    第二行恰好 5 个话题词(#开头, 空格分隔, 惯例带频道词 #艾伦和艾薇);
  - 文件可放片目录根或 发布/ 子目录(递归扫描); 块之间可空行分隔;
  - 不允许出现旧版字段标记(爆款标题：/匹配标签：/发布建议：/版权提醒：/封面正标题/封面副标题)。

用法:
  python scripts/validate_publication_info.py <根目录> [--blocks 2] [--json-out report.json] [--max-title 25]
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


def validate_file(path: Path, root: Path, max_title: int, blocks: int = 1) -> dict:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    non_empty = [l for l in text.splitlines() if l.strip()]

    if len(non_empty) != 2 * blocks:
        issues.append(
            f"非空行数为 {len(non_empty)}, 应为 2×{blocks}={2 * blocks} 行"
            f"(每块=标题+话题词; 多份时用 --blocks N)"
        )
    if EMOJI_RE.search(text):
        issues.append("含 emoji")
    found_legacy = [f for f in LEGACY_FIELDS if f in text]
    if found_legacy:
        issues.append("出现旧版字段: " + ", ".join(found_legacy))

    block_results = []
    for i in range(blocks):
        title = non_empty[2 * i].strip() if len(non_empty) > 2 * i else ""
        tag_line = non_empty[2 * i + 1].strip() if len(non_empty) > 2 * i + 1 else ""
        b_issues: list[str] = []
        if not title:
            b_issues.append("标题缺失")
        if len(title) > max_title:
            b_issues.append(f"标题长度 {len(title)}, 超过 {max_title} 字")
        if re.match(r"^(?:爆款)?标题[:：]", title):
            b_issues.append("标题行包含字段名")
        tag_tokens = tag_line.split()
        valid_tags = [t for t in tag_tokens if HASHTAG_RE.fullmatch(t)]
        if len(valid_tags) != 5:
            b_issues.append(f"有效话题词 {len(valid_tags)} 个, 应恰好 5 个")
        prefix = f"第{i + 1}块: " if blocks > 1 else ""
        issues.extend(prefix + bi for bi in b_issues)
        block_results.append({
            "title": title, "title_length": len(title),
            "hashtag_count": len(valid_tags), "issues": b_issues,
        })

    first = block_results[0] if block_results else {"title": "", "title_length": 0, "hashtag_count": 0}
    return {
        "file": str(path.relative_to(root)),
        "valid": not issues,
        "blocks": blocks,
        "title": first["title"],
        "title_length": first["title_length"],
        "hashtag_count": first["hashtag_count"],
        "issues": issues,
        "block_results": block_results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 发布信息.txt(标题 + 5个话题词)")
    ap.add_argument("root", type=Path)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--max-title", type=int, default=25)
    ap.add_argument("--blocks", type=int, default=1,
                    help="发布信息块数(每块=标题+话题词两行); 多平台各留一份时传实际份数, 默认 1")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
        return 2

    files = sorted(root.rglob("发布信息.txt"))
    results = [validate_file(p, root, args.max_title, args.blocks) for p in files]
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
