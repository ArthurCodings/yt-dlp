from pathlib import Path

import pytest

from creatorkit.cli import build_parser
from creatorkit.config import load_config
from creatorkit.notes import INDEX_MD, add_to_index, find_in_index, load_index, render_note
from creatorkit.pipeline import _explain_error, _find_media, parse_browser_spec
from creatorkit.subtitles import Segment
from creatorkit.textconv import convert_segments, convert_text


def test_textconv():
    assert convert_text('軟體與網路', 'hans') == '软体与网路'
    assert convert_text('软件和网络', 'hant') == '軟體和網路'
    assert convert_text('台中市警方', 'hant') == '台中市警方'
    assert convert_text('軟體', 'keep') == '軟體'
    assert convert_segments([Segment(0, 1, '這個')], 'hans')[0].text == '这个'


def test_cjk_punctuation():
    from creatorkit.textconv import normalize_cjk_punct
    assert normalize_cjk_punct('好,我们直接开始。真的吗?是的!') == '好，我们直接开始。真的吗？是的！'
    assert normalize_cjk_punct('Hello, world: 1,000') == 'Hello, world: 1,000'
    assert normalize_cjk_punct('原本的工作 台中市第四分局 LED背心') == '原本的工作，台中市第四分局 LED背心'
    assert convert_segments([Segment(0, 1, '來了,我們')], 'keep')[0].text == '來了，我們'


def test_asr_context():
    from creatorkit.pipeline import asr_context
    info = {'title': '《面容》一命速通！ #Steam游戏 #恐怖游戏', 'tags': ['恐怖游戏', '速通技巧']}
    assert asr_context(info) == '《面容》一命速通！ Steam游戏 恐怖游戏 速通技巧'
    assert asr_context({}) == ''


def test_config_file_and_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.delenv('CK_CONFIG', raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'nohome')
    (tmp_path / 'creatorkit.toml').write_text('mode = "audio"\nscript = "hant"\n', encoding='utf-8')
    cfg, used = load_config(overrides={'script': 'keep', 'model': None})
    assert used == tmp_path / 'creatorkit.toml'
    assert (cfg.mode, cfg.script, cfg.model) == ('audio', 'keep', 'large-v3-turbo')


def test_config_rejects_bad_values(tmp_path: Path):
    bad = tmp_path / 'a.toml'
    bad.write_text('nope = 1\n', encoding='utf-8')
    with pytest.raises(ValueError, match='未知配置项'):
        load_config(str(bad))
    empty = tmp_path / 'empty.toml'
    empty.write_text('', encoding='utf-8')
    with pytest.raises(ValueError, match='mode'):
        load_config(str(empty), {'mode': 'movie'})
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / 'missing.toml'))


def test_render_note():
    info = {'title': '测试视频', 'uploader': '某作者', 'extractor_key': 'BiliBili', 'upload_date': '20261101',
            'duration': 125, 'webpage_url': 'https://b23.tv/x', 'view_count': 123456, 'like_count': 99,
            'description': '这是简介', 'tags': ['剪辑', '教程']}
    md = render_note(info, [Segment(0, 1, '大家好'), Segment(5, 6, '再见')], '平台人工字幕（zh-CN）',
                     {'视频': 'video.mp4'})
    for expected in ('# 测试视频', '| 作者 | 某作者 |', '2026-11-01', '02:05', '播放 12.3 万', '## 简介',
                     '`#剪辑`', '**[00:00]** 大家好。', '**[00:05]** 再见。', '[视频](video.mp4)', '## 我的笔记'):
        assert expected in md, expected


def test_index(tmp_path: Path):
    add_to_index(tmp_path, {'key': 'A:1', 'folder': 'A/x', 'title': 't1', 'collected_at': '2026-01-01 00:00'})
    add_to_index(tmp_path, {'key': 'A:2', 'folder': 'A/y z', 'title': 't2', 'collected_at': '2026-01-02 00:00'})
    add_to_index(tmp_path, {'key': 'A:1', 'folder': 'A/x', 'title': 't1-new', 'collected_at': '2026-01-03 00:00'})
    assert [i['title'] for i in load_index(tmp_path)] == ['t2', 't1-new']
    assert find_in_index(tmp_path, 'A:1')['title'] == 't1-new'
    assert find_in_index(tmp_path, 'nope') is None
    md = (tmp_path / INDEX_MD).read_text(encoding='utf-8')
    assert md.index('t1-new') < md.index('t2')
    assert '(<A/y z/note.md>)' in md


def test_find_media(tmp_path: Path):
    for name in ('video.zh.srt', 'video.mp4.part', 'cover.jpg', 'video.mp4'):
        (tmp_path / name).write_text('x')
    assert _find_media(tmp_path, 'video').name == 'video.mp4'
    assert _find_media(tmp_path, 'audio') is None


def test_probe_requests_subtitles(tmp_path: Path):
    from creatorkit.config import Config
    from creatorkit.pipeline import Pipeline
    p = Pipeline(Config(output_dir=str(tmp_path), max_items=5))._probe_params()
    # 否则 B 站等“懒加载字幕”的提取器在解析阶段不会返回字幕
    assert p['writesubtitles'] and p['writeautomaticsub'] and p['skip_download']
    assert p['playlistend'] == 5


def test_browser_spec():
    assert parse_browser_spec('Firefox') == ('firefox', None, None, None)
    assert parse_browser_spec('chrome:Profile 1') == ('chrome', 'Profile 1', None, None)


def test_error_hints():
    assert 'douyin.txt' in _explain_error('ERROR: [Douyin] 1: Fresh cookies (not necessarily logged in) are needed')


def test_cli_parser():
    args = build_parser().parse_args(['get', 'https://a', 'https://b', '-m', 'text', '--max', '3'])
    assert (args.urls, args.mode, args.max_items, args.keep_audio) == (['https://a', 'https://b'], 'text', 3, None)
