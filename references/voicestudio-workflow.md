# Alan 配音工作流（VoiceStudio）

本项目已将旧版 GPT-SoVITS 配音入口替换为 `scripts/voicestudio_alan.py`。VoiceStudio 是本地桌面应用：应用运行时，API 位于 `http://127.0.0.1:3900/v1`；不使用尚未发布的云端 API。

## 首次建音色

1. 启动 VoiceStudio，并确认 `python scripts/voicestudio_alan.py health` 返回 `status: ok`。
2. 在目标项目目录创建 profile。默认参考音频就是用户指定的 `D:\BaiduSyncdisk\4 @数字人剪辑\大宝Agent\大宝1.1.mp3`：

```powershell
python scripts/voicestudio_alan.py clone `
  --work-dir "D:\自动剪辑\alan解说\项目名\音色"
```

脚本会把 MP3 转成单声道 48 kHz PCM WAV，并进行轻度高/低通与响度归一化；这只能减少底噪和响度漂移，不能凭空恢复 MP3 已损失的细节。`voicestudio-profile.json` 含本机 profile ID，不应提交 Git。

默认风格为：沉稳自然、清晰口语、有悬疑张力、不过度播音。若试听后需要调整，只改 `--instruct` 新建 profile；不要对成片做变调来伪造“更好”的音色。

## 配音和质量门禁

```powershell
python scripts/voicestudio_alan.py synthesize `
  --voice "<profile-id>" `
  --text "D:\自动剪辑\alan解说\项目名\解说稿.txt" `
  --output "D:\自动剪辑\alan解说\项目名\配音\大宝解说.wav"
```

长稿按自然段分段请求，再合并为 48 kHz、单声道、PCM16 WAV。每次都输出 `*.quality.json`，必须通过格式、声道和峰值门禁。profile ID、音频原件、未审核试音均是项目私有产物，不写入仓库。

当前参考音频仅约 8.8 秒。它可以建立克隆 profile，但若希望进一步提高稳定性，应补充一段 15–30 秒、单人、无 BGM、无混响、逐字稿准确的 WAV，再显式替换 `--reference` 和 `--reference-text` 建新 profile。
