#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《封面提示词-即梦.txt》: 即梦"图生图"用的两段完整提示词(3:4竖版 + 4:3横版)。

封面标准(艾伦频道): 参考图女主角重绘为金发碧眼美女 + 仅一个大大的手写体电影名标题,
画面中不出现任何其他文字。用法: 用户在即梦上传选好的底图(封面底图-主推.jpg)作为参考图,
选对应比例, 粘贴提示词生成。

用法:
  python scripts/gen_jimeng_cover_prompts.py --movie 夺命舞会 --out "D:\\...\\封面\\封面提示词-即梦.txt"
    [--subject 惊艳的金发碧眼美人] [--hair 金色微卷长发、发量丰盈光泽柔顺]
    [--outfit 深红色复古丝质衬衫式礼服，领口优雅微敞，剪裁贴合身形、勾勒迷人的身材曲线]
    [--scene 1980年代毕业舞会之夜：身后是虚化的舞会大厅，暖金色灯串与迪斯科灯球的柔光光斑、霓虹光晕点缀，深色暗调氛围]
    [--emotion 微微惊讶紧张，双眼睁大直直看向镜头，嘴唇微启，透出一丝不安的惊悚感]
    [--text-style 字身为鲜红色（大红），无渐变、无金属光泽，外侧描一圈细黑色描边]
    [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

BODY = (
    "电影解说视频封面，{ratio}构图，电影海报级画面。以参考图中的年轻女主角为主体，保留她的姿态与画面中的位置，"
    "把她重绘为一位{subject}：{hair}，湛蓝色的眼眸明亮深邃，肌肤白皙细腻如瓷，"
    "五官精致立体，妆容精致复古；身材丰盈傲人、曲线优美动人，身穿{outfit}；"
    "{emotion}。背景重绘为{scene}，悬疑恐怖电影光影，景深虚化，主体突出。"
    "{text_pos}排列一行大大的手写体中文标题：「{movie}」四个字，手写软笔笔刷字——"
    "笔画偏粗、粗细对比鲜明，顿笔出锋、转折利落，字形活泼生动有冲击力，带飞白、毛边与颗粒质感；"
    "{text_style}；字迹清晰准确、四字完整、无错字无变形，{text_width}。"
    "除「{movie}」这四个字外，画面中不出现任何其他文字、英文字母、logo或水印。"
    "整体高清细腻，电影级打光，复古高级质感，构图平衡。"
)

DEFAULTS = {
    "subject": "惊艳的金发碧眼美人",
    "hair": "一头金色微卷长发、发量丰盈光泽柔顺",
    "outfit": "深红色复古丝质衬衫式礼服，领口优雅微敞，剪裁贴合身形、勾勒迷人的身材曲线",
    "scene": "1980年代毕业舞会之夜：身后是虚化的舞会大厅，暖金色灯串与迪斯科灯球的柔光光斑、霓虹光晕点缀，深色暗调氛围",
    "emotion": "表情微微惊讶紧张，双眼睁大直直看向镜头，嘴唇微启，透出一丝不安的惊悚感",
    "text_style": "字身为鲜红色（大红），无渐变、无金属光泽，外侧描一圈细黑色描边、描边细而利落，与画面形成强烈的红黑对比",
}

RATIOS = (
    ("3:4竖版", "画面上方约五分之一处居中", "标题几乎横贯整个画面宽度"),
    ("4:3横版", "画面上部居中", "标题宽度约占画面的九成"),
)


def build(movie: str, opts: dict, ratio: str, text_pos: str, text_width: str) -> str:
    return BODY.format(movie=movie, ratio=ratio, text_pos=text_pos, text_width=text_width, **opts)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成即梦图生图封面提示词(3:4 + 4:3 两段)")
    ap.add_argument("--movie", required=True, help="电影名(将渲染为手写体大标题)")
    ap.add_argument("--out", help="输出文件路径(默认 ./封面提示词-即梦.txt)")
    for key, val in DEFAULTS.items():
        ap.add_argument(f"--{key}", default=val, help=f"默认: {val[:30]}...")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    opts = {k: getattr(args, k.replace("-", "_")) for k in DEFAULTS}
    parts = [build(args.movie, opts, r, p, w) for r, p, w in RATIOS]
    content = "\n\n".join(parts)

    if args.dry_run:
        print(content)
        return 0
    out = args.out or os.path.join(os.getcwd(), "封面提示词-即梦.txt")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"已写入 {out} ({len(content)} 字符, 2段: 3:4竖版 / 4:3横版)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
