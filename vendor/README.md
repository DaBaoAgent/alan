# vendor 依赖记录

这两个仓库是**只读依赖**，不进本仓库（见 `.gitignore` 的 `vendor/*`）。
换机器或需要升级时，按下表的 commit 重新 clone 即可。

| 目录 | 来源 | commit | 版本 | 许可 | 用途 |
|---|---|---|---|---|---|
| `ffmpeg-skill/` | https://github.com/kajisho5/ffmpeg-skill | `f1c97cbffeac71b8fdfca2f790ceb00db3bcce65` | v3.10.1 (2026-11-15) | MIT | 剪辑执行层：cut / fit / caption / audio / loudness / export / render |
| `movie-narrator/` | https://github.com/zcbacxc/movie-narrator | `4c7e81fedb9a0eec72257b15774a2bf5e2f2dd96` | 2026-09-16 | AGPL-3.0 | 匹配算法参考（未复制代码，只借鉴 act 分区 / topk / clamp / diversity 的实现思路） |

## 重建

```powershell
git clone --depth 1 https://github.com/kajisho5/ffmpeg-skill.git vendor/ffmpeg-skill
git -C vendor/ffmpeg-skill checkout f1c97cbffeac71b8fdfca2f790ceb00db3bcce65

git clone --depth 1 https://github.com/zcbacxc/movie-narrator.git vendor/movie-narrator
git -C vendor/movie-narrator checkout 4c7e81fedb9a0eec72257b15774a2bf5e2f2dd96
```

克隆后**删掉嵌套 `.git`**，否则 git 会把它们当成嵌套仓库/submodule：

```powershell
Remove-Item -LiteralPath vendor\ffmpeg-skill\.git -Recurse -Force
Remove-Item -LiteralPath vendor\movie-narrator\.git -Recurse -Force
```

## 边界

- `ffmpeg-skill` 是纯执行层，不做语义判断（其文档原文 "does not reason, plan, decide"），
  画面选哪个镜头由 `scripts/edit/match_edl.py` 决定，它只负责按 EDL 精确切、变速、拼、烧字幕、归一化。
- `movie-narrator` 自带写稿与 TTS，本管线**不用**它的这两步；只借鉴其匹配算法，
  且已按本项目需求改造（长句拆槽 / 句间停顿吸收 / 叙事游标），差异见 `references/edit-pipeline.md`。
- AGPL-3.0 的传染性只作用于"复制其代码"；本项目为独立实现，但若将来直接搬运其源文件，需按 AGPL 处理。
