# 电影解说自动剪辑工作流

主剪辑底座为 [PySceneDetect](https://github.com/Breakthrough/PySceneDetect)：约 5.2k GitHub stars、BSD-3-Clause，提供可嵌入的镜头边界检测。它与 FFmpeg 一起生成可审核的初剪；不把一个交互式剪辑 UI 直接塞进批处理流程。

## 完整交付目录

```text
<项目>/
  原片/<影片>.mp4                 # 已获授权或自有片源
  原片/<影片>.srt                 # 原片字幕
  解说稿.txt                       # 按 Alan 风格，通过 validate_script.py
  配音/大宝解说.wav                # VoiceStudio 成品 + quality.json
  剪辑/镜头.json                   # PySceneDetect 结果
  剪辑/初剪计划.json               # 必须审核的 EDL
  字幕/解说字幕.srt                # 成片字幕（人工或 ASR 校准）
  成片/<片名>_解说.mp4
  封面/封面提示词-即梦.txt
  发布信息.txt
```

## 自动初剪到成片

```powershell
python -m pip install -r requirements-movie-edit.txt

python scripts/auto_edit_movie.py detect-scenes `
  --video "<项目>\原片\影片.mp4" `
  --output "<项目>\剪辑\镜头.json"

python scripts/auto_edit_movie.py first-cut `
  --source-video "<项目>\原片\影片.mp4" `
  --narration "<项目>\配音\大宝解说.wav" `
  --scenes "<项目>\剪辑\镜头.json" `
  --output "<项目>\剪辑\初剪计划.json"
```

初剪会按原片时间顺序取镜头，适配本项目“按剧情顺序讲述”的解说稿。打开 `初剪计划.json`，逐条检查镜头与当段解说是否一致，将各条 `approved` 设为 `true` 后再渲染：

```powershell
python scripts/auto_edit_movie.py render `
  --plan "<项目>\剪辑\初剪计划.json" `
  --subtitle "<项目>\字幕\解说字幕.srt" `
  --output "<项目>\成片\片名_解说.mp4"
```

仅为内部试看可添加 `--allow-unreviewed`。正式成片不应跳过镜头审校；自动切点不等于画面语义正确。渲染默认静音原片并保留 VoiceStudio 解说，避免原声对白与解说互相打架。

## 流程边界

- 选题/查重：`check_done.py`、`select_next.py`。
- 下载原片/原片 SRT：只处理用户有权下载和使用的来源；沿用 `references/film-sourcing.md` 的验证要求。
- 生成解说稿：通读 SRT，再按 `SKILL.md` 的 Alan 风格写稿并运行 `validate_script.py`。
- 配音：使用 `references/voicestudio-workflow.md`。
- 封面与发布信息：使用 `select_cover_frame.py`、`gen_jimeng_cover_prompts.py`、`validate_publication_info.py`。
