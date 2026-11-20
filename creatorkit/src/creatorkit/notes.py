"""生成笔记（note.md）和素材库索引。

笔记结构：
    YAML 属性区（Obsidian / Typora 可识别，便于按平台、作者、标签筛选）
    标题 + 信息卡片 + 封面
    简介（话题标签单独提取）
    全文（按章节或每约 3 分钟分节，小标题带时间）
    我的笔记（重新生成时保留用户已写内容）
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .subtitles import Segment, format_clock, to_paragraphs

PLATFORM_NAMES = {
    'Douyin': '抖音', 'TikTok': 'TikTok', 'BiliBili': 'B站', 'BiliBiliBangumi': 'B站', 'BilibiliSpaceVideo': 'B站',
    'Youtube': 'YouTube', 'YoutubeTab': 'YouTube', 'XiaoHongShu': '小红书', 'Weibo': '微博', 'WeiboVideo': '微博',
    'Kuaishou': '快手', 'Instagram': 'Instagram', 'Facebook': 'Facebook', 'Twitter': 'X', 'Vimeo': 'Vimeo',
}
# 没有独立标题、标题就是文案的平台
CAPTION_PLATFORMS = {'Douyin', 'TikTok', 'Kuaishou', 'Instagram', 'Twitter', 'XiaoHongShu', 'Weibo'}

MY_NOTES_HEADING = '## 我的笔记'
MY_NOTES_TEMPLATE = '- **金句**：\n- **可以借鉴的点**：\n- **选题灵感**：\n'
SECTION_SECONDS = 180

_HASHTAG = re.compile(r'#([^\s#@，。！？,!?]+)')


def platform_name(info_or_key) -> str:
    key = info_or_key if isinstance(info_or_key, str) else (
        info_or_key.get('extractor_key') or info_or_key.get('extractor') or '')
    return PLATFORM_NAMES.get(key, key or '未知')


def _fmt_date(upload_date: str | None) -> str | None:
    if upload_date and len(upload_date) == 8 and upload_date.isdigit():
        return f'{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}'
    return None


def strip_hashtags(text: str) -> str:
    return re.sub(r'[ \t]{2,}', ' ', _HASHTAG.sub('', text)).strip()


def extract_tags(info: dict) -> list[str]:
    """平台标签 + 文案里的 #话题，去重保序。"""
    tags: list[str] = []
    for t in [*(info.get('tags') or []), *_HASHTAG.findall(info.get('description') or ''),
              *_HASHTAG.findall(info.get('title') or '')]:
        t = t.strip()
        if t and t not in tags:
            tags.append(t)
    return tags[:20]


def display_title(info: dict, max_len: int = 32) -> str:
    """抖音等平台没有标题，yt-dlp 把整段文案当标题：取第一句并去掉话题标签。"""
    raw = (info.get('title') or '').strip()
    key = info.get('extractor_key') or ''
    if key in CAPTION_PLATFORMS or len(raw) > 50:
        base = strip_hashtags(raw or info.get('description') or '')
        base = re.split(r'[。！？!?\n]', base, maxsplit=1)[0].strip()
        if len(base) > max_len:
            cut = None
            for sep in (' ', '；', '，', ',', '——'):
                pos = base.rfind(sep, 8, max_len + 1)
                if pos > 0:
                    cut = pos
                    break
            base = base[:cut].rstrip('，,；; ') if cut else base[:max_len] + '…'
        raw = base or raw
    return raw or info.get('id') or '未命名'


def _yaml_str(value) -> str:
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'


def _front_matter(fields: dict) -> list[str]:
    lines = ['---']
    for key, value in fields.items():
        if value in (None, '', []):
            continue
        if isinstance(value, list):
            lines.append(f'{key}: [{", ".join(_yaml_str(v) for v in value)}]')
        else:
            lines.append(f'{key}: {_yaml_str(value)}')
    lines.append('---')
    return lines


def _description_block(info: dict, title: str) -> list[str]:
    desc = strip_hashtags((info.get('description') or '').strip())
    if not desc:
        return []
    paras = [l.strip() for l in desc.splitlines() if l.strip()]
    if not paras or (len(paras) == 1 and paras[0] == title):
        return []
    body = '\n\n'.join(paras)
    if len(body) > 600 or len(paras) > 10:  # YouTube 等长简介：折叠
        return ['<details>', '<summary>展开简介</summary>', '', body, '', '</details>']
    return [body]


def _sections(segments: list[Segment], chapters: list[dict] | None) -> list[tuple[float, str | None, list[str]]]:
    """返回 [(小节开始时间, 章节名或 None, [段落...])]。"""
    paragraphs = to_paragraphs(segments, max_chars=150)
    if chapters and len(chapters) >= 2:
        sections = [(float(c.get('start_time') or 0), c.get('title'), []) for c in chapters]
        for start, text in paragraphs:
            idx = max((i for i, s in enumerate(sections) if s[0] <= start + 0.5), default=0)
            sections[idx][2].append(text)
        return [s for s in sections if s[2]]
    sections: list[tuple[float, str | None, list[str]]] = []
    for start, text in paragraphs:
        if not sections or start - sections[-1][0] >= SECTION_SECONDS:
            sections.append((start, None, []))
        sections[-1][2].append(text)
    return sections


def extract_my_notes(note_text: str) -> str | None:
    """取出旧笔记里“我的笔记”下用户写的内容（与模板相同则视为未填写）。"""
    idx = note_text.find(MY_NOTES_HEADING)
    if idx < 0:
        return None
    body = note_text[idx + len(MY_NOTES_HEADING):].strip('\n')
    normalized = re.sub(r'\s+', '', body)
    if normalized in ('', '-', re.sub(r'\s+', '', MY_NOTES_TEMPLATE)):
        return None
    return body.rstrip() + '\n'


def render_note(info: dict, segments: list[Segment], transcript_source: str, files: dict[str, str],
                my_notes: str | None = None, collected_at: str | None = None) -> str:
    title = display_title(info)
    platform = platform_name(info)
    author = info.get('uploader') or info.get('channel') or info.get('creator')
    date = _fmt_date(info.get('upload_date'))
    duration = format_clock(info['duration']) if info.get('duration') else None
    url = info.get('webpage_url') or info.get('original_url')
    tags = extract_tags(info)
    collected_at = collected_at or dt.datetime.now().strftime('%Y-%m-%d %H:%M')

    out = _front_matter({
        'title': title, 'platform': platform, 'author': author, 'date': date, 'duration': duration,
        'tags': tags, 'url': url, 'source': transcript_source, 'collected': collected_at,
    })
    out += ['', f'# {title}', '']

    meta = [f'**{platform}**']
    if author:
        meta.append(f'@{author}')
    if date:
        meta.append(date)
    if duration:
        meta.append(f'⏱ {duration}')
    links = ([f'[▶ 原视频]({url})'] if url else []) + [
        f'[{label}](<{name}>)' for label, name in files.items() if label != '封面']
    out.append('> ' + ' · '.join(meta) + '  ')
    if links:
        out.append('> ' + ' · '.join(links))
    out.append('')
    if cover := files.get('封面'):
        out += [f'<img src="{cover}" width="220">', '']

    desc = _description_block(info, title)
    if desc or tags:
        out += ['## 简介', '']
        if desc:
            out += [*desc, '']
        if tags:
            out += ['🏷 ' + ' '.join(f'`#{t}`' for t in tags), '']

    out += ['## 全文', '']
    if segments:
        out += [f'*文字来源：{transcript_source}*', '']
        for start, chapter, paras in _sections(segments, info.get('chapters')):
            heading = f'### {format_clock(start)}' + (f' {chapter}' if chapter else '')
            out += [heading, '']
            for p in paras:
                out += [p, '']
    else:
        out += ['（没有获取到字幕，也没有进行语音识别）', '']

    out += [MY_NOTES_HEADING, '', (my_notes or MY_NOTES_TEMPLATE).rstrip(), '']
    return '\n'.join(out)


# ---------------------------------------------------------------- 素材库索引

INDEX_JSONL = 'library.jsonl'
INDEX_MD = '索引.md'


def _cell(text) -> str:
    return str(text).replace('|', '\\|').replace('\n', ' ')


def load_index(root: Path) -> list[dict]:
    path = root / INDEX_JSONL
    if not path.is_file():
        return []
    items = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def find_in_index(root: Path, key: str) -> dict | None:
    for item in reversed(load_index(root)):
        if item.get('key') == key:
            return item
    return None


def save_index(root: Path, items: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / INDEX_JSONL).write_text(
        ''.join(json.dumps(i, ensure_ascii=False) + '\n' for i in items), encoding='utf-8')
    write_index_md(root, items)


def add_to_index(root: Path, entry: dict) -> None:
    items = [i for i in load_index(root) if i.get('key') != entry['key']]
    items.append(entry)
    save_index(root, items)


def _short_source(source: str) -> str:
    if source.startswith('语音识别'):
        return '语音识别'
    if source.startswith('平台人工'):
        return '人工字幕'
    if source.startswith('平台自动'):
        return '自动字幕'
    return source or '无'


def write_index_md(root: Path, items: list[dict]) -> None:
    lines = ['# 素材库索引', '', f'共 **{len(items)}** 条，最新采集的在最上面。', '',
             '| 采集日期 | 平台 | 标题 | 作者 | 时长 | 文字 |', '|---|---|---|---|---|---|']
    for i in sorted(items, key=lambda x: x.get('collected_at', ''), reverse=True):
        link = (Path(i['folder']) / 'note.md').as_posix()
        lines.append(f'| {i.get("collected_at", "")[:10]} | {_cell(platform_name(i.get("platform") or ""))} '
                     f'| [{_cell(i.get("title", ""))}](<{link}>) | {_cell(i.get("uploader", ""))} '
                     f'| {i.get("duration", "")} | {_short_source(i.get("source", ""))} |')
    (root / INDEX_MD).write_text('\n'.join(lines) + '\n', encoding='utf-8')
