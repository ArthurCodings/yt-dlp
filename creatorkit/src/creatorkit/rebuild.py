"""用已保存的数据重新生成笔记（模板更新后使用），不重新下载、不重新识别。"""

from __future__ import annotations

import json
from pathlib import Path

from .notes import display_title, extract_my_notes, load_index, render_note, save_index
from .subtitles import load_segments, parse_subtitle_file, to_plain_text

VIDEO_EXTS = {'.mp4', '.mkv', '.webm', '.mov', '.flv', '.m4v'}
AUDIO_EXTS = {'.m4a', '.mp3', '.opus', '.ogg', '.flac', '.wav', '.aac'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}


def collect_files(folder: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for f in sorted(folder.iterdir()):
        if f.stem == 'video' and f.suffix.lower() in VIDEO_EXTS:
            files.setdefault('视频', f.name)
        elif f.stem == 'audio' and f.suffix.lower() in AUDIO_EXTS:
            files.setdefault('音频', f.name)
    if (folder / 'transcript.srt').is_file():
        files['字幕'] = 'transcript.srt'
    if (folder / 'transcript.txt').is_file():
        files['全文'] = 'transcript.txt'
    cover = next((f for f in sorted(folder.glob('cover.*')) if f.suffix.lower() in IMAGE_EXTS), None)
    if cover:
        files['封面'] = cover.name
    return files


def rebuild_note(folder: Path, entry: dict) -> bool:
    meta = folder / 'meta.info.json'
    if not meta.is_file():  # 早期版本的文件名
        meta = next(folder.glob('*.info.json'), None)
        if meta is None:
            return False
    info = json.loads(meta.read_text(encoding='utf-8'))
    srt, data = folder / 'transcript.srt', folder / 'transcript.json'
    if data.is_file():
        segments = load_segments(data)
    else:  # 早期采集的没有 transcript.json
        segments = parse_subtitle_file(srt) if srt.is_file() else []
    if segments:  # 全文也按最新规则重新分段
        (folder / 'transcript.txt').write_text(to_plain_text(segments), encoding='utf-8')
    note = folder / 'note.md'
    my_notes = extract_my_notes(note.read_text(encoding='utf-8')) if note.is_file() else None
    note.write_text(render_note(info, segments, entry.get('source') or '无', collect_files(folder), my_notes,
                                collected_at=entry.get('collected_at')), encoding='utf-8')
    entry['title'] = display_title(info)
    return True


def rebuild_library(root: Path, log=print) -> tuple[int, int]:
    items = load_index(root)
    done = missing = 0
    for entry in items:
        folder = root / entry['folder']
        if folder.is_dir() and rebuild_note(folder, entry):
            done += 1
            log(f'  ✓ {entry["title"]}')
        else:
            missing += 1
            log(f'  · 跳过（文件夹或 meta.info.json 不存在）：{entry["folder"]}')
    save_index(root, items)
    return done, missing
