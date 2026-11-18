# CreatorKit

基于本仓库 yt-dlp 的**自媒体素材采集工具**：粘贴链接 → 下载视频或音频 → 拿到逐字稿 → 生成一份可以直接写文案的 Markdown 笔记。

- **全球站点**：yt-dlp 支持的上千个网站都能用——YouTube、B 站、抖音、TikTok、小红书、微博、Facebook、Instagram、X……
- **文字优先用平台字幕**：有人工字幕就用人工字幕；其次用平台自动字幕（YouTube 原语言自动字幕、B 站 AI 字幕）。**不会**用“自动翻译”的字幕。
- **没有字幕就本地语音识别**：faster-whisper + `large-v3-turbo`，有 NVIDIA 显卡自动用 GPU，全程离线，不上传任何内容。
- **简繁统一**：输出统一转成简体 / 台湾繁体 / 香港繁体（可关闭）。
- **素材库**：每条视频一个文件夹，自动维护 `索引.md`，重复链接自动跳过。

## 安装（Windows）

需要 Python 3.11+ 和 ffmpeg（`ffmpeg` 能在命令行运行即可）。

```powershell
# 有 NVIDIA 显卡
powershell -ExecutionPolicy Bypass -File creatorkit\setup.ps1
# 没有 N 卡
powershell -ExecutionPolicy Bypass -File creatorkit\setup.ps1 -Cpu
```

脚本会创建 `.venv`、以可编辑模式安装本仓库的 yt-dlp 和 CreatorKit，并生成 `%USERPROFILE%\.creatorkit.toml`。
之后用 `creatorkit\ck.cmd` 运行；把 `creatorkit` 目录加进 PATH 就能在任何地方直接敲 `ck`。

检查环境：

```powershell
ck doctor
```

## 用法

```powershell
# 下载视频 + 字幕/逐字稿 + 笔记（默认）
ck get "https://www.youtube.com/watch?v=xxxx"

# 只要音频（播客、访谈）
ck get -m audio "https://www.bilibili.com/video/BVxxxx"

# 只要文字：有字幕直接拿字幕，没有就临时下载音频识别完再删掉
ck get -m text "https://www.douyin.com/video/xxxx" --cookies E:\CreatorKit\cookies.txt

# 一次多个链接 / 从文件读取（每行一个，# 开头是注释）
ck get URL1 URL2 URL3
ck get -f links.txt

# 合集、频道、收藏夹：最多处理 20 条
ck get --max 20 "https://www.youtube.com/@somechannel/videos"

# 输出繁体（台湾用语）
ck get --script hant URL

# 已经有字幕也强制用语音识别（字幕质量差时）
ck get --asr always URL

# 本地文件转文字（生成同名 .srt / .txt / .md）
ck transcribe 录音.m4a 采访.mp4
```

## 输出结构

```
素材库/
├── 索引.md                     ← 所有采集记录，点标题跳到笔记
├── library.jsonl               ← 同上（机器可读，用于去重）
├── Youtube/
│   └── 2026-11-01 视频标题 [视频ID]/
│       ├── note.md             ← 笔记：元数据 + 简介 + 标签 + 带时间戳的全文 + “我的笔记”
│       ├── transcript.txt      ← 纯文本全文（按停顿分段，适合直接复制改写）
│       ├── transcript.srt      ← 字幕（可导入剪映 / Premiere）
│       ├── video.mp4           ← 优先 H.264 + AAC，剪辑软件兼容性最好
│       ├── cover.jpg           ← 封面
│       ├── source.zh-Hans.vtt  ← 平台原始字幕（如果有）
│       └── meta.info.json      ← 完整元数据
├── BiliBili/ ...
└── Douyin/ ...
```

## 各平台注意事项

| 平台 | 说明 |
|---|---|
| YouTube | 开箱即用。人工字幕 > 原语言自动字幕 > 语音识别。已装 deno 以支持新版 YouTube 签名。 |
| B 站 | 开箱即用。CC 字幕和 AI 字幕通常**需要登录**才能拿到；不登录会自动转语音识别。登录后还有 1080P+。 |
| 抖音 | **必须提供 cookie**（不登录也行，但要有浏览器访问过抖音产生的 cookie）。见下文。 |
| TikTok / 小红书 / 微博 / IG / X | 公开内容一般直接可用；失败时先补 cookie。 |
| 地区限制内容 | 配置 `proxy` 走对应地区的代理。 |

### 提供 cookie

新版 Chrome / Edge（127+）在 Windows 上对 cookie 做了应用绑定加密，yt-dlp 无法直接读取，所以推荐：

1. 在 Chrome/Edge 装扩展 **Get cookies.txt LOCALLY**（开源，只在本地导出）。
2. 打开 douyin.com（需要的话登录），点扩展 → Export，保存为 `E:\CreatorKit\cookies.txt`。
3. 配置文件写 `cookies = "E:/CreatorKit/cookies.txt"`，或命令行加 `--cookies 路径`。

cookie 过期后（通常几天到几周）重新导出一次即可。用 Firefox 的话可以直接 `cookies_from_browser = "firefox"`。

> cookie 等同于登录凭证，请勿分享 `cookies.txt`。仓库的 `.gitignore` 已排除素材库目录，但 cookie 文件请放在仓库外。

## 配置

见 [`creatorkit.example.toml`](creatorkit.example.toml)。查找顺序：`--config` 参数 → 环境变量 `CK_CONFIG` → 当前目录 `creatorkit.toml` → `%USERPROFILE%\.creatorkit.toml`。

语音识别模型首次使用时自动从 Hugging Face 下载（`large-v3-turbo` 约 1.6 GB），缓存在 `%USERPROFILE%\.cache\huggingface`。
大陆网络访问不畅时可设置环境变量 `HF_ENDPOINT=https://hf-mirror.com`。

## 开发

```powershell
.venv\Scripts\python -m pytest creatorkit\tests
```

代码都在 `creatorkit/` 下，不改动 `yt_dlp/`，方便同步上游：

```powershell
git fetch upstream
git merge upstream/master
```

| 模块 | 作用 |
|---|---|
| `pipeline.py` | 主流程：解析 → 选字幕 → 下载 → 识别 → 写文件 → 更新索引 |
| `subtitles.py` | 字幕选择规则、多格式解析（srt/vtt/json3/ttml/srv）、分段 |
| `asr.py` | faster-whisper 封装，自动 GPU/CPU，中文标点提示词 |
| `notes.py` | 笔记和索引生成 |
| `textconv.py` | OpenCC 简繁转换 |
| `config.py` / `cli.py` | 配置与命令行 |
