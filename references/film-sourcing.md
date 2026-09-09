# 老电影片源获取手册（2026-08-16 实测）

为解说稿批量找「最高清版+英文字幕」老片的实战路径。

## 1. YouTube 全片源（优先）

老片/邪典片在 YT 常有官方或知名频道全片上传：
- **Film&Clips / Film&Clips in English**：意大利片全片（血与黑蕾丝 1964 在此，480p 上限）
- **Full Moon Features**（官方频道）：Full Moon 系邪典片全片（保龄球馆尖叫女郎在此，但可能撞登录墙）
- **FilmRise Movies**（官方免费频道）：Prom Night 1980 等（实测 1080p + en 字幕）
- **TheKingInGiallo / Giallo Realm**：giallo 全片（你的恶习是密室，但常撞登录墙）
- 搜索配方：`ytsearchN:"<英文片名> <年份> full movie"`，备选词：`film`、`english`、`导演名`、`主演名`

**YouTube 没有的**（大厂片）：Friday the 13th(WB)、Species(MGM)、Cat People 1982(Universal)、Return of the Living Dead 1985(Orion/MGM 原片)——搜索只有预告/片段。

## 2. archive.org（IA）全片源（大厂片退路）

IA 有大量老电影条目，搜索配方：
- `title:("<片名>")` 全条目列出；再 `title:("<片名>") AND format:(SubRip)` 筛带字幕的
- **带 SubRip 的条目优先**（视频+英字一起拿）：实测 Return of the Living Dead 1985 有
  `the-return-of-the-living-dead-1985-1080p-h-264`（1080p mkv 1.4GB + srt）
- DVD/合集条目：`cat-people-1982-dvd`（480p 全片 852x480）、`the-cat-people-1942-1982`（1942+1944+1982 三部）
- 下载 URL：`https://archive.org/download/<identifier>/<urlencoded文件名>`；文件名含重音/大小写（Cópia/And vs and）必须从 `/metadata/<identifier>` 的 files 列表**原样复制**，手写必 404
- **坑：IA 下载会静默截断**（Content-Length 不符但连接正常结束）→ 下载后必须 ffprobe 验流（moov atom not found = 截断），校验函数：`ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 <file>` 有输出才算好
- 503 是单条目服务器抽风：换同片其他条目（`_202503`/`_202404` 等日期后缀条目）

## 3. 英文字幕缺口

- YT 全片自带 en/en-orig 自动字幕 → yt-dlp `--sub-langs "en(-orig)?" --write-auto-subs` 直接拿
- 登录墙（Sign in to confirm）：**关闭 Chrome 后**用 `--cookies-from-browser "chrome:Profile 1"` 直接解
  （实测 2026-08-16：三个 profile 都有 YT 会话，Profile 1 最全含 LOGIN_INFO；关 Chrome 后 cookie 库解锁，
  yt-dlp 自动处理 v10 解密；抓墙内视频的英字 `--skip-download --write-subs` 一次成功）
- 字幕抓取命令：`yt-dlp --cookies-from-browser "chrome:Profile 1" --skip-download --write-subs --write-auto-subs --sub-langs "en(-orig)?" --convert-subs srt -o "目录/%(id)s.%(ext)s" <URL>`
- IA 条目自带 .srt 的（Mr.Linton/YTS 发布组）直接拿
- 没有免费渠道的（OpenSubtitles 匿名 API 已 401、zimuku/4ksub/a4k 全挂、yifysubtitles 无结果）：
  老接口 `api.opensubtitles.org/xml-rpc` 匿名 LogIn 已关 → 需用户提供 srt 或 OpenSubtitles 账号
- legenda.srt 很可能是葡萄牙语，下前抽查前几行（`Sim!`/`Ninguém` 等葡语特征词）

## 4. 质量铁律

- **验证靠 ffprobe 不靠元数据**：IA 元数据 size 虚标（838MB 实为 567MB）、分辨率字段缺失；YT 用
  `-f "bv*[height>=720][height<=1080]" --print "%(height)s"` 实测
- 老片源本身低清就如实交付：血与黑蕾丝 480p、豹妹/千年血后 480p 是能找到的最好版本
- 10.4GB 的 35mm 开幅 mkv vs 1.4GB 1080p+srt 条目：**选带字幕的**（解说工作流字幕>无字幕超大文件）
- 目录规范：`D:\自动剪辑\alan解说\原片\NN-中文片名\视频+1个srt`；字幕只留 1 个（优先 .en.srt 手动轨，次 .en-orig.srt）
