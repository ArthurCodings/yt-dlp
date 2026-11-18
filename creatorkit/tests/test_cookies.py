from pathlib import Path

import pytest

from creatorkit.cookies import cookie_files, merge_cookie_files, resolve_cookiefile, summarize

DOUYIN = '# Netscape HTTP Cookie File\n# comment\n.douyin.com\tTRUE\t/\tFALSE\t0\ts_v_web_id\tverify_x\n' \
         '#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t0\tttwid\tabc\n'
BILI = '﻿.bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tzzz\nnot a cookie line\n'


def test_merge_folder(tmp_path: Path):
    d = tmp_path / 'cookies'
    d.mkdir()
    (d / 'douyin.txt').write_text(DOUYIN, encoding='utf-8')
    (d / 'bilibili.txt').write_text(BILI, encoding='utf-8')
    (d / 'readme.md').write_text('ignore me', encoding='utf-8')
    assert [f.name for f in cookie_files(d)] == ['bilibili.txt', 'douyin.txt']
    out = tmp_path / 'merged.txt'
    assert merge_cookie_files(cookie_files(d), out) == 3
    text = out.read_text(encoding='utf-8')
    assert text.startswith('# Netscape HTTP Cookie File\n')
    assert '#HttpOnly_.douyin.com' in text and 'SESSDATA' in text and 'not a cookie' not in text

    merged = Path(resolve_cookiefile(str(d)))
    assert merged != d and 'SESSDATA' in merged.read_text(encoding='utf-8')
    summary = '\n'.join(summarize(str(d)))
    assert 'douyin.txt：2 条，douyin.com' in summary and 'bilibili.txt：1 条，bilibili.com' in summary


def test_single_file_and_missing(tmp_path: Path):
    f = tmp_path / 'c.txt'
    f.write_text(DOUYIN, encoding='utf-8')
    assert resolve_cookiefile(str(f)) == str(f)
    with pytest.raises(FileNotFoundError):
        resolve_cookiefile(str(tmp_path / 'nope'))
