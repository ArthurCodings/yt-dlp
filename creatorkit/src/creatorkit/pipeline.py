"""核心流程：解析链接 → 选字幕 → 下载 → (语音识别) → 写字幕/全文/笔记 → 更新索引。"""

from __future__ import annotations

import dataclasses
import datetime as dt
import itertools
import re
import sys
from glob import escape as glob_escape
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .asr import Transcriber
from .config import Config
from .cookies import resolve_cookiefile
from .douyin_browser import BrowserFetchError, BrowserUnavailable, extract_video_id, fetch_aweme_detail, is_douyin_url
from .notes import add_to_index, find_in_index, render_note
from .subtitles import Segment, choose_subtitle, format_clock, parse_subtitle_file, to_plain_text, to_srt
from .textconv import convert_segments

FOLDER_TMPL = '%(extractor_key)s/%(upload_date>%Y-%m-%d|0000-00-00)s %(title).70B [%(id)s]'
MEDIA_EXTS = {'mp4', 'mkv', 'webm', 'mov', 'flv', 'm4a', 'mp3', 'opus', 'ogg', 'flac', 'wav', 'aac', 'm4v'}
SUB_FORMATS = 'json3/srt/vtt/ttml/srv3/srv1/best'


@dataclasses.dataclass
class ItemResult:
    url: str
    ok: bool
    folder: Path | None = None
    title: str | None = None
    source: str | None = None
    skipped: bool = False
    error: str | None = None


def parse_browser_spec(spec: str) -> tuple:
    """'chrome' / 'chrome:Profile 1' → yt-dlp 的 cookiesfrombrowser 元组。"""
    name, _, profile = spec.partition(':')
    return (name.strip().lower(), profile.strip() or None, None, None)


class Pipeline:
    def __init__(self, cfg: Config, log=print, force: bool = False):
        self.cfg = cfg
        self.log = log
        self.force = force
        self.root = Path(cfg.output_dir).expanduser().resolve()
        self._transcriber: Transcriber | None = None
        self._cookiefile: str | None = None

    # ------------------------------------------------------------ yt-dlp 参数

    def _base_params(self) -> dict:
        p = {
            'retries': 5,
            'fragment_retries': 5,
            'concurrent_fragment_downloads': 4,
            'noplaylist': False,
            'quiet': True,
            'no_warnings': False,
            'noprogress': False,
        }
        if self.cfg.cookies:
            if self._cookiefile is None:
                self._cookiefile = resolve_cookiefile(self.cfg.cookies)
            p['cookiefile'] = self._cookiefile
        if self.cfg.cookies_from_browser:
            p['cookiesfrombrowser'] = parse_browser_spec(self.cfg.cookies_from_browser)
        if self.cfg.proxy:
            p['proxy'] = self.cfg.proxy
        return p

    def _download_params(self, folder: Path, base_name: str, *, media: str | None,
                         choice=None) -> dict:
        p = self._base_params()
        p['outtmpl'] = {'default': str(folder / f'{base_name}.%(ext)s'),
                        'subtitle': str(folder / 'source.%(ext)s'),
                        'thumbnail': str(folder / 'cover.%(ext)s'),
                        'infojson': str(folder / 'meta')}
        p['writeinfojson'] = True
        p['postprocessors'] = []
        if self.cfg.write_thumbnail:
            p['writethumbnail'] = True
            p['postprocessors'].append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg', 'when': 'before_dl'})
        if choice is not None:
            p['writeautomaticsub' if choice.in_auto_dict else 'writesubtitles'] = True
            p['subtitleslangs'] = [re.escape(choice.lang)]
            p['subtitlesformat'] = SUB_FORMATS
        if media == 'video':
            h = self.cfg.video_max_height
            p['format'] = 'bv*+ba/b'
            # 优先 H.264 + AAC：剪映 / Premiere 等剪辑软件兼容性最好
            p['format_sort'] = [f'res:{h}', 'vcodec:h264', 'acodec:aac']
            p['merge_output_format'] = 'mp4'
        elif media == 'audio':
            p['format'] = 'ba/b'
            p['postprocessors'].append({'key': 'FFmpegExtractAudio',
                                        'preferredcodec': self.cfg.audio_format, 'preferredquality': '0'})
        else:
            p['skip_download'] = True
            p['noprogress'] = True
        return p

    # ------------------------------------------------------------ 入口

    def run(self, urls: list[str]) -> list[ItemResult]:
        results: list[ItemResult] = []
        for url in urls:
            results.extend(self.process_url(url))
        return results

    def _probe_params(self) -> dict:
        params = {
            **self._base_params(),
            'extract_flat': 'in_playlist',
            'skip_download': True,
            # B 站等提取器只有在“要字幕”时才会去取字幕列表（download=False 不会写任何文件）
            'writesubtitles': True,
            'writeautomaticsub': True,
        }
        if self.cfg.max_items:
            params['playlistend'] = self.cfg.max_items
        return params

    def process_url(self, url: str) -> list[ItemResult]:
        params = self._probe_params()
        self.log(f'\n▶ 解析 {url}')
        if self.cfg.douyin_browser and is_douyin_url(url) and _playwright_installed():
            return [self._process_douyin(url)]
        try:
            with YoutubeDL(params) as probe:
                info = probe.extract_info(url, download=False)
                if info.get('_type') in ('playlist', 'multi_video'):
                    entries = list(itertools.islice(info.get('entries') or [], self.cfg.max_items))
                    self.log(f'  这是一个列表：{info.get("title")}，共处理 {len(entries)} 条')
                    results = []
                    for entry in entries:
                        if not entry:
                            continue
                        entry_url = entry.get('webpage_url') or entry.get('url')
                        results.extend(self.process_url(entry_url))
                    return results
                return [self._process_video(probe, info, url)]
        except DownloadError as e:
            msg = _explain_error(str(e))
            self.log(f'  ✗ 失败：{msg}')
            return [ItemResult(url, False, error=msg)]

    # ------------------------------------------------------------ 抖音（浏览器）

    def _process_douyin(self, url: str) -> ItemResult:
        try:
            with YoutubeDL(self._probe_params()) as probe:
                video_id = extract_video_id(url)
                if not video_id:  # v.douyin.com 短链接：跟随跳转拿到作品 ID
                    with probe.urlopen(url) as resp:
                        video_id = extract_video_id(resp.url)
                if not video_id:
                    raise DownloadError('无法从链接中识别抖音作品 ID（目前支持视频作品）')
                if skipped := self._skip_existing(f'Douyin:{video_id}', url):
                    return skipped
                detail = fetch_aweme_detail(video_id, probe.params.get('cookiefile'),
                                            headless=self.cfg.browser_headless, log=self.log)
                ie = probe.get_info_extractor('Douyin')
                parsed = ie._parse_aweme_video_app(detail)
                # 抖音 CDN 校验 Referer，不带会 403
                for fmt in parsed.get('formats') or []:
                    fmt.setdefault('http_headers', {})['Referer'] = 'https://www.douyin.com/'
                probe.add_default_extra_info(parsed, ie, f'https://www.douyin.com/video/{video_id}')
                info = probe.process_ie_result(parsed, download=False)
                return self._process_video(probe, info, url)
        except (DownloadError, BrowserUnavailable, BrowserFetchError) as e:
            msg = _explain_error(str(e))
            self.log(f'  ✗ 失败：{msg}')
            return ItemResult(url, False, error=msg)

    # ------------------------------------------------------------ 单条视频

    def _skip_existing(self, key: str, url: str, title: str | None = None) -> ItemResult | None:
        existing = find_in_index(self.root, key)
        if existing and not self.force and (self.root / existing['folder'] / 'note.md').is_file():
            self.log(f'  已采集过，跳过（加 --force 可重新采集）：{existing["folder"]}')
            return ItemResult(url, True, self.root / existing['folder'], title or existing.get('title'),
                              existing.get('source'), skipped=True)
        return None

    def _process_video(self, probe: YoutubeDL, info: dict, url: str) -> ItemResult:
        cfg = self.cfg
        key = f'{info.get("extractor_key")}:{info.get("id")}'
        title = info.get('title') or info.get('id')
        self.log(f'  标题：{title}')

        if skipped := self._skip_existing(key, url, title):
            return skipped

        folder = Path(probe.prepare_filename(info, outtmpl=str(self.root / FOLDER_TMPL)))
        folder.mkdir(parents=True, exist_ok=True)

        choice = None if cfg.asr == 'always' else choose_subtitle(info, cfg.prefer_langs)
        if choice:
            kind = '自动' if choice.automatic else '人工'
            self.log(f'  找到平台{kind}字幕：{choice.lang}')
        elif cfg.asr == 'never':
            self.log('  没有合适的平台字幕（已设置不做语音识别）')
        else:
            self.log('  没有合适的平台字幕，将进行语音识别' if cfg.asr == 'auto' else '  按设置总是进行语音识别')

        base_name = {'video': 'video', 'audio': 'audio', 'text': 'audio'}[cfg.mode]
        need_asr = cfg.asr == 'always' or (choice is None and cfg.asr == 'auto')
        media_kind = cfg.mode if cfg.mode != 'text' else ('audio' if need_asr else None)
        self._download(probe, info, self._download_params(folder, base_name, media=media_kind, choice=choice))

        segments: list[Segment] = []
        source = '无'
        if choice:
            sub_file = next(folder.glob(f'source.{glob_escape(choice.lang)}.*'), None)
            if sub_file:
                segments = parse_subtitle_file(sub_file)
                source = f'平台{"自动" if choice.automatic else "人工"}字幕（{choice.lang}）'
            if not segments:
                self.log('  平台字幕为空或下载失败')
                if cfg.asr == 'auto':
                    need_asr = True

        media_file = _find_media(folder, base_name)
        downloaded_for_asr = False
        if need_asr:
            if media_file is None:
                self.log('  下载音频用于语音识别……')
                self._download(probe, info, self._download_params(folder, 'audio', media='audio'))
                media_file = _find_media(folder, 'audio')
                downloaded_for_asr = True
            elif cfg.mode == 'text':
                downloaded_for_asr = True
            if media_file is None:
                raise DownloadError('没有下载到可供识别的音视频文件')
            segments, lang = self._get_transcriber().transcribe(
                media_file, cfg.language, cfg.script, context=asr_context(info))
            source = f'语音识别（{cfg.model}，{lang}）'

        segments = convert_segments(segments, cfg.script)
        files: dict[str, str] = {}
        if media_file and media_file.exists() and not (downloaded_for_asr and cfg.mode == 'text' and not cfg.keep_audio):
            files['视频' if media_file.suffix.lstrip('.') in {'mp4', 'mkv', 'webm', 'mov', 'flv', 'm4v'} else '音频'] = media_file.name
        if segments:
            (folder / 'transcript.srt').write_text(to_srt(segments), encoding='utf-8-sig')
            (folder / 'transcript.txt').write_text(to_plain_text(segments), encoding='utf-8')
            files['字幕'] = 'transcript.srt'
            files['全文'] = 'transcript.txt'
        cover = next((f for f in sorted(folder.glob('cover.*'))
                      if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')), None)
        if cover:
            files['封面'] = cover.name
        (folder / 'note.md').write_text(render_note(info, segments, source, files), encoding='utf-8')

        if downloaded_for_asr and cfg.mode == 'text' and not cfg.keep_audio and media_file and media_file.exists():
            media_file.unlink()

        add_to_index(self.root, {
            'key': key,
            'folder': folder.relative_to(self.root).as_posix(),
            'title': title,
            'uploader': info.get('uploader') or info.get('channel') or '',
            'platform': info.get('extractor_key'),
            'url': info.get('webpage_url') or url,
            'duration': format_clock(info['duration']) if info.get('duration') else '',
            'source': source,
            'mode': cfg.mode,
            'collected_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
        self.log(f'  ✓ 完成（{source}，{len(segments)} 句）→ {folder}')
        return ItemResult(url, True, folder, title, source)

    def _download(self, probe: YoutubeDL, info: dict, params: dict) -> None:
        with YoutubeDL(params) as ydl:
            # 复用解析阶段拿到的 cookie（抖音/B 站等下载时需要）
            for cookie in probe.cookiejar:
                ydl.cookiejar.set_cookie(cookie)
            ydl.process_ie_result(YoutubeDL.sanitize_info(info, remove_private_keys=True), download=True)
        if not params.get('skip_download'):
            print()  # yt-dlp 进度条以回车结尾，换行避免与后续日志粘连

    def _get_transcriber(self) -> Transcriber:
        if self._transcriber is None:
            self._transcriber = Transcriber(self.cfg.model, self.cfg.device, self.cfg.compute_type, log=self.log)
        return self._transcriber


def asr_context(info: dict) -> str:
    """把标题和标签整理成语音识别提示词（去掉 # 和多余空白）。"""
    parts = [info.get('title') or '']
    parts += [t for t in (info.get('tags') or [])[:10] if t not in parts[0]]
    text = ' '.join(parts).replace('#', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _playwright_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec('playwright') is not None


def _find_media(folder: Path, base_name: str) -> Path | None:
    for f in sorted(folder.glob(f'{base_name}.*')):
        if f.suffix.lstrip('.').lower() in MEDIA_EXTS and f.stem == base_name:
            return f
    return None


def _explain_error(msg: str) -> str:
    msg = re.sub(r'^ERROR:\s*', '', msg)
    low = msg.lower()
    if 'fresh cookies' in low or 's_v_web_id' in low:
        return msg + ('\n    提示：抖音需要 cookie 和浏览器组件。请导出 douyin.txt 放进 cookies 文件夹，'
                      '并安装：pip install -e "creatorkit[browser]"')
    if 'could not copy chrome cookie database' in low or 'failed to decrypt' in low or 'app-bound' in low:
        return msg + '\n    提示：新版 Chrome/Edge 的 cookie 加密无法直接读取。建议用 Firefox 登录后设置 cookies_from_browser = "firefox"，或用浏览器扩展导出 cookies.txt。'
    if 'sign in to confirm' in low or 'login required' in low or 'requires login' in low:
        return msg + '\n    提示：该内容需要登录，请配置 cookies_from_browser 或 cookies。'
    if 'geo' in low and ('restrict' in low or 'block' in low or 'not available in your country' in low):
        return msg + '\n    提示：地区限制，请配置 proxy 使用对应地区的代理。'
    return msg
