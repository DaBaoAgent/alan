<!-- README-PROMO:START -->
<p align="center">
  <img src="assets/readme/hero.webp" alt="ALAN 艾伦：电影解说全流程工作台" width="100%" />
  <img src="assets/readme/workflow.webp" alt="ALAN 工作流：选片、查重、写稿、配音、剪辑、封面发布" width="100%" />
  <img src="assets/readme/beginner.webp" alt="ALAN 新手上手：选片、写稿、成片" width="100%" />
</p>
<!-- README-PROMO:END -->

# ALAN 艾伦 — 电影解说全流程工作台

B站/抖音电影解说 UP 主「艾伦」的一条完整生产线：**选片 → 查重 → 写口播稿 → 校验 → 配音 → 剪辑成片 → 封面与发布信息**。

不是"一键生成解说视频"的黑盒：稿子由人写，音色由固定克隆音色合成，画面由剪辑决策表（EDL）精确驱动，每一步的中间产物都是可读、可改、可重跑的 JSON。

- **稿子**：艾伦亲笔风格，6 件套结构，3800–5200 字
- **配音**：默认调外部 `PeiYin` 项目（dabao 克隆音色）；想换音色时退回本地 GPT-SoVITS
- **剪辑**：自建匹配层做"句 → 镜头"决策，`ffmpeg-skill` 纯执行
- **封面与发布**：调外部 `fengmian` 项目出两张封面提示词 + 两行制发布信息，过交付门禁

<p align="center">
  <img src="https://img.shields.io/badge/频道定位-全网首发-FF2449" alt="Position">
  <img src="https://img.shields.io/badge/目标-200%20部全网首发-6B4EFF" alt="Goal">
  <img src="https://img.shields.io/badge/已解说库-82%20部-3776AB" alt="Library">
  <img src="https://img.shields.io/badge/Agent%20Skill-Codex%20%7C%20Claude%20Code%20%7C%20Hermes-2ea44f" alt="Skill">
  <img src="https://img.shields.io/badge/license-MIT-2ea44f" alt="License">
</p>

**频道定位**：**全网首发**冷门经典恐怖 / 铅黄（Giallo）/ 剥削（B 级）片，目标 200 部全网首发。
文风与选片标准全部从艾伦亲笔的 **63 篇解说稿**逐条提炼。

---

## 何时使用

| 说法 | 触发流程 |
|---|---|
| "帮我选片 / 推荐一部没解说过的恐怖片" | 选片流 |
| "写解说稿 / 按艾伦风格写一篇" | 写稿流 |
| "这部片艾伦解说过吗" | 查重 |
| "配音 / 合成语音 / 克隆音色读稿" | 配音流 |
| "剪辑 / 配画面 / 把这篇稿做成成片" | 剪辑流 |
| "生成封面 / 发布信息" | 封面发布流 |

---

## 一、选片标准

1. **题材范围**：意大利/西班牙铅黄 Giallo、70-80 年代 B 级恐怖、剥削片、Hammer 吸血鬼、slasher、冷门科幻恐怖；延伸经典恐怖/惊悚/夺宝探险/西部。
2. **硬性调性**：**女主颜值/身材必须在线**，裸露戏份是加分项。
3. **全网首发**：中文区没人完整解说过。选片必须 ① 跑 `scripts/check_done.py` 查已解说库 ② 豆瓣查是否有评分/是否已有 UP 主解说。
4. **质量底线**：IMDB 先筛演员（个人评分 5+）保证下限，再筛导演（导演评分 8+）保证上限。
5. **片源可得性**：能找到蓝光/修复版生肉。
6. **系列补拍机会**：已做续集的可以回头做第一部。

---

## 二、解说稿文风规范

### 结构模板（6 件套）

1. **开场钩子**：2-4 句名场面白描，短句堆叠悬念，**不能第一句就报片名**。钩子段角色一律匿名（用"女孩/小伙"指代）。
2. **影片信息段**："今天艾伦的全网首发/细读经典，带来 [年份]年上映的[国家][类型]《片名》……" —— 卡司只报【女主】+【男主】，配角一律不报名字。
3. **正片解说**：第三人称逐场景叙事，短句为主、一句一行，人物用外号。
4. **结尾句**："好了 电影结束"。
5. **点评段**：≤100 字，槽点半句 + 亮点半句 + 烂片指数或分数收尾。
6. **互动+签名**：互动 + 固定签名 **"我是艾伦 一个[当期梗]的阿婆 好了 我要去遛狗了 下期更精彩哦"**。

### 开场美女钩子规律（63 篇实测）

频道钩子 = **美色开路**。63 篇中开头两句内含美色招牌的约 32 篇（每 2 篇就有 1 篇）：

- **机制 A：场景美色钩** —— 梳妆/更衣/泳装型、身体慢镜+偷窥型、情色张力+险型。**铁律**：美色镜头最多 2-4 句，第 3-5 句必须"变"（危险逼近/悬念/意外）。
- **机制 B：信息段女色招牌** —— 第一句直接砸女色标签（女星头衔句式 / 阵容密度句式 / 擦边预告句式）。

### 语言特征

- 短句一行一句，口语感叹词：好家伙/哎呀/我的天/乖乖/噗呲/咔咔
- **叙述一律第三人称**，角色台词转述为间接引语
- **血腥黑话**：番茄酱/番茄汁 = 血；死亡动词一律隐晦（嗝屁/归西/没了/挂了/领盒饭…）；**"杀手"名词可用**
- **角色命名法**：男主 = 玛德，男二 = 法克，男三 = 谢特；女主 = 侯丽，女二 = 幂幂
- **裸露尺度词**：禁直白词，一律用"你们都懂的原因""能给的都给了""多豁得出去"

### 字数纪律

- 成稿目标 **3800–5200 字**（63 篇中位≈4300），硬界 2500–8000
- 开场钩子 **60–110 字**

---

## 三、全流程

```
选片 ──► 写稿 ──► 校验 ──► 配音 ──► 对齐 ──► 镜头表 ──► 匹配 ──► 渲染 ──► 封面/发布
 │        │        │        │         │          │          │         │
查重   6件套    结构与    PeiYin   句级时间   切点检测   生成 EDL  ffmpeg-skill   fengmian
     黑话密度   签名     GPT-SoVITS timeline  shots.json  edl.json   project.json   封面+发布信息
                                                                        │
                                                                    final.mp4
```

七个剪辑/交付步骤对应 `scripts/edit/` 下的脚本，用 `alan_edit.py` 统一调度。

### 1. 选片

```bash
python scripts/check_done.py "候选片名"          # 查重（支持中/英/别名模糊匹配）
python scripts/select_next.py <candidate.json>   # 批量过滤候选池
```

### 2. 写稿

```bash
python scripts/validate_script.py <稿.txt>   # 校验 6 件套 + 签名格式 + 黑话密度
```

### 3. 配音

```bash
# 默认：外部 PeiYin 项目（dabao 克隆音色，段间停顿与质检门禁都在那边）
python scripts/edit/alan_edit.py voice --work "<片目录>" --backend peiyin

# 退路：本地 GPT-SoVITS（CPU，语速固定 1.0）
python scripts/edit/alan_edit.py voice --work "<片目录>" --backend alan

# 已有配音只是校验
python scripts/edit/alan_edit.py voice --work "<片目录>" --backend none
```

PeiYin 路径默认 `D:\@kaifa\PeiYin`，可用 `--peiyin-root` 或环境变量 `PEIYIN_ROOT` 覆盖。
配音产物固定为 `<片目录>/配音.wav`，下游不关心是谁合成的。

### 4. 剪辑

```bash
# 建片目录（稿子复制、原片/配音硬链接，同盘不占空间）
python scripts/edit/alan_edit.py init --name 片名 --script 稿.txt --video 原片.mp4

# 一条链：读稿 → 配音 → 对齐 → 镜头 → 匹配 → 出片 → 封面/发布
python scripts/edit/alan_edit.py all --work "D:\@kaifa\Alan\films\片名" --backend peiyin --run

# 分步
python scripts/edit/alan_edit.py script --work <片目录>
python scripts/edit/alan_edit.py align  --work <片目录> --backend auto
python scripts/edit/alan_edit.py shots  --work <片目录> --backend auto
python scripts/edit/alan_edit.py match  --work <片目录>
python scripts/edit/alan_edit.py render --work <片目录> --csv --run
python scripts/edit/alan_edit.py cover  --work <片目录>

# 查看进度
python scripts/edit/alan_edit.py status --work <片目录>
```

关键参数：

| 命令 | 参数 | 作用 |
|---|---|---|
| `align` | `--backend auto\|whisperx\|faster\|rough` | 对齐后端，逐级降级 |
| `align` | `--model medium` | ASR 模型，中文解说建议 medium 起 |
| `shots` | `--scd-threshold 12` | ffmpeg 场景分数阈值（真实电影 10~15，静态素材 3~5） |
| `shots` | `--caption-backend openai` | 让 VLM 给每个镜头写 40 字画面描述 |
| `shots` | `--skip-intro 15` | 开头多少秒当片头，不参与匹配 |
| `match` | `--max-slot 5` | 单槽配音上限秒数（0 = 按镜头均值自动） |
| `match` | `--monotonic on` | 镜头随解说推进，不回跳 |
| `match` | `--absorb-gap 1.2` | 句间停顿并入上一句画面，防音画累积错位 |
| `render` | `--font-size 20` | ASS points，1080p 实际字高 ≈ size×3.75 |
| `render` | `--export-timeline edit.fcpxml` | 导出时间线进 Premiere / Resolve 返工 |

### 5. 封面与发布信息

由 `scripts/edit/publish.py` 调外部 `fengmian` 完成（`vendor/fengmian`）：

```bash
# 只看能抽出什么：建议主标 / 副标 / 话题 / 钩子 / 数字
python scripts/edit/publish.py --work "<片目录>" --analyze

# 定稿：主标 6 字、副标 8 字、标题两段式 ≤25 字、恰好 4 个话题
python scripts/edit/publish.py --work "<片目录>" \
  --main "阴风阵阵老宅" --sub "修女的血色诅咒夜" \
  --title "阴风阵阵：1977年最邪的一栋房子" \
  --tags "#阴风阵阵 #铅黄电影 #恐怖片 #艾伦解说"

# 配了 ARK_API_KEY 可直出两张封面（2048×1536 / 1536×2048）
python scripts/edit/publish.py --work "<片目录>" --covers ark
```

产物落点：

| 文件 | 位置 | 说明 |
|---|---|---|
| `发布信息.txt` | 片目录根 | 两行制：标题 + 4 个话题 |
| `封面-4比3.png` / `封面-3比4.png` | 片目录根 | 6 字金黄主标 + 8 字白色副标 |
| `封面提示词-4比3.txt` / `-3比4.txt` | `build/` | 出图提示词，中间产物不入交付根 |
| `封面元信息.json` | `build/` | 主标/副标/风格/场景/钩子来源 |

交付门禁沿用 fengmian 的规则：交付根只允许成片、两张正式封面、`发布信息.txt` 与子目录，其余含"封面/cover/即梦/提示词"的文件一律拦。

> 项目里还留着早期的 `select_cover_frame.py`（抽帧打分）、`gen_jimeng_cover_prompts.py`（旧提示词模板）、`validate_publication_info.py`（旧规则：5 个话题）。新链路以 `publish.py` + fengmian 为准（**4 个话题**），旧脚本只在需要抽帧参考图时用。

---

## 四、剪辑流水线详解

### 片目录与数据契约

```
films/<片名>/
├── 口播稿_定稿.txt      # 配音稿（人写；结构行会被 read_script 剔除）
├── 配音.wav             # 对齐与成片的唯一音源
├── 原片.mp4
├── final.mp4            # 成片（根目录只放交付物）
├── 封面-4比3.png        # 封面（publish 出图后）
├── 封面-3比4.png
├── 发布信息.txt         # 两行制发布信息
├── film.json
└── build/               # 中间产物，删掉可随时重算
    ├── segments.json    句级切分 + TTS 分段
    ├── 配音稿.txt        送 TTS 的段落稿（≤120 字 / 段）
    ├── voice.json
    ├── timeline.json     每句 start / end
    ├── subtitle.srt      句级字幕
    ├── shots.json        镜头表（start / end / dur / mid / caption）
    ├── edl.json          ★ 剪辑决策表
    ├── edl.csv           人工核对用
    ├── project.json      ffmpeg-skill 渲染工程
    ├── 封面提示词-*.txt  封面提示词（publish 写）
    ├── 封面元信息.json
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

### 匹配精度分级（重要）

`match` 按可用信号自动选档，实际用了哪档写在 `edl.json` 的 `stats.scorer`：

| 档位 | 条件 | 含义 |
|---|---|---|
| `temporal` | 镜头无画面描述 | 纯剧情时序先验，等于按比例猜 |
| `keyword` | 有描述、无向量模型 | 中文 2-gram 重叠 0.65 + 时序 0.35 |
| `embed` | 有描述 + `sentence-transformers` | 语义余弦 0.75 + 时序 0.25 |

**想要"精准配画面"，必须先补两件事**：

```bash
# ① 给每个镜头写画面描述（覆盖率 <70% 会自动退回 temporal）
python scripts/edit/alan_edit.py shots --work <片目录> --caption-backend openai \
  --caption-base-url $ALAN_VLM_BASE_URL --caption-key $ALAN_VLM_KEY

# ② 装向量模型，让描述真正参与匹配
pip install sentence-transformers
```

同理，`align` 的 `rough` 只用于跑通结构，正式出片要装 `faster-whisper`（±0.5s 以上的漂移会让画面提前或滞后）。

### 算法与三处改造

血统是 [`movie-narrator`](vendor/README.md) 的 `pipeline/match`，保留四条：act 分区（0.15 / 0.25 / 0.40 / 0.20）、贪心 topk + 复用惩罚、窗口 clamp、滑动窗口多样性换镜。

针对电影解说改了三处：

1. **长句拆槽** —— 一句 8~18 s、镜头均 3~6 s，原实现一句只配一镜靠 1.25 倍变速硬撑必然超速；现在按标点切成 `ceil(句长 / max_slot)` 个子槽各自选镜，同句内源时间递增。
2. **句间停顿吸收** —— 句间 0.18 s、段间 0.35 s、场景间 1.0 s 没有解说词但画面不能停，并入上一句尾槽，否则片段累计比配音短、音画一路错位。
3. **叙事游标** —— 期望位置取"解说进度"与"上一镜中点"的较大值，镜头只前进不倒退；纯时序打分时位置差按 18% 片长归一，避免复用惩罚盖过位置优势导致跳镜（实测会 0→1→0→2）。

### 为什么是"自建匹配层 + ffmpeg-skill 执行"

- `ffmpeg-skill` 是**纯执行层**，文档原文 "does not reason, plan, decide"，`scenes.py --highlights` 也明写 "ranks by loudness, not meaning"——它不会按解说语义选画面。
- `movie-narrator` 有 `detect_scenes → match_clips`，但自产稿、自 TTS，且一句一镜、无长句拆槽。
- 现成的"人写稿 + 人配音 + 精准配画面"产品，市面上没有。

所以：稿与配音留在本地生产管线，画面决策自建（`match_edl.py`），执行交给成熟的 `ffmpeg-skill`，返工走 `--export-timeline`。

### 成片规格

| 项 | 值 |
|---|---|
| 画面 | 1920×1080 / 30fps / H.264 / yuv420p / bt709 |
| 音量 | -14 LUFS，真峰值 ≤ -1 dBTP（渲染后自动复核，欠调会补一次校准） |
| 字幕 | 句级 SRT → 硬字幕，白字黑描边，底部居中，最多 2 行，`Microsoft YaHei` |
| 转场 | 默认无（fade 0.5 会吃掉每个切口 0.5 s，总长就对不上配音） |

---

## 五、环境与安装

**必需**

| 依赖 | 版本 | 说明 |
|---|---|---|
| Windows | 10/11 | PowerShell 7（`pwsh`） |
| Python | 3.11–3.13 | 精细剪辑链路只用标准库即可跑通 |
| ffmpeg | ≥ 9.0 | 需要 `scdet` 滤镜与 `-fps_mode`（`-vsync` 已移除） |
| Node.js | ≥ 18 | 仅 `--covers ark` 直出封面时需要 |

**可选（决定精度）**

| 依赖 | 用途 | 装法 |
|---|---|---|
| `faster-whisper` | 配音强制对齐（替代 rough） | `pip install faster-whisper` |
| `whisperx` | 更高精度对齐 | `pip install whisperx` |
| `sentence-transformers` | 画面语义向量匹配 | `pip install sentence-transformers` |
| `Pillow` | fengmian 落盘归一封面尺寸 | `pip install Pillow` |

**外部项目 / vendor**

| 依赖 | 位置 | 作用 |
|---|---|---|
| `PeiYin` | `D:\@kaifa\PeiYin`（`--peiyin-root` 可改） | 配音：dabao 克隆音色段落合成 |
| `vendor/ffmpeg-skill` | 本仓库 | 剪辑执行 |
| `vendor/movie-narrator` | 本仓库 | 匹配算法参考 |
| `vendor/fengmian` | 本仓库 | 封面与发布信息 |

```powershell
git clone --depth 1 https://github.com/kajisho5/ffmpeg-skill.git vendor/ffmpeg-skill
git -C vendor/ffmpeg-skill checkout f1c97cbffeac71b8fdfca2f790ceb00db3bcce65
git clone --depth 1 https://github.com/zcbacxc/movie-narrator.git vendor/movie-narrator
git -C vendor/movie-narrator checkout 4c7e81fedb9a0eec72257b15774a2bf5e2f2dd96
git clone --depth 1 https://github.com/DaBaoAgent/fengmian.git vendor/fengmian
git -C vendor/fengmian checkout 651c011c63fac9caab3ab8e8abd20d2d1cccc6b4
# 删掉嵌套 .git，否则会被当成嵌套仓库
Remove-Item -LiteralPath vendor\ffmpeg-skill\.git, vendor\movie-narrator\.git, vendor\fengmian\.git -Recurse -Force
```

版本、许可与边界见 [`vendor/README.md`](vendor/README.md)。

---

## 六、目录结构

```
Alan/
├── README.md                   本文件
├── SKILL.md                    技能主入口：选片标准 / 文风规范 / 各流程入口
├── assets/readme/              README 配图
├── scripts/
│   ├── edit/                   生产主链（本仓库核心）
│   │   ├── alan_edit.py        统一 CLI：init / script / voice / align / shots / match / render / cover / all / status
│   │   ├── common.py           编码探测、ffprobe、时间格式、文本清洗
│   │   ├── read_script.py      口播稿 → 句级 segments.json + TTS 分段稿
│   │   ├── voiceover.py        配音（PeiYin / 本地 GPT-SoVITS）
│   │   ├── align_voice.py      配音 → 句级 timeline.json + SRT
│   │   ├── shot_table.py       原片 → shots.json（可选 VLM 画面描述）
│   │   ├── match_edl.py        匹配 → edl.json
│   │   ├── render_edl.py       edl → ffmpeg-skill project.json → final.mp4
│   │   └── publish.py          封面 + 发布信息（调 vendor/fengmian）
│   ├── check_done.py           已解说库查重
│   ├── select_next.py          候选池过滤
│   ├── validate_script.py      6 件套 / 签名 / 黑话密度校验
│   ├── synthesize_alan_cpu.py  本地 GPT-SoVITS 克隆音色配音
│   ├── select_cover_frame.py   早期封面选帧（抽帧打分）
│   └── gen_jimeng_cover_prompts.py  早期即梦封面提示词
├── references/
│   ├── edit-pipeline.md        剪辑流完整契约（算法 / 精度 / 限制）
│   ├── voiceover-workflow.md   GPT-SoVITS 配音契约
│   └── cover-publish.md        早期封面与发布契约
├── vendor/                     只读依赖，不入库，版本见 vendor/README.md
├── films/                      片目录（不入库）
└── .gitignore
```

---

## 七、常见坑

- **中文老片 txt 混合编码**：解说稿大部分 GBK、少数 UTF-8+BOM，读取必须自动探测，直接按 UTF-8 读会乱码。
- 选片优先查**女主**（颜值身材是频道卖点），其次导演，其次冷门度。
- 生肉片源翻译量大，写稿前确认原片已到手，别对着 IMDB 简介编剧情。
- **暴力描写一律隐晦**：不写解剖细节，套路 = 拟声词 + 结果 + 番茄酱收尾。
- 评分制："烂片指数 10 分满分"时**分数越低越神**，别写反。

**剪辑与交付**

- **成片比配音短/长**：检查 `match --absorb-gap`（默认 1.2 s）是否覆盖句间与场景停顿；`edl.json` 的 `warnings` 会写"留白 x s，画面会比配音短"。
- **所有片段 speed 都是 1.25**：原片镜头普遍长于单槽（如 11 s 镜头配 5 s 槽），clamp 只能收缩到 1.25；真实素材镜头均 3~6 s 时会接近 1.0。
- **渲染报 `loudness FAIL`**：loudnorm 的 linear 模式在真峰值受限时会欠调 1~2 dB，`render_edl.py` 会自动补跑一次校准；仍失败则手工 `loudness.py -I -14 --tp -1`。
- **字幕太大/太小**：`caption.py` 的 `--size` 按 288p 脚本缩放，1080p 实际字高 ≈ size×3.75；20 ≈ 75 px。
- **`Unrecognized option 'vsync'`**：ffmpeg 9 已移除该参数，统一用 `-fps_mode passthrough`。
- **封面主标必须 6 字、副标 8 字**：不符时 `publish.py` 只出发布信息、不生成提示词，用 `--main` / `--sub` 定稿再跑。
- **发布信息恰好 4 个话题**：这是 fengmian 的硬校验，旧脚本 `validate_publication_info.py` 的 5 话题规则已不适用于新链路。

---

## 八、参考文件

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 全部规则主入口（选片 / 文风 / 各流程） |
| `scripts/done_movies.json` | 已解说 82 部电影索引（中/英名、年份、导演、女主） |
| `scripts/check_done.py` | 查重脚本 |
| `scripts/select_next.py` | 候选池过滤脚本 |
| `scripts/validate_script.py` | 稿子结构校验脚本 |
| `scripts/edit/alan_edit.py` | 生产链统一入口（七步 + status） |
| `references/edit-pipeline.md` | 剪辑完整契约（算法血统 / 长句拆槽 / 三档精度 / 已知限制） |
| `scripts/synthesize_alan_cpu.py` | GPT-SoVITS 克隆音色配音（CPU，语速 1.0） |
| `references/voiceover-workflow.md` | GPT-SoVITS 配音契约（参考音色 / 质检门禁） |
| `vendor/fengmian/README.md` | 封面与发布信息的规格、风格预设、门禁规则 |
| `scripts/edit/publish.py` | 调 fengmian 出封面提示词 + 发布信息 |
| `scripts/select_cover_frame.py` | 早期封面选帧（抽帧 + 图像统计打分） |
| `scripts/gen_jimeng_cover_prompts.py` | 早期即梦封面提示词模板 |
| `scripts/validate_publication_info.py` | 早期发布信息校验（5 话题） |

---

## License

MIT

第三方依赖各自按其许可：`vendor/ffmpeg-skill` 与 `vendor/fengmian` 为 MIT，`vendor/movie-narrator` 为 AGPL-3.0（本项目只借鉴算法思路，未复制其代码）。解说稿、配音、封面素材的版权与平台规则由使用者自行负责。
