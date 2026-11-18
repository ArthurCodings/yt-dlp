"""配置加载：默认值 < 配置文件 < 命令行参数。"""

from __future__ import annotations

import dataclasses
import os
import tomllib
from pathlib import Path

MODES = ('video', 'audio', 'text')
ASR_POLICIES = ('auto', 'always', 'never')
SCRIPTS = ('hans', 'hant', 'hk', 'keep')


@dataclasses.dataclass
class Config:
    # 素材库根目录
    output_dir: str = str(Path.home() / 'CreatorKit')
    # video: 下载视频；audio: 只要音频；text: 只要文字（需要转写时临时下载音频）
    mode: str = 'video'
    # auto: 没有可用字幕时才语音识别；always: 总是语音识别；never: 从不
    asr: str = 'auto'
    # 中文输出字形：hans 简体 / hant 繁体(台湾用语) / hk 繁体(香港) / keep 不转换
    script: str = 'hans'
    # 语音识别
    model: str = 'large-v3-turbo'
    device: str = 'auto'          # auto / cuda / cpu
    compute_type: str = 'auto'    # auto / float16 / int8_float16 / int8 ...
    language: str | None = None   # 强制识别语言，如 zh / en / ja；None 为自动检测
    # 字幕语言偏好（在“与视频原语言一致”的前提下的次序）
    prefer_langs: list[str] = dataclasses.field(
        default_factory=lambda: ['zh-hans', 'zh-hant', 'zh', 'en', 'ja', 'ko'])
    # 下载
    video_max_height: int = 1080
    audio_format: str = 'm4a'     # m4a / mp3 / opus / best
    keep_audio: bool = False      # text 模式下转写完是否保留临时音频
    write_thumbnail: bool = True
    # 网络 / 登录
    cookies_from_browser: str | None = None  # 如 firefox / chrome / edge
    cookies: str | None = None               # Netscape 格式 cookies.txt 路径
    proxy: str | None = None                 # 如 http://127.0.0.1:7897
    # 抖音用真实浏览器（本机 Chrome/Edge）打开页面获取作品数据
    douyin_browser: bool = True
    browser_headless: bool = True            # False 显示浏览器窗口（遇到验证码时手动完成）
    # 播放列表/频道一次最多处理多少条
    max_items: int | None = None

    def validate(self) -> None:
        for name, allowed in (('mode', MODES), ('asr', ASR_POLICIES), ('script', SCRIPTS)):
            value = getattr(self, name)
            if value not in allowed:
                raise ValueError(f'配置项 {name}={value!r} 无效，可选值：{", ".join(allowed)}')


def config_search_paths(explicit: str | None = None) -> list[Path]:
    paths = []
    if explicit:
        paths.append(Path(explicit))
    if env := os.environ.get('CK_CONFIG'):
        paths.append(Path(env))
    paths.append(Path.cwd() / 'creatorkit.toml')
    paths.append(Path.home() / '.creatorkit.toml')
    return paths


def load_config(explicit: str | None = None, overrides: dict | None = None) -> tuple[Config, Path | None]:
    cfg = Config()
    used = None
    for path in config_search_paths(explicit):
        if path.is_file():
            with path.open('rb') as f:
                data = tomllib.load(f)
            known = {f.name for f in dataclasses.fields(Config)}
            unknown = set(data) - known
            if unknown:
                raise ValueError(f'{path} 中有未知配置项：{", ".join(sorted(unknown))}')
            for key, value in data.items():
                setattr(cfg, key, value)
            used = path
            break
        if explicit and path == Path(explicit):
            raise FileNotFoundError(f'找不到配置文件：{path}')
    for key, value in (overrides or {}).items():
        if value is not None:
            setattr(cfg, key, value)
    cfg.validate()
    return cfg, used
