"""cookie 文件处理：支持单个 cookies.txt，或一个放着多个平台 cookie 文件的文件夹。"""

from __future__ import annotations

import atexit
import os
import tempfile
from collections import Counter
from pathlib import Path

HEADER = '# Netscape HTTP Cookie File\n'


def _cookie_lines(path: Path) -> list[str]:
    lines = []
    for line in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        # “#HttpOnly_” 开头的是 HttpOnly cookie，不是注释
        if not line.strip() or (line.startswith('#') and not line.startswith('#HttpOnly_')):
            continue
        if line.count('\t') >= 6:
            lines.append(line)
    return lines


def cookie_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() == '.txt')
    return [path] if path.is_file() else []


def merge_cookie_files(files: list[Path], dest: Path) -> int:
    lines = []
    for f in files:
        lines.extend(_cookie_lines(f))
    dest.write_text(HEADER + '\n'.join(lines) + '\n', encoding='utf-8')
    return len(lines)


def resolve_cookiefile(cookies: str) -> str:
    """返回交给 yt-dlp 的 cookie 文件路径；文件夹会被合并成一个临时文件。"""
    path = Path(cookies).expanduser()
    if not path.exists():
        raise FileNotFoundError(f'找不到 cookie 文件或文件夹：{path}')
    if path.is_file():
        return str(path)
    fd, tmp = tempfile.mkstemp(prefix='ck-cookies-', suffix='.txt')
    os.close(fd)
    atexit.register(lambda: Path(tmp).unlink(missing_ok=True))
    merge_cookie_files(cookie_files(path), Path(tmp))
    return tmp


def summarize(cookies: str) -> list[str]:
    """给 ck doctor 用：每个 cookie 文件里有哪些网站。"""
    path = Path(cookies).expanduser()
    files = cookie_files(path)
    if not files:
        return [f'✗ cookie：{path} 下没有找到 .txt 文件']
    out = [f'✓ cookie：{path}']
    for f in files:
        domains = Counter(l.split('\t')[0].removeprefix('#HttpOnly_').lstrip('.') for l in _cookie_lines(f))
        top = '、'.join(d for d, _ in domains.most_common(4)) or '（空文件）'
        out.append(f'    {f.name}：{sum(domains.values())} 条，{top}')
    return out
