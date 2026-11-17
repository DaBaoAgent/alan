# 剪辑流水线（稿 → 配音 → 对齐 → 镜头表 → EDL → 成片）

Alan 的第六件套之外，补上了从"成稿 + 配音"到"成片"的那一段。分解：

```
口播稿_定稿.txt
   │  read_script.py          句级切分 + TTS 分段
   ▼
build/segments.json + build/配音稿.txt
   │  voiceover.py            调 PeiYin dianying 管线（默认，参数见 references/peiyin-voice-contract.md）
   ▼
配音.wav
   │  align_voice.py          ASR 词时间 ↔ 稿子字符流全局对齐
   ▼
build/timeline.json + build/subtitle.srt
   │  shot_table.py           镜头检测（+ 可选画面描述）
   ▼
build/shots.json
   │  match_edl.py            语义/时序打分 + act 分区 + 长句拆槽 + clamp
   ▼
build/edl.json + build/edl.csv
   │  render_edl.py           → ffmpeg-skill 的 project.json
   ▼
final.mp4
```

## 片目录

```
films/<片名>/
  口播稿_定稿.txt     配音稿（read_script 也会生成 build/配音稿.txt 供 TTS 分段）
  配音.wav            成品配音，对齐与成片的唯一音源
  原片.mp4
  film.json
  build/              全部中间产物（gitignore）
```

`alan_edit.py init` 会把稿子复制、视频/配音硬链接进片目录（同盘瞬时，不占空间）。

## 命令

```powershell
# 一次性建片目录
python scripts\edit\alan_edit.py init --name 某片 --script 稿.txt --video 原片.mp4

# 逐步跑（每步可单独重跑）
python scripts\edit\alan_edit.py script  --work "D:\@kaifa\Alan\films\某片"
python scripts\edit\alan_edit.py voice   --work ... --backend peiyin     # 或 alan / none
python scripts\edit\alan_edit.py align   --work ... --backend auto       # whisperx>faster>rough
python scripts\edit\alan_edit.py shots   --work ... --backend auto       # pyscenedetect>ffmpeg
python scripts\edit\alan_edit.py match   --work ...
python scripts\edit\alan_edit.py render  --work ... --csv                # 只出 project.json
python scripts\edit\alan_edit.py render  --work ... --run                # 直接出片

# 一条链
python scripts\edit\alan_edit.py all --work ... --run
```

## 匹配层做了什么

算法血统是 `vendor/movie-narrator/src/movie_narrator/pipeline/match`，保留下来的四条：

- **act 分区**：场景按 0.15 / 0.25 / 0.40 / 0.20 的时间权重分四段，句子按叙事位置落桶，
  对应"钩子 / 铺垫 / 正片 / 收尾"，避免开头就抓高潮镜头；
- **贪心 topk**：候选按分数排序，复用惩罚 0.15、回看窗口 3；
- **窗口 clamp**：`speed = 原片时长 / 配音时长` 必须在 `[0.85, 1.25]`，超出则以镜头中点为心
  扩/缩，撞到片头片尾贴边；
- **多样性**：滑动窗口 3 内同镜超过 2 次，换最近未用镜头（优先往后找）并重新 clamp。

本项目改的三处（这是它跟 movie-narrator 的本质差别）：

1. **长句拆槽**。Alan 一句 8~18s，电影镜头均 3~6s。原实现一句只配一镜，靠 1.25 倍变速
   硬撑，长句必然超速。这里先按标点把长句切 `k = ceil(句长 / --max-slot)` 个子槽，每槽独立
   选镜，并要求同句内源时间递增，于是 18s 的一句话落到 3~4 个连续镜头，speed 仍在 ±15%。
2. **句间停顿吸收**。配音里的静默（dianying 直连：句间约 0.1s、段间约 0.2s；段落模式段间按 `--paragraph-gap-ms`）
   没有解说词但画面不能停。把它们并入上一句最后一个槽（上限 `--absorb-gap`，默认 1.2s），
   否则片段累计比配音短，音画会一路累积错位。
3. **叙事游标**。`--monotonic on`（默认）让期望位置取"解说进度"与"上一镜中点"的较大值，
   镜头只前进不倒退；纯时序打分时位置差按 18% 片长归一，避免复用惩罚盖过位置优势导致跳镜。

## 精度分三档，必须如实知晓

`edl.json` 的 `stats.scorer` 写明实际用了哪一档：

| scorer | 条件 | 含义 |
|---|---|---|
| `embed` | 有画面描述 + sentence-transformers | 语义余弦 0.75 + 时序 0.25，真的在"看懂画面" |
| `keyword` | 有画面描述、无模型 | 中文 2-gram 重叠 0.65 + 时序 0.35 |
| `temporal` | 无画面描述 | 纯剧情时序先验，等于按比例猜 |

**要"精准配画面"，必须先给 shots.json 补描述**：

```powershell
python scripts\edit\alan_edit.py shots --work ... --caption-backend openai `
  --caption-base-url $env:ALAN_VLM_BASE_URL --caption-key $env:ALAN_VLM_KEY
```

描述覆盖率 <70% 时打分自动退回 `temporal`，并在 `warnings` 里标出来。

## 渲染

`render_edl.py` 生成的 project.json 与 ffmpeg-skill 的 `OBJECT_KEYS` 严格对齐：

- `clips[]`：`{src, in, out, speed}`，speed 是播放倍速，内部 `fit.py --duration 原长/speed`，
  `speed=1.0` 时跳过重编码；
- `audio: {replace: 配音.wav}`：`audio.py --replace` 是"整条音轨替换，按画面长度裁剪/补静音"，
  正好匹配"无声原片 + 整条配音"；
- `captions: {srt, font, size, margin, max_lines}`：走 `caption.py`，`margin` 是**像素整数**；
  `size` 是 ASS points，**按 288p 脚本缩放**，1080p 实际字高 ≈ size×3.75，所以默认 20（约 75px），
  想小一点用 16，想大一点 24；
- `loudness: {lufs: -14, tp: -1}`，`export.normalize=false`（否则二次归一化会冲掉 loudness）；
  loudnorm 的 linear 模式在真峰值受限时会欠调 1~2dB，`render_edl.py` 渲染后会自己复核一次，
  不合格就补跑一遍 `loudness.py`（`--no-loudness-fix` 可关）；
- `transition` 默认 `none`：fade 0.5 会让每个切口吃掉 0.5s，总长就对不上配音了。

成片落到**片目录根** `films/<片名>/final.mp4`，`build/` 只留中间产物（project.json 等），
符合"交付目录根只放最终交付物"。

返工：`render --export-timeline build/edit.fcpxml` 把时间线导进 Premiere / Resolve。

## 已知限制

- **对齐**：没装 faster-whisper / whisperx 时 `rough` 按字数比例切，±0.5s 以上会漂移，
  只能用来跑通结构，正式出片必须装 ASR（`pip install faster-whisper`）。
- **镜头检测**：pyscenedetect 未装时用 ffmpeg `scdet`，阈值是 0~100 的分数
  （真实电影 10~15，静态/暗场素材要降到 3~5）。暗场切换可能漏检，漏检只会让镜头偏长。
- **字幕字体**：Windows 上默认 `Microsoft YaHei`；换字体要确认系统已安装，否则中文会是方块。
- **配音静音**：`loudness.py` 会拒绝处理静音轨（这是对的），测试/占位配音请用 `--no-loudness`。
- **许可**：`vendor/movie-narrator` 是 AGPL-3.0，只借鉴算法实现、未复制其代码；
  `vendor/ffmpeg-skill` 是 MIT。
