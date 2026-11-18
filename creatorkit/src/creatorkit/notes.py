"""生成笔记（note.md）和素材库索引。"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .subtitles import Segment, format_clock, to_paragraphs


def _fmt_date(upload_date: str | None) -> str:
    if upload_date and len(upload_date) == 8 and upload_date.isdigit():
        return f'{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}'
    return '未知'


def _fmt_num(n) -> str | None:
    if n is None:
        return None
    if n >= 100_000_000:
        return f'{n / 100_000_000:.1f} 亿'
    if n >= 10_000:
        return f'{n / 10_000:.1f} 万'
    return str(n)


def _cell(text) -> str:
    return str(text).replace('|', '\\|').replace('\n', ' ')


def render_note(info: dict, segments: list[Segment], transcript_source: str, files: dict[str, str]) -> str:
    title = info.get('title') or info.get('id') or '未命名'
    uploader = info.get('uploader') or info.get('channel') or info.get('creator') or '未知'
    url = info.get('webpage_url') or info.get('original_url') or ''
    rows = [
        ('平台', info.get('extractor_key') or info.get('extractor') or '未知'),
        ('作者', uploader),
        ('发布日期', _fmt_date(info.get('upload_date'))),
        ('时长', format_clock(info['duration']) if info.get('duration') else '未知'),
        ('链接', url),
    ]
    stats = [(label, _fmt_num(info.get(key))) for label, key in
             (('播放', 'view_count'), ('点赞', 'like_count'), ('评论', 'comment_count'), ('转发', 'repost_count'))]
    stats = [f'{label} {v}' for label, v in stats if v]
    if stats:
        rows.append(('数据', ' · '.join(stats)))
    rows.append(('文字来源', transcript_source))
    rows.append(('采集时间', dt.datetime.now().strftime('%Y-%m-%d %H:%M')))
    if files:
        rows.append(('文件', ' · '.join(f'[{k}]({v})' for k, v in files.items())))

    out = [f'# {title}', '', '| 项目 | 内容 |', '|---|---|']
    out += [f'| {k} | {_cell(v)} |' for k, v in rows]

    desc = (info.get('description') or '').strip()
    if desc and desc != title:
        out += ['', '## 简介', '', desc]
    tags = info.get('tags') or []
    if tags:
        out += ['', '## 标签', '', ' '.join(f'`#{t}`' for t in tags[:30])]

    out += ['', '## 全文', '']
    if segments:
        for start, para in to_paragraphs(segments):
            out += [f'**[{format_clock(start)}]** {para}', '']
    else:
        out += ['（没有获取到字幕，也没有进行语音识别）', '']

    out += ['## 我的笔记', '', '- ', '']
    return '\n'.join(out)


# ---------------------------------------------------------------- 素材库索引

INDEX_JSONL = 'library.jsonl'
INDEX_MD = '索引.md'


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


def add_to_index(root: Path, entry: dict) -> None:
    items = [i for i in load_index(root) if i.get('key') != entry['key']]
    items.append(entry)
    root.mkdir(parents=True, exist_ok=True)
    (root / INDEX_JSONL).write_text(
        ''.join(json.dumps(i, ensure_ascii=False) + '\n' for i in items), encoding='utf-8')
    write_index_md(root, items)


def write_index_md(root: Path, items: list[dict]) -> None:
    lines = ['# 素材库索引', '', f'共 {len(items)} 条，按采集时间倒序。', '',
             '| 采集时间 | 平台 | 作者 | 标题 | 时长 | 文字来源 |', '|---|---|---|---|---|---|']
    for i in sorted(items, key=lambda x: x.get('collected_at', ''), reverse=True):
        note = Path(i['folder']) / 'note.md'
        link = note.as_posix()
        lines.append(f'| {i.get("collected_at", "")} | {_cell(i.get("platform", ""))} | {_cell(i.get("uploader", ""))} '
                     f'| [{_cell(i.get("title", ""))}](<{link}>) | {i.get("duration", "")} | {_cell(i.get("source", ""))} |')
    (root / INDEX_MD).write_text('\n'.join(lines) + '\n', encoding='utf-8')
