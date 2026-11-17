# PeiYin / dianying 管线配音契约（Alan 侧）

Alan 的成片配音默认走 PeiYin 的 dianying 管线（dabao 克隆音色），不在 Alan 侧另养一套音色参数。
本文件是 2026-11 同步过来的最新参数与阅读约定；改参数一律改 PeiYin 的 preset，不要改这里抄一份。

## 一条命令

```powershell
# 推荐：走 Alan 的编排（自动把配音稿、元数据放对位置）
python scripts\edit\alan_edit.py voice --work "<片目录>" --backend peiyin
```

等价于直接调 dianying 管线：

```powershell
D:\@kaifa\PeiYin\GPT-SoVITS\.venv\Scripts\python.exe -X utf8 `
  D:\@kaifa\PeiYin\GPT-SoVITS\dabao_tts.py `
  --text-file "<片目录>\build\配音稿.txt" `
  --out "<片目录>\配音.wav" --force
```

- 产物：`<片目录>/配音.wav`（pcm_s16le 44.1kHz 单声道）+ 同名 `.json`（分段与生效参数）；
  `voiceover.py` 会把 json 挪到 `build/voice_peiyin.json`，片目录根只留 wav。
- dianying 引擎会自动拉起本机 GPT-SoVITS 服务，首次约 1 分钟，之后逐段合成。

## 锁定参数（`voices/dabao/preset.json`，2026-11 定稿）

| 项 | 值 |
|---|---|
| 模型 / 音色 | gpt-sovits-v5turbo / `dabao`（艾伦男声） |
| speed | 1.0（固定，不要用 `--speed` 另设） |
| temperature / top_p / top_k | 0.9 / 0.9 / 20 |
| repetition_penalty | 1.3 |
| fragment_interval | 0.2 s |
| max_chunk_chars / split | 150 字 / cut1 |
| 句间保留静音 keep_gap | 100 ms |
| 可压缩静音判定 min_gap | 150 ms |
| 静音阈值 / 噪声门 / 门内保留 | -40 dB / -33 dB / 0.3 |
| 段间补 gap | 20 ms |
| 采样 / 格式 | 44.1 kHz 单声道 / wav |

`build/voice.json` 的 `params` 会记录本次实际生效值（engine/model/speed/temp/top_p/top_k/rep/fragment/max_chunk/gap/gate），排障先看它。

## 阅读约定（写作与改稿都要遵守）

- **数字写中文**：一九七一年、十三个人、第九十四，不写 1971 / 13 / 94。
- **外国人名连读**：引擎把「·」当断句点，每个点多停约 0.2 s。合成前 `strip_name_dots` 会自动删掉夹在两个汉字之间的间隔号，`马里奥·巴瓦` 读作「马里奥巴瓦」。**稿子里照常写「·」用于显示**，不要把去点后的名字写进源稿。
- **段首/段尾独立短句要并句**：`先交代一下背景。` `重头戏在这儿。` 这类短句容易被整句吞掉，TTS 稿里改成逗号并入后一句。
- **英文缩写/片名按中文音读**：必要时在 PeiYin preset 的 `speak_fixes` 里加一条替换（如 IndieWire → 独立连线），别在稿子里写英文让模型猜。

## 交付前核对（必做）

1. 读 `build/voice_peiyin.json` 的 `chunks[].spoken`：应无「·」残留，人名连续。
2. 每段字数与时长比对：字数明显偏少的那段就是被吞了，改文本重配。
3. 需要质检门禁时加 `--check`，跑 `PeiYin\scripts\check_dabao_audio.ps1`。
4. 试听开头 20 秒 + 抽听人名/人名密集处。

## 可选：段落模式

```powershell
python scripts\edit\alan_edit.py voice --work "<片目录>" --backend peiyin --paragraph-gap-ms 200
```

走 `PeiYin\scripts\synthesize_dabao_paragraphs.py`：按空行切段、每段单独合成再拼，段间留固定停顿，长片分节呼吸感更好。默认 `0` = dianying 直连（一次成片，停顿全走 preset）。

## 环境

- PeiYin 根目录默认 `D:\@kaifa\PeiYin`，可用 `--peiyin-root` 或 `PEIYIN_ROOT` 覆盖。
- 需要本机 GPT-SoVITS（`GPT-SoVITS\dabao_tts.py` + `.venv`）与 ffmpeg（preset 里的 `runtime/ffmpeg.exe` 优先）。
- 音色参考音频是 Git LFS 文件，缺失时引擎会直接报错，别静默降级到别的音色。
