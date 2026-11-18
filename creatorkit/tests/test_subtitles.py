import json
from pathlib import Path

import pytest

from creatorkit.subtitles import (
    Segment, choose_subtitle, normalize_lang, parse_json3, parse_srt_or_vtt, parse_subtitle_file,
    parse_xml_timed, to_paragraphs, to_plain_text, to_srt,
)

PREFS = ['zh-hans', 'zh-hant', 'zh', 'en', 'ja']


@pytest.mark.parametrize('code, expected', [
    ('zh-Hans', 'zh-hans'), ('zh-CN', 'zh-hans'), ('zh-TW', 'zh-hant'), ('zh-HK', 'zh-hant'),
    ('ai-zh', 'zh'), ('en-orig', 'en'), ('en-US', 'en-us'), ('', ''), (None, ''),
])
def test_normalize_lang(code, expected):
    assert normalize_lang(code) == expected


def _sub():
    return [{'ext': 'vtt', 'url': 'http://x'}]


class TestChooseSubtitle:
    def test_manual_same_language_wins(self):
        info = {'language': 'zh', 'subtitles': {'en': _sub(), 'zh-Hant': _sub()},
                'automatic_captions': {'zh-orig': _sub()}}
        c = choose_subtitle(info, PREFS)
        assert (c.lang, c.automatic, c.in_auto_dict) == ('zh-Hant', False, False)

    def test_manual_other_language_is_translation(self):
        info = {'language': 'zh', 'subtitles': {'en': _sub()}, 'automatic_captions': {}}
        assert choose_subtitle(info, PREFS) is None

    def test_youtube_orig_auto_caption(self):
        info = {'language': 'en', 'subtitles': {'live_chat': _sub()},
                'automatic_captions': {'en-orig': _sub(), 'en': _sub(), 'zh-Hans': _sub()}}
        c = choose_subtitle(info, PREFS)
        assert (c.lang, c.automatic, c.in_auto_dict) == ('en-orig', True, True)

    def test_never_use_auto_translation(self):
        info = {'language': 'ja', 'subtitles': {}, 'automatic_captions': {'zh-Hans': _sub(), 'en': _sub()}}
        assert choose_subtitle(info, PREFS) is None

    def test_bilibili_ai_subtitle_and_danmaku(self):
        info = {'subtitles': {'danmaku': [{'ext': 'xml'}], 'ai-zh': [{'ext': 'srt'}]}}
        c = choose_subtitle(info, PREFS)
        assert (c.lang, c.automatic, c.in_auto_dict) == ('ai-zh', True, False)

    def test_human_beats_ai(self):
        info = {'subtitles': {'ai-zh': _sub(), 'zh-CN': _sub()}}
        assert choose_subtitle(info, PREFS).lang == 'zh-CN'

    def test_unknown_language_uses_preference(self):
        info = {'subtitles': {'ja': _sub(), 'en': _sub(), 'zh-TW': _sub()}}
        assert choose_subtitle(info, PREFS).lang == 'zh-TW'

    def test_nothing(self):
        assert choose_subtitle({}, PREFS) is None


def test_parse_srt():
    srt = '﻿1\r\n00:00:01,000 --> 00:00:02,500\r\n你好\r\n世界\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\n<i>再见</i>\r\n'
    segs = parse_srt_or_vtt(srt)
    assert [(s.start, s.end, s.text) for s in segs] == [(1.0, 2.5, '你好 世界'), (3.0, 4.0, '再见')]


def test_music_symbols_removed():
    srt = '1\n00:00:00,000 --> 00:00:01,000\n♪ ♪\n\n2\n00:00:01,000 --> 00:00:02,000\n♪ 点击即玩 ♪\n'
    assert [s.text for s in parse_srt_or_vtt(srt)] == ['点击即玩']


def test_parse_rolling_vtt_dedupes():
    vtt = """WEBVTT
Kind: captions

00:00:00.000 --> 00:00:02.000 align:start
hello<00:00:00.500><c> there</c>

00:00:02.000 --> 00:00:02.010
hello there

00:00:02.010 --> 00:00:04.000
hello there
general kenobi
"""
    segs = parse_srt_or_vtt(vtt)
    assert [s.text for s in segs] == ['hello there', 'general kenobi']


def test_parse_json3():
    data = {'events': [
        {'tStartMs': 0, 'dDurationMs': 1500, 'segs': [{'utf8': 'Hello '}, {'utf8': 'world'}]},
        {'tStartMs': 1500, 'dDurationMs': 10, 'segs': [{'utf8': '\n'}]},
        {'tStartMs': 2000, 'dDurationMs': 1000},
    ]}
    segs = parse_json3(json.dumps(data))
    assert [(s.start, s.end, s.text) for s in segs] == [(0.0, 1.5, 'Hello world')]


def test_parse_srv1_and_ttml():
    srv1 = '<transcript><text start="1.5" dur="2">a &amp;amp; b</text></transcript>'
    assert [(s.start, s.end, s.text) for s in parse_xml_timed(srv1)] == [(1.5, 3.5, 'a & b')]
    ttml = ('<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
            '<p begin="00:00:01.000" end="00:00:02.000">第一句</p></div></body></tt>')
    assert [(s.start, s.end, s.text) for s in parse_xml_timed(ttml)] == [(1.0, 2.0, '第一句')]


def test_parse_subtitle_file_by_extension(tmp_path: Path):
    f = tmp_path / 'video.zh.srt'
    f.write_text('1\n00:00:00,000 --> 00:00:01,000\n同一句\n\n2\n00:00:01,100 --> 00:00:02,000\n同一句\n', encoding='utf-8')
    segs = parse_subtitle_file(f)
    assert len(segs) == 1 and segs[0].end == 2.0


def test_to_srt():
    out = to_srt([Segment(0, 1.2345, 'a'), Segment(3661.5, 3662, 'b')])
    assert out == '1\n00:00:00,000 --> 00:00:01,234\na\n\n2\n01:01:01,500 --> 01:01:02,000\nb\n\n' or \
        out == '1\n00:00:00,000 --> 00:00:01,235\na\n\n2\n01:01:01,500 --> 01:01:02,000\nb\n\n'


def test_paragraphs_join_chinese_and_english():
    segs = [Segment(0, 1, '大家好'), Segment(1, 2, '今天聊聊剪辑'), Segment(2, 3, '好的。'),
            Segment(10, 11, 'hello'), Segment(11, 12, 'world')]
    paras = to_paragraphs(segs)
    assert paras == [(0, '大家好，今天聊聊剪辑，好的。'), (10, 'hello world')]
    assert to_plain_text(segs) == '大家好，今天聊聊剪辑，好的。\n\nhello world\n'


def test_paragraphs_split_long_text():
    segs = [Segment(i, i + 1, '这是一句比较长的话。' * 3) for i in range(20)]
    paras = to_paragraphs(segs, max_chars=100)
    assert len(paras) > 3
    assert all(p.endswith('。') for _, p in paras)
