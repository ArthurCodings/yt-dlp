"""简繁转换（OpenCC）。"""

from __future__ import annotations

import functools

from .subtitles import Segment

_OPENCC_CONFIG = {
    'hans': 't2s',     # 繁 → 简
    'hant': 's2twp',   # 简 → 繁（台湾正体，含常用词转换）
    'hk': 's2hk',      # 简 → 繁（香港）
}


@functools.cache
def _converter(script: str):
    from opencc import OpenCC
    return OpenCC(_OPENCC_CONFIG[script])


def convert_text(text: str, script: str) -> str:
    if script == 'keep' or not text:
        return text
    if script == 'hant':
        # 先统一成简体再转台湾繁体，避免繁体原文被二次转换出错
        # OpenCC 会把“台”转成正式写法“臺”，台湾日常书写（台中、台北、电视台）一般用“台”
        return _converter('hant').convert(_converter('hans').convert(text)).replace('臺', '台')
    return _converter(script).convert(text)


def convert_segments(segments: list[Segment], script: str) -> list[Segment]:
    if script == 'keep':
        return segments
    return [Segment(s.start, s.end, convert_text(s.text, script)) for s in segments]
