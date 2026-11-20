import json
from pathlib import Path

from creatorkit.notes import (
    INDEX_MD, display_title, extract_my_notes, extract_tags, load_index, platform_name, render_note, save_index,
)
from creatorkit.rebuild import rebuild_library
from creatorkit.subtitles import Segment, save_segments, to_srt

DOUYIN = {
    'id': '7682768843856563519', 'extractor_key': 'Douyin', 'uploader': 'shuiqiupao68', 'upload_date': '20260907',
    'duration': 1612, 'webpage_url': 'https://www.douyin.com/video/7682768843856563519',
    'title': '成功唯一的燃料，是一段"成功记忆" 判断一个人能不能出彩，只看一件事——他能不能塌下心、耐着性子，去做一件没人理解的事',
    'description': '成功唯一的燃料，是一段"成功记忆" 判断一个人能不能出彩，只看一件事。\n'
                   '练出来的方法，就是逼自己走通一条长路。\n#个人成长 #认知升级 #人生智慧',
    'like_count': 13000, 'comment_count': 279, 'repost_count': 2455, 'view_count': 0,
}


def test_display_title():
    assert display_title(DOUYIN) == '成功唯一的燃料，是一段"成功记忆"'
    assert display_title({'extractor_key': 'Douyin', 'title': '今天聊聊剪辑。后面还有很多 #教程'}) == '今天聊聊剪辑'
    assert display_title({'extractor_key': 'BiliBili', 'title': '【官方 MV】Never Gonna Give You Up'}) == \
        '【官方 MV】Never Gonna Give You Up'
    long_no_sep = {'extractor_key': 'TikTok', 'title': '一' * 60}
    assert display_title(long_no_sep) == '一' * 32 + '…'
    assert display_title({'id': 'abc'}) == 'abc'


def test_tags_and_platform():
    assert extract_tags(DOUYIN) == ['个人成长', '认知升级', '人生智慧']
    assert extract_tags({'tags': ['a', 'b'], 'description': '#b #c'}) == ['a', 'b', 'c']
    assert platform_name(DOUYIN) == '抖音' and platform_name('BiliBiliBangumi') == 'B站'
    assert platform_name('SomethingNew') == 'SomethingNew'


def test_render_douyin_note():
    segs = [Segment(0, 2, '我这句话赌上我13年的教学生涯。'), Segment(2, 4, '我教过很多学生。'),
            Segment(200, 202, '第二节的内容。')]
    md = render_note(DOUYIN, segs, '语音识别（large-v3-turbo，zh）',
                     {'视频': 'video.mp4', '字幕': 'transcript.srt', '封面': 'cover.jpeg'}, collected_at='2026-11-21 00:14')
    assert md.startswith('---\ntitle: "成功唯一的燃料，是一段\\"成功记忆\\""\nplatform: "抖音"\n')
    assert 'tags: ["个人成长", "认知升级", "人生智慧"]' in md
    assert '# 成功唯一的燃料，是一段"成功记忆"\n' in md
    assert '> **抖音** · @shuiqiupao68 · 2026-09-07 · ⏱ 26:52' in md
    assert '[▶ 原视频](https://www.douyin.com/video/7682768843856563519) · [视频](<video.mp4>)' in md
    assert '<img src="cover.jpeg" width="220">' in md
    # 不显示点赞/评论/转发/播放
    for word in ('点赞', '评论', '转发', '播放', '1.3 万', '2455'):
        assert word not in md, word
    # 简介去掉话题标签并分段，标签单独一行
    assert '练出来的方法，就是逼自己走通一条长路。' in md and '\n#个人成长' not in md
    assert '🏷 `#个人成长` `#认知升级` `#人生智慧`' in md
    # 全文每约 3 分钟一节
    assert '### 00:00\n\n我这句话赌上我13年的教学生涯。我教过很多学生。' in md
    assert '### 03:20\n\n第二节的内容。' in md
    assert md.rstrip().endswith('- **选题灵感**：')


def test_chapters_and_long_description():
    info = {'title': 'A talk', 'extractor_key': 'Youtube', 'description': '\n'.join(f'line {i}' for i in range(15)),
            'chapters': [{'start_time': 0, 'title': 'Intro'}, {'start_time': 60, 'title': 'Main'}]}
    md = render_note(info, [Segment(1, 2, 'Hello.'), Segment(70, 71, 'Core idea.')], '平台人工字幕（en）', {})
    assert '### 00:00 Intro\n\nHello.' in md and '### 01:00 Main\n\nCore idea.' in md
    assert '<summary>展开简介</summary>' in md


def test_my_notes_preserved():
    template_note = render_note({'title': 't'}, [], '无', {})
    assert extract_my_notes(template_note) is None
    edited = template_note.replace('- **金句**：', '- **金句**：成功需要记忆')
    assert '成功需要记忆' in extract_my_notes(edited)
    again = render_note({'title': 't'}, [], '无', {}, my_notes=extract_my_notes(edited))
    assert '成功需要记忆' in again and again.count('## 我的笔记') == 1


def test_rebuild_library(tmp_path: Path):
    folder = tmp_path / 'Douyin' / 'x'
    folder.mkdir(parents=True)
    (folder / 'meta.info.json').write_text(json.dumps(DOUYIN, ensure_ascii=False), encoding='utf-8')
    (folder / 'transcript.srt').write_text(to_srt([Segment(0, 1, '你好。')]), encoding='utf-8-sig')
    (folder / 'video.mp4').write_bytes(b'x')
    (folder / 'cover.jpeg').write_bytes(b'x')
    (folder / 'note.md').write_text('# old\n\n## 我的笔记\n\n- 我自己写的想法\n', encoding='utf-8')
    save_index(tmp_path, [
        {'key': 'Douyin:1', 'folder': 'Douyin/x', 'title': '很长很长的旧标题', 'platform': 'Douyin',
         'source': '语音识别（large-v3-turbo，zh）', 'collected_at': '2026-11-21 00:14'},
        {'key': 'Douyin:2', 'folder': 'Douyin/gone', 'title': 'gone', 'collected_at': '2026-11-20 00:00'},
    ])
    # 有 transcript.json 时优先使用（保留“词中间硬断”的标记，不会多出逗号）
    save_segments([Segment(0, 1, '我认为一定能出彩的一个', cont=True), Segment(1, 2, '人。')], folder / 'transcript.json')
    assert rebuild_library(tmp_path, log=lambda *_: None) == (1, 1)
    assert '能出彩的一个人。' in (folder / 'transcript.txt').read_text(encoding='utf-8')
    note = (folder / 'note.md').read_text(encoding='utf-8')
    assert '- 我自己写的想法' in note and '[视频](<video.mp4>)' in note and 'cover.jpeg' in note
    assert load_index(tmp_path)[0]['title'] == '成功唯一的燃料，是一段"成功记忆"'
    index = (tmp_path / INDEX_MD).read_text(encoding='utf-8')
    assert '| 2026-11-21 | 抖音 | [成功唯一的燃料' in index and '| 语音识别 |' in index
