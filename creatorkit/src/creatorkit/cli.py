"""命令行入口：ck get / ck transcribe / ck doctor。"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import ASR_POLICIES, MODES, SCRIPTS, load_config


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument('-c', '--config', help='配置文件路径（默认依次查找 ./creatorkit.toml、~/.creatorkit.toml）')
    p.add_argument('--script', choices=SCRIPTS, help='中文字形：hans 简体 / hant 台湾繁体 / hk 香港繁体 / keep 不转换')
    p.add_argument('--model', help='语音识别模型，如 large-v3-turbo / large-v3 / medium / small')
    p.add_argument('--device', choices=('auto', 'cuda', 'cpu'), help='语音识别设备')
    p.add_argument('--lang', dest='language', help='强制识别语言，如 zh / en / ja（默认自动检测）')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='ck', description='CreatorKit：下载视频/音频，获取字幕或语音转写，生成文案笔记')
    parser.add_argument('--version', action='version', version=f'creatorkit {__version__}')
    sub = parser.add_subparsers(dest='command', required=True)

    g = sub.add_parser('get', help='采集链接（支持单个视频、合集、频道）')
    g.add_argument('urls', nargs='*', help='视频/合集/频道链接，可以写多个')
    g.add_argument('-f', '--file', help='从文本文件读取链接，每行一个，# 开头为注释')
    g.add_argument('-m', '--mode', choices=MODES, help='video 视频(默认) / audio 只要音频 / text 只要文字')
    g.add_argument('--asr', choices=ASR_POLICIES, help='auto 没字幕才识别(默认) / always 总是识别 / never 不识别')
    g.add_argument('-o', '--output', dest='output_dir', help='素材库目录')
    g.add_argument('--cookies-from-browser', help='从浏览器读取登录 cookie，如 firefox / chrome / edge')
    g.add_argument('--cookies', help='cookies.txt 路径（Netscape 格式）')
    g.add_argument('--proxy', help='代理，如 http://127.0.0.1:7897')
    g.add_argument('--max', dest='max_items', type=int, help='合集/频道最多处理多少条')
    g.add_argument('--keep-audio', action='store_true', default=None, help='text 模式下保留转写用的音频')
    g.add_argument('--force', action='store_true', help='已经采集过的也重新采集')
    g.add_argument('--show-browser', dest='browser_headless', action='store_false', default=None,
                   help='抖音：显示浏览器窗口（遇到验证码时在窗口里手动完成）')
    _add_common(g)

    t = sub.add_parser('transcribe', help='把本地音视频文件转成字幕和文字')
    t.add_argument('files', nargs='+', help='本地音视频文件')
    _add_common(t)

    d = sub.add_parser('doctor', help='检查运行环境（ffmpeg、显卡、配置）')
    d.add_argument('-c', '--config', help='配置文件路径')
    return parser


def _read_urls(args) -> list[str]:
    urls = list(args.urls)
    if args.file:
        for line in Path(args.file).read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    return urls


def cmd_get(args) -> int:
    overrides = {k: getattr(args, k, None) for k in (
        'mode', 'asr', 'output_dir', 'cookies_from_browser', 'cookies', 'proxy', 'max_items',
        'keep_audio', 'script', 'model', 'device', 'language', 'browser_headless')}
    cfg, used = load_config(args.config, overrides)
    urls = _read_urls(args)
    if not urls:
        print('请提供至少一个链接，或用 -f 指定链接文件', file=sys.stderr)
        return 2
    from .pipeline import Pipeline

    print(f'配置：{used or "内置默认值"} · 模式：{cfg.mode} · 素材库：{Path(cfg.output_dir).expanduser()}')
    results = Pipeline(cfg, force=args.force).run(urls)
    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    print(f'\n共 {len(results)} 条：成功 {len(ok)}（其中跳过 {sum(r.skipped for r in ok)}），失败 {len(failed)}')
    for r in failed:
        print(f'  ✗ {r.url}\n    {r.error}')
    return 1 if failed else 0


def cmd_transcribe(args) -> int:
    overrides = {k: getattr(args, k, None) for k in ('script', 'model', 'device', 'language')}
    cfg, _ = load_config(args.config, overrides)
    from .asr import Transcriber
    from .notes import render_note
    from .subtitles import to_plain_text, to_srt
    from .textconv import convert_segments

    tr = Transcriber(cfg.model, cfg.device, cfg.compute_type)
    code = 0
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            print(f'✗ 找不到文件：{path}', file=sys.stderr)
            code = 1
            continue
        print(f'\n▶ {path.name}')
        segments, lang = tr.transcribe(path, cfg.language, cfg.script)
        segments = convert_segments(segments, cfg.script)
        stem = path.with_suffix('')
        Path(f'{stem}.srt').write_text(to_srt(segments), encoding='utf-8-sig')
        Path(f'{stem}.txt').write_text(to_plain_text(segments), encoding='utf-8')
        info = {'title': path.stem, 'extractor_key': '本地文件'}
        Path(f'{stem}.md').write_text(
            render_note(info, segments, f'语音识别（{cfg.model}，{lang}）', {'文件': path.name}), encoding='utf-8')
        print(f'  ✓ {len(segments)} 句 → {stem}.srt / .txt / .md')
    return code


def cmd_doctor(args) -> int:
    ok = True
    print(f'creatorkit {__version__} · Python {sys.version.split()[0]}')
    try:
        import yt_dlp
        print(f'✓ yt-dlp {yt_dlp.version.__version__}（{Path(yt_dlp.__file__).parent}）')
    except ImportError:
        print('✗ 未安装 yt-dlp')
        ok = False
    for tool in ('ffmpeg', 'ffprobe'):
        path = shutil.which(tool)
        print(f'{"✓" if path else "✗"} {tool}：{path or "未找到（合并视频、提取音频需要它）"}')
        ok &= bool(path)
    try:
        import faster_whisper
        from .asr import _setup_cuda_dlls, cuda_available
        _setup_cuda_dlls()
        print(f'✓ faster-whisper {faster_whisper.__version__}')
        print(f'{"✓" if cuda_available() else "·"} CUDA：{"可用，语音识别将使用显卡" if cuda_available() else "不可用，将使用 CPU"}')
    except ImportError:
        print('· 未安装 faster-whisper（没有平台字幕时无法语音识别）')
    try:
        import playwright  # noqa: F401
        print('✓ 浏览器组件 playwright：已安装（抖音会用本机 Chrome/Edge 打开页面）')
    except ImportError:
        print('· 未安装 playwright（抖音无法采集）：pip install -e "creatorkit[browser]"')
    try:
        cfg, used = load_config(args.config)
        print(f'✓ 配置：{used or "内置默认值"}')
        for k, v in vars(cfg).items():
            print(f'    {k} = {v!r}')
        if cfg.cookies:
            from .cookies import summarize
            print('\n'.join(summarize(cfg.cookies)))
    except Exception as e:
        print(f'✗ 配置错误：{e}')
        ok = False
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    if not (sys.argv[1:] if argv is None else argv):  # 不带参数（比如双击启动）：进入交互菜单
        from .menu import run_menu
        try:
            return run_menu()
        except KeyboardInterrupt:
            return 130
        except (ValueError, FileNotFoundError) as e:
            print(f'错误：{e}', file=sys.stderr)
            return 2
    args = build_parser().parse_args(argv)
    try:
        return {'get': cmd_get, 'transcribe': cmd_transcribe, 'doctor': cmd_doctor}[args.command](args)
    except (ValueError, FileNotFoundError) as e:
        print(f'错误：{e}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('\n已取消', file=sys.stderr)
        return 130
