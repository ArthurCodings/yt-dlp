from pathlib import Path

from creatorkit.menu import parse_input


def test_parse_douyin_share_text():
    text = '7.43 复制打开抖音，看看【某某的作品】一命速通！ https://v.douyin.com/iRNBho6u/ abc:/ 01/02 Sdy:/'
    urls, files = parse_input(text)
    assert urls == ['https://v.douyin.com/iRNBho6u/'] and files == []


def test_parse_bilibili_share_and_multiple():
    text = ('【守护解放西】总预告-哔哩哔哩】 https://b23.tv/AbCdEf\n'
            'https://www.youtube.com/watch?v=jNQXAC9IVRw\n'
            'https://www.youtube.com/watch?v=jNQXAC9IVRw')
    urls, _ = parse_input(text)
    assert urls == ['https://b23.tv/AbCdEf', 'https://www.youtube.com/watch?v=jNQXAC9IVRw']


def test_parse_dragged_file(tmp_path: Path):
    f = tmp_path / '采访 录音.m4a'
    f.write_bytes(b'x')
    (tmp_path / 'notes.txt').write_text('x')
    urls, files = parse_input(f'"{f}"\n{tmp_path / "notes.txt"}\n{tmp_path / "missing.mp4"}')
    assert urls == [] and files == [f]
