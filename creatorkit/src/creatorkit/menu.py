"""交互式菜单：双击启动后粘贴链接即可，不需要记命令。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .config import load_config

URL_RE = re.compile(r'https?://[^\s，。、；！？“”‘’"\'<>【】（）()]+')
MEDIA_SUFFIXES = {'.mp4', '.mkv', '.mov', '.webm', '.flv', '.avi', '.m4a', '.mp3', '.wav', '.flac', '.aac', '.ogg', '.opus'}

MODES = {
    '1': ('video', '视频 + 文字'),
    '2': ('audio', '只要音频 + 文字'),
    '3': ('text', '只要文字（最快，不保存视频）'),
}


def parse_input(text: str) -> tuple[list[str], list[Path]]:
    """从粘贴的内容里找出链接和本地文件。

    支持直接粘贴抖音/B 站 App 的分享文字，例如：
    “7.43 复制打开抖音，看看【某某的作品】…… https://v.douyin.com/xxxx/ ……”
    """
    urls: list[str] = []
    files: list[Path] = []
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip('.,;:!?')
        if url not in urls:
            urls.append(url)
    for line in text.splitlines():
        candidate = line.strip().strip('"').strip("'")
        if candidate and not URL_RE.search(candidate):
            p = Path(candidate)
            if p.suffix.lower() in MEDIA_SUFFIXES and p.is_file() and p not in files:
                files.append(p)
    return urls, files


def _read_block() -> str | None:
    """读取一段粘贴内容（空行结束）；输入流结束时返回 None。"""
    lines = []
    while True:
        try:
            line = input('  > ' if not lines else '    ')
        except EOFError:
            return '\n'.join(lines) if lines else None
        if not line.strip():
            if lines:
                break
            continue
        lines.append(line)
    return '\n'.join(lines)


def _open(path: Path) -> None:
    try:
        if sys.platform == 'win32' and not os.environ.get('CK_NO_OPEN'):
            os.startfile(path)  # 用资源管理器打开文件夹
    except OSError:
        pass


def run_menu() -> int:
    cfg, used = load_config()
    library = Path(cfg.output_dir).expanduser()
    print('=' * 60)
    print('  CreatorKit 素材采集')
    print(f'  素材库：{library}')
    print('=' * 60)

    while True:
        print('\n① 粘贴链接（可以直接粘贴 App 里复制的分享文字，可多个），')
        print('   也可以把本地视频/音频文件拖进这个窗口；粘贴完按两次回车：')
        block = _read_block()
        if block is None:
            return 0
        urls, files = parse_input(block)
        if not urls and not files:
            print('  没有找到链接或文件，请重新粘贴。')
            continue
        for u in urls:
            print(f'  · 链接：{u}')
        for f in files:
            print(f'  · 本地文件：{f.name}')

        folders: list[Path] = []
        if urls:
            print('\n② 选择要什么（直接回车 = 1）：')
            for key, (_, label) in MODES.items():
                print(f'   {key}. {label}')
            try:
                choice = input('  > ').strip() or '1'
            except EOFError:
                return 0
            mode = MODES.get(choice, MODES['1'])[0]
            from .pipeline import Pipeline
            run_cfg, _ = load_config(overrides={'mode': mode})
            results = Pipeline(run_cfg).run(urls)
            ok = [r for r in results if r.ok]
            failed = [r for r in results if not r.ok]
            print(f'\n完成：成功 {len(ok)} 条，失败 {len(failed)} 条')
            for r in failed:
                print(f'  ✗ {r.url}\n    {r.error}')
            folders += [r.folder for r in ok if r.folder]

        if files:
            from .cli import main as cli_main
            cli_main(['transcribe', *map(str, files)])
            folders += [f.parent for f in files]

        if len(folders) == 1:
            print(f'\n已打开结果文件夹：{folders[0]}')
            _open(folders[0])
        elif folders:
            print(f'\n已打开素材库（索引.md 里有全部记录）：{library}')
            _open(library)

        print('\n' + '-' * 60)
        print('继续采集就粘贴下一个链接；不用了直接关闭窗口。')
