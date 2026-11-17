# -*- coding: utf-8 -*-
"""Alan 剪辑管线（B 方案：自建匹配层 + ffmpeg-skill 执行）。

模块顺序即数据流：
    read_script  稿 → segments.json
    voiceover    配音稿 → 配音.wav（PeiYin / 本地）
    align_voice  配音 → timeline.json（句级时间）
    shot_table   原片 → shots.json（镜头表）
    match_edl    timeline + shots → edl.json
    render_edl   edl → ffmpeg-skill project.json → final.mp4
"""
