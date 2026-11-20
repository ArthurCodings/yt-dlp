"""字幕：选择最合适的字幕轨，解析多种格式，输出 SRT / 纯文本段落。"""

from __future__ import annotations

import dataclasses
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


@dataclasses.dataclass
class Segment:
    start: float
    end: float
    text: str
    cont: bool = False  # 这一句在词中间被硬断开，下一句是它的延续


@dataclasses.dataclass
class SubtitleChoice:
    lang: str            # 平台给的语言键，原样用于下载
    automatic: bool      # True 表示平台自动生成的字幕（YouTube 自动字幕 / B 站 AI 字幕）
    in_auto_dict: bool   # 该语言键位于 automatic_captions 中（决定用哪个 yt-dlp 开关下载）


# 不是“对白字幕”的轨道
_SKIP_TRACKS = {'danmaku', 'live_chat', 'comments', 'rechat'}

_HANS = {'zh-hans', 'zh-cn', 'zh-sg', 'zh-my', 'cmn-hans', 'cmn-hans-cn'}
_HANT = {'zh-hant', 'zh-tw', 'zh-hk', 'zh-mo', 'cmn-hant', 'cmn-hant-tw', 'yue', 'yue-hant'}


def normalize_lang(code: str | None) -> str:
    """把各平台五花八门的语言代码规整为 zh-hans / zh-hant / zh / en 之类。"""
    if not code:
        return ''
    c = code.lower().replace('_', '-')
    c = re.sub(r'^ai-', '', c)          # B 站 AI 字幕：ai-zh
    c = re.sub(r'-orig$', '', c)        # YouTube 原语言自动字幕：en-orig
    if c in _HANS:
        return 'zh-hans'
    if c in _HANT:
        return 'zh-hant'
    if c in ('zh', 'cmn', 'chi', 'zho'):
        return 'zh'
    return c


def base_lang(code: str | None) -> str:
    n = normalize_lang(code)
    return 'zh' if n.startswith('zh') else n.split('-')[0]


def _pref_index(key: str, prefer_langs: list[str]) -> int:
    norm = normalize_lang(key)
    prefs = [normalize_lang(p) for p in prefer_langs]
    if norm in prefs:
        return prefs.index(norm)
    base = base_lang(key)
    for i, p in enumerate(prefs):
        if base_lang(p) == base:
            return i + 0.5
    return len(prefs) + 1


def choose_subtitle(info: dict, prefer_langs: list[str]) -> SubtitleChoice | None:
    """挑一条“就是视频原话”的字幕。

    规则：
    1. 人工字幕优先，其次平台自动字幕（YouTube 原语言自动字幕、B 站 AI 字幕）。
    2. 已知视频原语言时，只接受同语言的字幕——其他语言的是翻译，不如直接语音识别。
    3. 永远不用 YouTube 的“自动翻译”字幕。
    """
    orig = base_lang(info.get('language'))
    manual = {k: v for k, v in (info.get('subtitles') or {}).items() if v and k.lower() not in _SKIP_TRACKS}
    auto = {k: v for k, v in (info.get('automatic_captions') or {}).items() if v}

    candidates: list[tuple[tuple, SubtitleChoice]] = []
    for key in manual:
        is_ai = key.lower().startswith('ai-')
        if orig and base_lang(key) != orig:
            continue
        rank = (1 if is_ai else 0, _pref_index(key, prefer_langs))
        candidates.append((rank, SubtitleChoice(key, is_ai, False)))

    for key in auto:
        if key.endswith('-orig'):
            rank = (2, 0)
        elif orig and normalize_lang(key) == normalize_lang(info.get('language')):
            rank = (2, 1)
        else:
            continue  # 自动翻译字幕
        candidates.append((rank, SubtitleChoice(key, True, True)))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


# ---------------------------------------------------------------- 解析

_TS = re.compile(r'(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})')
_TAG = re.compile(r'<[^>]+>')


def _ts(value: str) -> float:
    m = _TS.search(value)
    if not m:
        raise ValueError(f'无法解析时间戳：{value!r}')
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, '0')) / 1000


def _clean(text: str) -> str:
    text = _TAG.sub('', text)
    text = html.unescape(text).replace('​', '')
    text = re.sub(r'[♪♫♬]+', ' ', text)  # 音乐符号（B 站 AI 字幕、YouTube 自动字幕常见）
    return re.sub(r'[ \t]+', ' ', text).strip()


def parse_srt_or_vtt(content: str) -> list[Segment]:
    content = content.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿')
    segments: list[Segment] = []
    last_line = None
    for block in re.split(r'\n\s*\n', content):
        lines = [l for l in block.split('\n') if l.strip()]
        idx = next((i for i, l in enumerate(lines) if '-->' in l), None)
        if idx is None:
            continue
        start_s, _, end_s = lines[idx].partition('-->')
        try:
            start, end = _ts(start_s), _ts(end_s)
        except ValueError:
            continue
        # YouTube 等“滚动式”VTT：每个 cue 会重复上一行，只保留新出现的行
        new_lines = []
        for raw in lines[idx + 1:]:
            line = _clean(raw)
            if line and line != last_line:
                new_lines.append(line)
                last_line = line
        if new_lines:
            segments.append(Segment(start, end, ' '.join(new_lines)))
        elif segments:  # 与上一条完全重复：只延长上一条的结束时间
            segments[-1].end = max(segments[-1].end, end)
    return segments


def parse_json3(content: str) -> list[Segment]:
    data = json.loads(content)
    segments = []
    for ev in data.get('events', []):
        if 'segs' not in ev:
            continue
        text = _clean(''.join(s.get('utf8', '') for s in ev['segs']).replace('\n', ' '))
        if not text:
            continue
        start = ev.get('tStartMs', 0) / 1000
        segments.append(Segment(start, start + ev.get('dDurationMs', 0) / 1000, text))
    return segments


def parse_xml_timed(content: str) -> list[Segment]:
    """srv1 (<text start dur>) / srv3 (<p t d>) / TTML (<p begin end>)。"""
    root = ET.fromstring(content)
    segments = []
    for el in root.iter():
        tag = el.tag.rsplit('}', 1)[-1]
        a = el.attrib
        text = _clean(''.join(el.itertext()))
        if not text:
            continue
        if tag == 'text' and 'start' in a:
            start = float(a['start'])
            end = start + float(a.get('dur', 0))
        elif tag == 'p' and 't' in a:
            start = int(a['t']) / 1000
            end = start + int(a.get('d', 0)) / 1000
        elif tag == 'p' and 'begin' in a:
            start, end = _ttml_time(a['begin']), _ttml_time(a.get('end', a['begin']))
        else:
            continue
        segments.append(Segment(start, end, text))
    return segments


def _ttml_time(v: str) -> float:
    if v.endswith('ms'):
        return float(v[:-2]) / 1000
    if v.endswith('s'):
        return float(v[:-1])
    parts = v.split(':')
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return _ts(v)


def parse_subtitle_file(path: Path) -> list[Segment]:
    content = path.read_text(encoding='utf-8', errors='replace')
    ext = path.suffix.lower().lstrip('.')
    if ext == 'json3':
        segs = parse_json3(content)
    elif ext in ('srv1', 'srv2', 'srv3', 'ttml', 'xml', 'dfxp'):
        segs = parse_xml_timed(content)
    else:
        segs = parse_srt_or_vtt(content)
    return merge_duplicates(segs)


def merge_duplicates(segments: list[Segment]) -> list[Segment]:
    out: list[Segment] = []
    for seg in segments:
        if out and seg.text == out[-1].text and seg.start - out[-1].end < 0.5:
            out[-1].end = max(out[-1].end, seg.end)
        else:
            out.append(seg)
    return out


# ---------------------------------------------------------------- 语音识别结果重新断句

_STRONG = tuple('。！？!?….')
_WEAK = tuple('，,、；;：:')


def _visual_len(text: str) -> float:
    """字幕长度：中日韩字符算 1，其他字符算 0.5。"""
    return sum(1 if _CJK.match(ch) else 0.5 for ch in text)


def regroup_words(words: list[tuple[float, float, str]], max_len: float = 22, max_dur: float = 7.0) -> list[Segment]:
    """把逐词时间戳重新组合成适合做字幕的短句。

    句末标点必断；逗号处够长就断；超长/超时时先退回最近的逗号断开，
    没有逗号才硬断，并标记 cont=True（合并全文时不在断点加逗号）。
    """
    def emit(ws, cont=False):
        segments.append(Segment(ws[0][0], ws[-1][1], ''.join(w[2] for w in ws).strip(), cont))

    def boundary_after(i: int) -> bool:
        """buf[i] 之后是否是自然停顿：标点，或中文之间的空格（Whisper 常用空格代替逗号）。"""
        if buf[i][2].strip().endswith(_STRONG + _WEAK):
            return True
        nxt = buf[i + 1][2] if i + 1 < len(buf) else ''
        return (nxt[:1].isspace() and bool(_CJK.match(buf[i][2].strip()[-1:] or ' '))
                and bool(_CJK.match(nxt.strip()[:1] or ' ')))

    segments: list[Segment] = []
    buf: list[tuple[float, float, str]] = []
    for word in words:
        if not word[2].strip():
            continue
        buf.append(word)
        if len(buf) > 1 and boundary_after(len(buf) - 2) \
                and _visual_len(''.join(w[2] for w in buf[:-1]).strip()) >= max_len * 0.5:
            emit(buf[:-1])  # 中文空格停顿处，前面已经够长：在空格处断开
            buf = buf[-1:]
        text = ''.join(w[2] for w in buf).strip()
        length = _visual_len(text)
        if text.endswith(_STRONG) or (text.endswith(_WEAK) and length >= max_len * 0.5):
            emit(buf)
            buf = []
        elif length >= max_len or buf[-1][1] - buf[0][0] >= max_dur:
            cut = next((i for i in range(len(buf) - 2, 0, -1) if boundary_after(i)), None)
            if cut is not None:
                emit(buf[:cut + 1])
                buf = buf[cut + 1:]
            else:
                emit(buf, cont=True)
                buf = []
    if buf:
        emit(buf)
    return segments


# ---------------------------------------------------------------- 输出

def format_srt_time(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def format_clock(t: float) -> str:
    t = int(t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


def to_srt(segments: list[Segment]) -> str:
    return ''.join(
        f'{i}\n{format_srt_time(s.start)} --> {format_srt_time(s.end)}\n{s.text}\n\n'
        for i, s in enumerate(segments, 1))


_CJK = re.compile(r'[぀-ヿ㐀-鿿가-힯豈-﫿]')
_END_PUNCT = tuple('。！？!?…」』”"')
_ANY_PUNCT = _END_PUNCT + tuple('，,、；;：:.')


def _join(a: str, b: str, cont: bool = False) -> str:
    if not a:
        return b
    if cont:  # 上一句是在词中间被硬断的：直接接上
        return a + b if _CJK.search(a[-1]) or _CJK.search(b[0]) else a + ' ' + b
    if _CJK.search(a[-1]) and _CJK.search(b[0]):
        return a + b if a.endswith(_ANY_PUNCT) else a + '，' + b
    if a.endswith(('，', '。', '！', '？', '、', '；', '：')):
        return a + b
    return a + ' ' + b


def to_paragraphs(segments: list[Segment], gap: float = 2.0, max_chars: int = 150) -> list[tuple[float, str]]:
    """把零碎字幕行合并成段落，返回 [(段落开始时间, 文本)]。

    分段时机：停顿超过 gap 秒；够长（max_chars）且在句末；明显过长（1.4 倍）时在任意停顿处。
    """
    paragraphs: list[tuple[float, str]] = []
    start, buf, prev_end, prev_cont = None, '', None, False
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        brk = buf and not prev_cont and (
            (prev_end is not None and seg.start - prev_end > gap)
            or (len(buf) >= max_chars and buf.endswith(_END_PUNCT))
            or len(buf) >= max_chars * 1.4)
        if brk:
            paragraphs.append((start, _finish(buf)))
            start, buf = None, ''
        if start is None:
            start = seg.start
        buf = _join(buf, text, prev_cont)
        prev_end, prev_cont = seg.end, seg.cont
    if buf:
        paragraphs.append((start, _finish(buf)))
    return paragraphs


def _finish(text: str) -> str:
    text = text.strip().rstrip('，,')
    if text and _CJK.search(text[-1]) and not text.endswith(_END_PUNCT):
        text += '。'
    return text


def save_segments(segments: list[Segment], path: Path) -> None:
    """完整保存逐句数据（含 cont 标记），供重新生成笔记时使用。"""
    path.write_text(json.dumps([dataclasses.asdict(s) for s in segments], ensure_ascii=False, indent=0),
                    encoding='utf-8')


def load_segments(path: Path) -> list[Segment]:
    return [Segment(**d) for d in json.loads(path.read_text(encoding='utf-8'))]


def to_plain_text(segments: list[Segment]) -> str:
    return '\n\n'.join(p for _, p in to_paragraphs(segments)) + '\n'
