from pathlib import Path

import pytest

from creatorkit.cli import build_parser
from creatorkit.douyin_browser import extract_video_id, is_douyin_url, load_cookies_for_playwright


@pytest.mark.parametrize('url, expected', [
    ('https://www.douyin.com/video/7707894307008564530', True),
    ('https://v.douyin.com/iRNBho6u/', True),
    ('https://www.iesdouyin.com/share/video/7707894307008564530/', True),
    ('https://www.douyin.com/jingxuan?modal_id=7707894307008564530', True),
    ('https://www.tiktok.com/@a/video/1', False),
    ('https://example.com/?u=douyin.com.evil', False),
])
def test_is_douyin_url(url, expected):
    assert is_douyin_url(url) is expected


@pytest.mark.parametrize('url, expected', [
    ('https://www.douyin.com/video/7707894307008564530?previous_page=x', '7707894307008564530'),
    ('https://www.douyin.com/user/MS4w?modal_id=7707633990651350308', '7707633990651350308'),
    ('https://www.iesdouyin.com/share/video/7687101640054246708/?region=CN', '7687101640054246708'),
    ('https://v.douyin.com/iRNBho6u/', None),
])
def test_extract_video_id(url, expected):
    assert extract_video_id(url) == expected


def test_load_cookies_for_playwright(tmp_path: Path):
    f = tmp_path / 'c.txt'
    f.write_text(
        '# Netscape HTTP Cookie File\n'
        '.douyin.com\tTRUE\t/\tFALSE\t1900000000\ts_v_web_id\tverify_x\n'
        '#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc\n'
        '.bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tzzz\n', encoding='utf-8')
    cookies = load_cookies_for_playwright(str(f))
    assert [c['name'] for c in cookies] == ['s_v_web_id', 'sessionid']
    assert cookies[0]['expires'] == 1900000000 and not cookies[0]['httpOnly']
    assert 'expires' not in cookies[1] and cookies[1]['httpOnly'] and cookies[1]['secure']
    assert load_cookies_for_playwright(None) == []


def test_show_browser_flag():
    assert build_parser().parse_args(['get', 'u', '--show-browser']).browser_headless is False
    assert build_parser().parse_args(['get', 'u']).browser_headless is None
