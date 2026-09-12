# Alan 配音工作流（GPT-SoVITS 克隆音色）

艾伦解说稿 → 克隆音色配音的标准流程。2026-09-12 定版,第一段验收通过(夺命舞会)。

## 固定环境

- GPT-SoVITS 根目录:`D:\@佳康顺矩阵\@工具\GPT-SoVITS`(用 `.venv\Scripts\python.exe`,CPU 推理)
- 推理配置 `GPT_SoVITS\configs\tts_infer.yaml` 必须是 `device: cpu` / `is_half: false` / `version: v2`
- 参考音色源:`D:\BaiduSyncdisk\18 艾伦全自动解说\克隆音色\dabao3.wav`
  (14.1s,44.1kHz 立体声;干净段 6.48–13.96s,脚本自动裁剪 + 转 32k 单声道)
- 提示文本(与参考片段逐字匹配,**用户亲笔转写,勿改**):
  `准备迎接最大挑战，理论上斯大林仍是希特勒的盟友，罗马尼亚、保加利亚和匈牙利是德国的坚定盟友。`

## 标准命令

```powershell
& 'D:\@佳康顺矩阵\@工具\GPT-SoVITS\.venv\Scripts\python.exe' `
  '<alan>\scripts\synthesize_alan_cpu.py' `
  --text '<配音稿.txt>' `
  --name '<中文片名>'
```

- 默认语速 **1.0**(2026-09-12 用户定版;要 1.1× 显式传 `--speed 1.1`)
- 成品写在配音稿同目录:`<片名>_艾伦音色_CPU_大段落_1.0倍速_句间停顿缩短.wav`
- 中间产物(RAW/segments/配音稿_大段落.txt/配音配置.json/progress.log)在 `<同目录>\配音\`
- 长稿(CPU 约 0.5 分钟/200 字)用后台运行 + 日志重定向;断点续接=删掉 `配音\segments` 里
  已完成的段落数之外的部分后重跑会全量重来,所以长稿建议按"段落分块文本"分次跑再拼

## 质检门禁(全部通过才算完成)

1. 成品 32kHz / 单声道 / PCM16,峰值 <1.0,`clipped_samples=0`(脚本自动检查,失败即抛)
2. 单独试听/ASR 复听开头 2–5 秒:拖音、慢起音、语义重复 = 随机推理异常,只重配第一段
   (换 seed:`--seed-base` ±1;或 temperature 0.82 / top_p 0.95 / repetition_penalty 1.50)
3. ASR 回听逐句核对吐字。**判错标准 = 拼音显著偏离**;同音/近音/拟声词差异是 ASR 误听:
   - whisper small 在 1.0–1.1× 语速下大量近音字误报(喘息声→船牺牲),不能据此判 TTS 错
   - 仲裁用 medium(int8 CPU,先 ffmpeg 截可疑区间 20s 再听,整段会超时)或 FunASR
   - 实测易误听类:衣衫半解→一山半界 / 番茄汁糊了→狐狸一 / 猛踩油门→蒙彩油门(均发音正确)
4. 某段错读只重配该段(分段重跑)再拼接,不必全量重跑

## 换参考音色

换人声时:选 4–10s 单人无噪音无 BGM 无截断片段,提示文本必须与音频逐字一致
(用户转写为准,ASR 转写只能做校验——实测 ASR 把「乡间别墅」写成「香荆别墅」)。
命令传 `--reference <wav> --prompt-text '<逐字文本>'`;源音频是长录音时用
`--ref-start/--ref-end` 指定干净段(silencedetect 找静音点),已裁剪短片整段自动使用。
