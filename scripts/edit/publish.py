#!/usr/bin/env python
"""封面 + 发布信息：调 vendor/fengmian，把成片补成可交付的完整包。

本脚本是 Alan 剪辑链路的最后一环，上游吃 <片目录>/build/subtitle.srt
（没有时退回 <片目录>/口播稿_定稿.txt），下游产出：

  <片目录>/发布信息.txt                     两行制：标题 ≤25 字两段式 + 恰好 4 个话题
  <片目录>/build/封面提示词-4比3.txt        6 字主标 + 8 字副标的成图提示词
  <片目录>/build/封面提示词-3比4.txt
  <片目录>/build/封面元信息.json            主标/副标/风格/场景/钩子来源，便于回查
  <片目录>/封面-4比3.png、封面-3比4.png     仅在 --covers ark 且配置 ARK_API_KEY 时

交付根只留：final.mp4 / 封面-4比3 / 封面-3比4 / 发布信息.txt / build/ / 素材文件。
提示词与元信息一律进 build/，配合 fengmian 的交付门禁（fm/gate.py）检查。

用法：
  python scripts/edit/publish.py --work "D:\\@kaifa\\Alan\\films\\阴风阵阵"
  python scripts/edit/publish.py --work <片目录> --main 阴风阵阵 --sub 修女的血色诅咒 \
      --title "阴风阵阵：1977年最邪的一栋房子" --tags "#阴风阵阵 #铅黄电影 #恐怖片 #艾伦解说"
  python scripts/edit/publish.py --work <片目录> --covers ark
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import build_dir, ensure_dir, read_text_any, write_json, write_text_utf8  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FENGMIAN = ROOT / "vendor" / "fengmian"
MAIN_LEN = 6
SUB_LEN = 8


def load_fm():
    if not FENGMIAN.is_dir():
        raise SystemExit(
            f"未找到 fengmian：{FENGMIAN}\n"
            "重建：git clone --depth 1 https://github.com/DaBaoAgent/fengmian.git vendor/fengmian"
        )
    if str(FENGMIAN) not in sys.path:
        sys.path.insert(0, str(FENGMIAN))
    from fm import analyze as A
    from fm import cover as C
    from fm import gate as G
    from fm import publish as P
    from fm import validate as V

    return A, C, P, V, G


def pick_source(work: Path) -> tuple[Path, str]:
    """优先用句级字幕（已去时间轴，正文最干净），退回口播稿并转 UTF-8。"""
    b = build_dir(work)
    srt = b / "subtitle.srt"
    if srt.exists():
        return srt, "字幕"
    txt = work / "口播稿_定稿.txt"
    if txt.exists():
        dst = b / "封面源稿.txt"
        write_text_utf8(dst, read_text_any(txt))
        return dst, "口播稿"
    raise SystemExit(f"片目录里既没有 {srt}，也没有 {txt}")


def cmd(args) -> int:
    work = Path(args.work).resolve()
    if not work.is_dir():
        raise SystemExit(f"片目录不存在：{work}")
    A, C, P, V, G = load_fm()

    src, kind = pick_source(work)
    name = args.name or work.name
    parsed = A.analyze(src, name)

    print(f"源文案：{src}（{kind}）")
    print(f"建议主标：{parsed['suggested_main']}  建议副标：{parsed['suggested_sub']}")
    print(f"建议话题：{' '.join(parsed['suggested_tags'])}")
    print(f"钩子：{parsed['hooks'][:3]}")

    if args.analyze:
        print(json.dumps({"suggested_main": parsed["suggested_main"],
                          "suggested_sub": parsed["suggested_sub"],
                          "suggested_tags": parsed["suggested_tags"],
                          "hooks": parsed["hooks"][:6],
                          "numbers": parsed["numbers"][:6]}, ensure_ascii=False, indent=2))
        return 0

    if args.tags:
        tag_list = args.tags.split()
        if len(tag_list) != 4:
            raise SystemExit(f"话题必须恰好 4 个，实际 {len(tag_list)} 个：{' '.join(tag_list)}")
    else:
        tag_list = [t if t.startswith("#") else f"#{t}" for t in parsed["suggested_tags"]]
        for extra in [name] + list(parsed.get("keywords", [])):
            if len(tag_list) >= 4:
                break
            tag = "#" + "".join(str(extra).split())
            if re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9]{2,8}", tag[1:]) and tag not in tag_list:
                tag_list.append(tag)
        if len(tag_list) < 4:
            raise SystemExit(
                f"文案太短，自动只凑出 {len(tag_list)} 个话题（{' '.join(tag_list)}），用 --tags 指定恰好 4 个"
            )
        if len(tag_list) > 4:
            tag_list = tag_list[:4]

    main = args.main or parsed["suggested_main"]
    sub = args.sub or parsed["suggested_sub"]
    main, sub = "".join(main.split()), "".join(sub.split())
    scenes = {
        "4x3": args.scene43 or "画面主体位于中部，左右留出标题呼吸区，环境交代清楚，无人物正脸特写。",
        "3x4": args.scene34 or "主体位于中下部朝画面深处，上部三分之一留作标题净空，环境层次向上延伸。",
    }

    b = ensure_dir(build_dir(work))
    sized = len(main) == MAIN_LEN and len(sub) == SUB_LEN
    if sized:
        prompts = C.build(main, sub, scenes["4x3"], scenes["3x4"], args.style)
        write_text_utf8(b / "封面提示词-4比3.txt", prompts["ratio_4x3"] + "\n")
        write_text_utf8(b / "封面提示词-3比4.txt", prompts["ratio_3x4"] + "\n")
        print(f"  ✓ {b / '封面提示词-4比3.txt'}")
        print(f"  ✓ {b / '封面提示词-3比4.txt'}")
    else:
        print(f"  · 主标需 {MAIN_LEN} 字、副标需 {SUB_LEN} 字（当前主标 {len(main)} 字「{main}」/ "
              f"副标 {len(sub)} 字「{sub}」），本次只出发布信息；用 --main / --sub 定稿后再跑可出封面提示词。")

    try:
        info = P.from_analysis(parsed, title=args.title, tags=tag_list)
    except ValueError as exc:
        raise SystemExit(f"发布信息生成失败：{exc}")
    write_text_utf8(work / "发布信息.txt", info)
    print(f"  ✓ {work / '发布信息.txt'}")

    meta = {
        "source": str(src),
        "source_kind": kind,
        "name": name,
        "style": args.style,
        "main": main,
        "sub": sub,
        "scene_4x3": scenes["4x3"],
        "scene_3x4": scenes["3x4"],
        "publish_info": info.strip().splitlines(),
        "suggested_tags": parsed["suggested_tags"],
        "hooks": parsed["hooks"][:4],
        "numbers": parsed["numbers"][:6],
        "auto_main": args.main is None,
        "auto_sub": args.sub is None,
        "covers_prompted": sized,
    }
    write_json(b / "封面元信息.json", meta)
    print(f"  ✓ {b / '封面元信息.json'}")

    check = V.check(work / "发布信息.txt")
    print(json.dumps(check, ensure_ascii=False, indent=2))

    gate = G.scan(work)
    if gate["extras"]:
        print("✗ 交付门禁：根目录有多余封面/提示词，交付前必须清掉：" + "、".join(gate["extras"]))
    if gate["missing"]:
        print("  （封面尚未出图：" + "、".join(gate["missing"]) + "）")

    rc = 0 if check["valid"] else 1

    if args.covers == "ark":
        if not os.environ.get("ARK_API_KEY"):
            print("⚠ 未配置 ARK_API_KEY，跳过出图；可直接用 build/ 里的提示词人工出图。")
        else:
            cmdline = [
                "node", str(FENGMIAN / "scripts" / "gen_covers_ark.mjs"),
                "--out", str(work),
                "--prompt43", str(b / "封面提示词-4比3.txt"),
                "--prompt34", str(b / "封面提示词-3比4.txt"),
            ]
            print(" ".join(cmdline))
            subprocess.call(cmdline, cwd=str(FENGMIAN))

    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="封面 + 发布信息（调 vendor/fengmian）")
    ap.add_argument("--work", required=True, help="片目录，如 D:\\@kaifa\\Alan\\films\\片名")
    ap.add_argument("--name", help="片名（默认取片目录名）")
    ap.add_argument("--main", help=f"封面主标，恰好 {MAIN_LEN} 字")
    ap.add_argument("--sub", help=f"封面副标，恰好 {SUB_LEN} 字")
    ap.add_argument("--style", default="tuiyan", help="tuiyan / laolang / auto，或直接传风格描述")
    ap.add_argument("--scene43", help="4:3 画面描述")
    ap.add_argument("--scene34", help="3:4 画面描述")
    ap.add_argument("--title", help='两段式标题，如 "阴风阵阵：1977年最邪的一栋房子"')
    ap.add_argument("--tags", help='恰好 4 个话题，空格分隔，如 "#阴风阵阵 #铅黄电影 #恐怖片 #艾伦解说"')
    ap.add_argument("--covers", default="prompt", choices=["prompt", "ark", "none"],
                    help="prompt=只出提示词；ark=配置密钥后直出两张封面")
    ap.add_argument("--analyze", action="store_true", help="只解析文案，打印建议，不写文件")
    args = ap.parse_args(argv)
    return cmd(args)


if __name__ == "__main__":
    sys.exit(main())
