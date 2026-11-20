# CreatorKit

基于本仓库 yt-dlp 的**自媒体素材采集工具**：粘贴链接 → 下载视频或音频 → 拿到逐字稿 → 生成一份可以直接写文案的 Markdown 笔记。

- **全球站点**：yt-dlp 支持的上千个网站都能用——YouTube、B 站、抖音、TikTok、小红书、微博、Facebook、Instagram、X……
- **文字优先用平台字幕**：有人工字幕就用人工字幕；其次用平台自动字幕（YouTube 原语言自动字幕、B 站 AI 字幕）。**不会**用“自动翻译”的字幕。
- **没有字幕就本地语音识别**：faster-whisper + `large-v3-turbo`，有 NVIDIA 显卡自动用 GPU，全程离线，不上传任何内容。会把视频标题和标签作为提示词，提高人名、游戏名等专有名词的准确率；按词级时间戳重新断句，字幕可直接导入剪映。
- **简繁统一**：输出统一转成简体 / 台湾繁体 / 香港繁体（可关闭）。
- **素材库**：每条视频一个文件夹，自动维护 `索引.md`，重复链接自动跳过。

## 最简单的用法：双击

1. 双击 `creatorkit\采集素材.cmd`，会弹出一个黑色窗口。
2. 把链接粘贴进去（右键或 Ctrl+V）。可以直接粘贴抖音 / B 站 App 里“分享 → 复制链接”得到的整段文字，工具会自己找出链接；一次可以粘贴多个。
   也可以把电脑里的视频/音频文件**拖进窗口**，直接转成文字。
3. 按两次回车，再输入 `1`（视频+文字）/ `2`（音频+文字）/ `3`（只要文字），回车。
4. 完成后会自动打开结果文件夹，`note.md` 是笔记，`transcript.txt` 是全文。
5. 窗口不用关，接着粘贴下一个链接即可。

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
ck get -m text "https://www.douyin.com/video/xxxx"

# 一次多个链接 / 从文件读取（每行一个，# 开头是注释）
ck get URL1 URL2 URL3
ck get -f links.txt

# 合集、频道、收藏夹：最多处理 20 条
ck get --max 20 "https://www.youtube.com/@somechannel/videos"

# 抖音遇到验证码：显示浏览器窗口，手动完成验证
ck get --show-browser "https://www.douyin.com/video/xxxx"

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
| 抖音 | 需要 **cookie（douyin.txt）+ 本机 Chrome 或 Edge**。抖音接口需要浏览器端签名，工具会在后台用你的 Chrome 带 cookie 打开视频页，读取页面自己加载的作品数据。遇到验证码时加 `--show-browser`，在弹出的窗口里手动完成。 |
| TikTok / 小红书 / 微博 / IG / X | 公开内容一般直接可用；失败时先补 cookie。 |
| 地区限制内容 | 配置 `proxy` 走对应地区的代理。 |

### 提供 cookie

推荐做法：每个平台导出一个 cookie 文件，全部放进同一个文件夹，配置里写这个文件夹：

```toml
cookies = "E:/CreatorKit/cookies"   # 里面放 douyin.txt、bilibili.txt ……
```

新版 Chrome / Edge（127+）在 Windows 上对 cookie 做了应用绑定加密，yt-dlp 无法直接读取，所以用扩展导出：

1. Chrome 打开扩展 **Get cookies.txt LOCALLY** 的商店页并安装（开源，只在本地导出，不上传）：
   <https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc>
2. 打开要用的网站（抖音 douyin.com / B 站 bilibili.com），需要的话先登录。
3. 点浏览器右上角拼图图标 → Get cookies.txt LOCALLY → **Export**，把下载的文件改名为 `douyin.txt` / `bilibili.txt`，放进上面的文件夹。
4. 运行 `ck doctor`，最后几行会列出每个 cookie 文件包含的网站，确认无误即可。

cookie 过期后（抖音通常几天到几周，B 站约半年）重新导出覆盖即可。用 Firefox 的话可以直接 `cookies_from_browser = "firefox"`。

> cookie 等同于登录凭证，请勿分享这些文件，也不要放进仓库目录。

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
| `subtitles.py` | 字幕选择规则、多格式解析（srt/vtt/json3/ttml/srv）、逐词重新断句、分段 |
| `asr.py` | faster-whisper 封装，自动 GPU/CPU，中文标点提示词，标题热词 |
| `douyin_browser.py` | 抖音：用本机浏览器打开视频页，读取页面加载的作品数据 |
| `cookies.py` | cookie 文件/文件夹合并 |
| `notes.py` | 笔记和索引生成 |
| `textconv.py` | OpenCC 简繁转换 |
| `config.py` / `cli.py` | 配置与命令行 |
