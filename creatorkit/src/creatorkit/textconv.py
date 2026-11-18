"""简繁转换（OpenCC）。"""

from __future__ import annotations

import functools
import re

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


_CJK = r'[㐀-鿿豈-﫿]'
_HALF_TO_FULL = {',': '，', '?': '？', '!': '！', ':': '：', ';': '；'}


def normalize_cjk_punct(text: str) -> str:
    """中文语境里的半角标点 → 全角（“好,我们” → “好，我们”），不影响英文和数字。"""
    text = re.sub(rf'(?<={_CJK})([,?!:;])\s*', lambda m: _HALF_TO_FULL[m.group(1)], text)
    # 中文之间的空格是 Whisper 用来表示停顿的，换成逗号
    return re.sub(rf'(?<={_CJK})\s+(?={_CJK})', '，', text)


def convert_segments(segments: list[Segment], script: str) -> list[Segment]:
    return [Segment(s.start, s.end, normalize_cjk_punct(convert_text(s.text, script)), s.cont) for s in segments]
