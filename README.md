# Alan 电影解说工作台

面向 B 站 / 抖音电影解说账号「艾伦」的**工业化生产线**：选片查重 → 写口播稿 → 配音 → 剪辑成片 → 封面与发布信息。

不是"一键生成解说视频"的黑盒。稿子由人写、音色由固定克隆音色合成、画面由剪辑决策表（EDL）精确驱动，每一步的中间产物都是可读、可改、可重跑的 JSON。

- 稿子：艾伦亲笔风格，6 件套结构，3800–5200 字
- 配音：默认调外部 PeiYin 项目（本地 `D:\@kaifa\PeiYin`，可用 `--peiyin-root` 改）的 dabao 克隆音色，也可退回本地 GPT-SoVITS
- 剪辑：自建匹配层做"句 → 镜头"决策，[ffmpeg-skill] 做纯执行
- 成片：1920×1080 / 30fps / H.264 / -14 LUFS / -1 dBTP，硬字幕

---

## 流水线

```
选片 ──► 写稿 ──► 校验 ──► 配音 ──► 对齐 ──► 镜头表 ──► 匹配 ──► 渲染 ──► 封面/发布
 │        │        │        │         │          │          │         │
查重   6件套    结构与      PeiYin   句级时间   切点检测   生成EDL   ffmpeg-skill
     黑话密度   签名        GPT-     timeline   shots.json  edl.json   project.json
                           SoVITS                                        │
                                                                     final.mp4
```

六个剪辑步骤一一对应 `scripts/edit/` 下的六个脚本，也可用 `alan_edit.py` 统一调度。

## 目录结构

```
Alan/
├── SKILL.md                    技能主入口：选片标准 / 文风规范 / 各流程入口
├── scripts/
│   ├── edit/                   剪辑流水线（本仓库核心）
│   │   ├── alan_edit.py        统一 CLI：init / script / voice / align / shots / match / render / all / status
│   │   ├── common.py           编码探测、ffprobe、时间格式、文本清洗
│   │   ├── read_script.py      口播稿 → 句级 segments.json + TTS 分段稿
│   │   ├── voiceover.py        配音（PeiYin / 本地 GPT-SoVITS）
│   │   ├── align_voice.py      配音 → 句级 timeline.json + SRT
│   │   ├── shot_table.py       原片 → shots.json（可选 VLM 画面描述）
│   │   ├── match_edl.py        匹配 → edl.json
│   │   └── render_edl.py       edl → ffmpeg-skill project.json → final.mp4
│   ├── check_done.py           已解说库查重
│   ├── select_next.py          候选池过滤
│   ├── validate_script.py      6 件套 / 签名 / 黑话密度校验
│   ├── synthesize_alan_cpu.py  本地 GPT-SoVITS 克隆音色配音
│   ├── select_cover_frame.py   封面选帧
│   ├── gen_jimeng_cover_prompts.py  即梦图生图封面提示词
│   └── validate_publication_info.py 发布信息校验
├── references/
│   ├── edit-pipeline.md        剪辑流完整契约（算法血统 / 精度 / 限制）
│   ├── voiceover-workflow.md   配音流契约（参考音色 / 停顿 / 门禁）
│   └── cover-publish.md        封面与发布契约
├── vendor/                     只读依赖，不入库，版本见 vendor/README.md
│   ├── ffmpeg-skill/           剪辑执行层（MIT）
│   └── movie-narrator/         匹配算法参考（AGPL-3.0，未复制代码）
├── films/                      片目录（不入库）
└── .gitignore
```

## 环境与安装

**必需**

| 依赖 | 版本 | 说明 |
|---|---|---|
| Windows | 10/11 | PowerShell 7（`pwsh`） |
| Python | 3.11–3.13 | 只用标准库即可跑通全链路 |
| ffmpeg | ≥ 9.0 | 需要 `scdet` 滤镜与 `-fps_mode`（`-vsync` 已移除） |

**可选（决定精度，见下节）**

| 依赖 | 用途 | 装法 |
|---|---|---|
| `faster-whisper` | 配音强制对齐（替代 rough） | `pip install faster-whisper` |
| `whisperx` | 更高精度对齐 | `pip install whisperx` |
| `scenedetect[opencv]` | 更准的镜头切点 | `pip install "scenedetect[opencv]"` |
| `sentence-transformers` | 画面语义向量匹配 | `pip install sentence-transformers` |

**vendor 依赖**

```powershell
git clone --depth 1 https://github.com/kajisho5/ffmpeg-skill.git vendor/ffmpeg-skill
git -C vendor/ffmpeg-skill checkout f1c97cbffeac71b8fdfca2f790ceb00db3bcce65
git clone --depth 1 https://github.com/zcbacxc/movie-narrator.git vendor/movie-narrator
git -C vendor/movie-narrator checkout 4c7e81fedb9a0eec72257b15774a2bf5e2f2dd96
# 删掉嵌套 .git，否则会被当成嵌套仓库
Remove-Item -LiteralPath vendor\ffmpeg-skill\.git, vendor\movie-narrator\.git -Recurse -Force
```

版本与边界说明见 [`vendor/README.md`](vendor/README.md)。

## 快速开始

```powershell
# 1) 建片目录：稿子复制、原片/配音硬链接（同盘不占空间）
python scripts\edit\alan_edit.py init --name 血之海滩 --script 稿.txt --video 原片.mp4

# 2) 一条链跑完：读稿 → 配音 → 对齐 → 镜头 → 匹配 → 出片
python scripts\edit\alan_edit.py all --work "D:\@kaifa\Alan\films\血之海滩" --backend peiyin --run

# 3) 查看进度
python scripts\edit\alan_edit.py status --work "D:\@kaifa\Alan\films\血之海滩"
```

`all` 会跳过已存在的中间产物（`--force-voice` / `--force-shots` 可强制重跑）。只想看匹配结果不出片，`--steps script,voice,align,shots,match`。

## 各环节

### 选片

```powershell
python scripts\check_done.py "候选片名"          # 已解说库里是否已有
python scripts\select_next.py candidate.json      # 候选池批量过滤
```

选片先看女主（颜值身材是频道卖点），再看导演，最后看冷门度。无豆瓣评分 = 冷门加分；搜站确认无人解说。

### 写稿

按 6 件套起草：钩子 → 信息段 → 正片 → 「好了 电影结束」→ 点评（≤100 字）→ 互动 + 签名。
签名定版：`我是艾伦 一个[当期梗]的阿婆 好了 我要去遛狗了 下期更精彩哦`。

```powershell
python scripts\validate_script.py 稿.txt          # 6 件套 / 签名 / 黑话密度
```

暴力描写一律隐晦：拟声词 + 结果 + 「番茄汁 / 番茄酱」收尾，不写解剖细节。

### 配音

```powershell
# 默认：外部 PeiYin 项目
python scripts\edit\alan_edit.py voice --work <片目录> --backend peiyin

# 退回本地 GPT-SoVITS（speed 固定 1.0）
python scripts\edit\alan_edit.py voice --work <片目录> --backend alan

# 配音已存在，只做校验
python scripts\edit\alan_edit.py voice --work <片目录> --backend none
```

PeiYin 路径默认 `D:\@kaifa\PeiYin`，可用 `--peiyin-root` 或环境变量 `PEIYIN_ROOT` 覆盖。
产物统一为 `<片目录>/配音.wav`，下游不关心是谁合成的。

### 剪辑

```powershell
# 分步
python scripts\edit\alan_edit.py script --work <片目录>
python scripts\edit\alan_edit.py align  --work <片目录> --backend auto
python scripts\edit\alan_edit.py shots  --work <片目录> --backend auto
python scripts\edit\alan_edit.py match  --work <片目录>
python scripts\edit\alan_edit.py render --work <片目录> --csv --run
```

关键参数：

| 命令 | 参数 | 作用 |
|---|---|---|
| `align` | `--backend auto\|whisperx\|faster\|rough` | 对齐后端，`auto` 逐级降级 |
| `align` | `--model medium` | ASR 模型，中文解说建议 medium 起 |
| `shots` | `--scd-threshold 12` | ffmpeg 场景分数阈值（真实电影 10~15，静态素材 3~5） |
| `shots` | `--caption-backend openai` | 让 VLM 给每个镜头写 40 字画面描述 |
| `shots` | `--skip-intro 15` | 开头多少秒当片头，不参与匹配 |
| `match` | `--max-slot 5` | 单槽配音上限秒数（0 = 按镜头均值自动） |
| `match` | `--monotonic on` | 镜头随解说推进，不回跳 |
| `match` | `--absorb-gap 1.2` | 句间停顿并入上一句画面，防音画累积错位 |
| `render` | `--font-size 20` | ASS points，1080p 实际字高 ≈ size×3.75 |
| `render` | `--export-timeline edit.fcpxml` | 导出时间线进 Premiere / Resolve 返工 |

### 封面与发布

```powershell
python scripts\select_cover_frame.py 原片.mp4 --times 120,140,160
python scripts\gen_jimeng_cover_prompts.py --movie 片名 --out 片目录\封面\封面提示词-即梦.txt
python scripts\validate_publication_info.py 片目录
```

## 片目录与数据契约

```
films/<片名>/
├── 口播稿_定稿.txt      # 配音稿（人写；结构行会被 read_script 剔除）
├── 配音.wav             # 对齐与成片的唯一音源
├── 原片.mp4
├── final.mp4            # 成片（根目录只放交付物）
├── film.json
└── build/               # 全部中间产物，可随时删掉重算
    ├── segments.json    句级切分 + TTS 分段
    ├── 配音稿.txt        送 TTS 的段落稿（≤120 字 / 段）
    ├── voice.json
    ├── timeline.json     每句 start / end
    ├── subtitle.srt      句级字幕
    ├── shots.json        镜头表（start / end / dur / mid / caption）
    ├── edl.json          ★ 剪辑决策表
    ├── edl.csv           人工核对用
    ├── project.json      ffmpeg-skill 渲染工程
    └── render_work/      渲染中间文件
```

`edl.json` 的每个片段：

| 字段 | 含义 |
|---|---|
| `n` / `seg` / `sub` | 片段号 / 句号 / 句内子槽号 |
| `text` | 该槽对应的解说文字 |
| `narr_start` / `narr_end` / `narr_dur` | 配音时间轴上的位置与时长 |
| `src_start` / `src_end` / `src_dur` | 原片时间轴上的取景窗口 |
| `speed` | 播放倍速 = `src_dur / narr_dur`，恒在 `[0.85, 1.25]` |
| `shot` / `score` / `source` | 命中的镜头号 / 语义分 / 打分来源 |
| `expanded` | 是否因 clamp 扩/缩过窗口（可能跨切点） |

## 匹配精度分级（重要）

`match` 会按可用信号自动选档，实际用了哪档写在 `edl.json` 的 `stats.scorer`：

| 档位 | 条件 | 含义 |
|---|---|---|
| `temporal` | 镜头无画面描述 | 纯剧情时序先验，等于按比例猜 |
| `keyword` | 有描述、无向量模型 | 中文 2-gram 重叠 0.65 + 时序 0.35 |
| `embed` | 有描述 + `sentence-transformers` | 语义余弦 0.75 + 时序 0.25 |

**想要"精准配画面"，必须先补两件事**：

```powershell
# ① 给每个镜头写画面描述（覆盖率 <70% 会自动退回 temporal）
python scripts\edit\alan_edit.py shots --work <片目录> --caption-backend openai `
  --caption-base-url $env:ALAN_VLM_BASE_URL --caption-key $env:ALAN_VLM_KEY

# ② 装向量模型，让描述真正参与匹配
pip install sentence-transformers
```

同理，`align` 的 `rough` 只用于跑通结构，正式出片要装 `faster-whisper`（±0.5s 以上的漂移会让画面提前或滞后）。

## 匹配算法

血统是 [`movie-narrator`](vendor/movie-narrator) 的 `pipeline/match`，保留四条：act 分区（0.15 / 0.25 / 0.40 / 0.20）、贪心 topk + 复用惩罚、窗口 clamp、滑动窗口多样性换镜。

针对电影解说改了三处：

1. **长句拆槽** —— 一句 8~18 s、镜头均 3~6 s，原实现一句只配一镜靠 1.25 倍变速硬撑必然超速；现在按标点切成 `ceil(句长 / max_slot)` 个子槽各自选镜，同句内源时间递增。
2. **句间停顿吸收** —— 句间 0.18 s、段间 0.35 s、场景间 1.0 s 没有解说词但画面不能停，并入上一句尾槽，否则片段累计比配音短、音画一路错位。
3. **叙事游标** —— 期望位置取"解说进度"与"上一镜中点"的较大值，镜头只前进不倒退；纯时序打分时位置差按 18% 片长归一，避免复用惩罚盖过位置优势导致跳镜（实测会 0→1→0→2）。

## 设计取舍：为什么是"自建匹配层 + ffmpeg-skill 执行"

- `ffmpeg-skill` 是**纯执行层**，其文档原文 "does not reason, plan, decide"，`scenes.py --highlights` 也明写 "ranks by loudness, not meaning"——它不会按解说语义选画面。
- `movie-narrator` 有 `detect_scenes → match_clips` 与时间线导出，但自产稿、自 TTS，且一句一镜、无长句拆槽。
- 现成的"人写稿 + 人配音 + 精准配画面"产品，市面上没有。

所以：稿与配音留在本地生产管线，画面决策自建（`match_edl.py`），执行交给成熟的 `ffmpeg-skill`，返工走 `--export-timeline`。

## 成片规格

| 项 | 值 |
|---|---|
| 画面 | 1920×1080 / 30fps / H.264 / yuv420p / bt709 |
| 音量 | -14 LUFS，真峰值 ≤ -1 dBTP（渲染后自动复核，欠调会补一次校准） |
| 字幕 | 句级 SRT → 硬字幕，白字黑描边，底部居中，最多 2 行，`Microsoft YaHei` |
| 转场 | 默认无（fade 0.5 会吃掉每个切口 0.5 s，总长就对不上配音） |

## 已知限制

- **对齐**：无 ASR 时 `rough` 按字数比例切，只能用来跑通结构。
- **镜头检测**：pyscenedetect 未装时用 ffmpeg `scdet`；暗场切换可能漏检（漏检只让镜头偏长，不毁 EDL）。
- **字幕字体**：Windows 默认 `Microsoft YaHei`；换字体需确认系统已安装，否则中文变方块。
- **配音静音**：`loudness.py` 会拒绝处理静音轨（这是正确行为）。真实配音不会遇到；用静音 wav 做占位测试时，质检会判 `loudness FAIL`，属于预期。
- **许可**：`vendor/movie-narrator` 为 AGPL-3.0，本项目只借鉴算法思路、未复制其代码；`vendor/ffmpeg-skill` 为 MIT。

## 常见问题

**成片比配音短/长？** 检查 `match` 的 `--absorb-gap`（默认 1.2 s）是否能覆盖句间与场景停顿；`edl.json` 的 `warnings` 会写"留白 x s，画面会比配音短"。

**所有片段的 speed 都是 1.25？** 说明原片镜头普遍长于单槽（如 11 s 镜头配 5 s 槽），clamp 只能收缩到 1.25。真实素材镜头均 3~6 s 时 speed 会接近 1.0。

**渲染报 `loudness FAIL`？** loudnorm 的 linear 模式在真峰值受限时会欠调 1~2 dB；`render_edl.py` 会自动补跑一次校准，仍失败则手工 `loudness.py -I -14 --tp -1`。

**字幕太大/太小？** `caption.py` 的 `--size` 按 288p 脚本缩放，1080p 实际字高 ≈ size×3.75。20 ≈ 75 px。

**`ffmpeg` 报 `Unrecognized option 'vsync'`？** ffmpeg 9 已移除该参数，本仓库统一用 `-fps_mode passthrough`，升级脚本即可。

## 开发与自测

- 纯标准库可跑通全链路，重依赖全部 `try import` 降级，不会因缺包直接崩。
- 自测素材可用 ffmpeg 合成：多段纯色视频 + `anullsrc`/`sine` 配音，分别验切点、拆槽、音量与字幕。
- 代码约定：中间产物一律 JSON + UTF-8，编码读取必须探测（老稿 GBK / UTF-8+BOM 混用）；所有时间用秒（float），只在写 ffmpeg 参数时转 `m:ss.mmm`。

```powershell
# 语法自检
python -m py_compile (Get-ChildItem scripts\edit -Filter *.py).FullName
```

## 依赖与许可

- 本仓库未附 LICENSE 文件。
- `vendor/ffmpeg-skill`：MIT。
- `vendor/movie-narrator`：AGPL-3.0（详见 [`vendor/README.md`](vendor/README.md)）。
- 解说稿、配音、封面素材的版权与平台规则由使用者自行负责。

---

[ffmpeg-skill]: vendor/README.md
