"""抖音：用真实浏览器打开视频页，拿到页面自己请求到的作品数据。

抖音网页的作品接口需要浏览器端计算的签名，yt-dlp 目前没有实现。这里不伪造签名，
而是让本机安装的 Chrome（或 Playwright 自带的 Chromium）带着用户自己的 cookie
正常打开视频页，页面加载时会自己请求作品数据，我们只是读取这次响应。
如果抖音弹出验证码，用 --show-browser 打开可见窗口手动完成即可。
"""

from __future__ import annotations

import re
from pathlib import Path

DOUYIN_ID_RE = re.compile(r'(?:/video/|/note/|/share/video/|modal_id=)(\d{15,21})')
DETAIL_API = '/aweme/v1/web/aweme/detail/'


class BrowserUnavailable(RuntimeError):
    pass


class BrowserFetchError(RuntimeError):
    pass


def is_douyin_url(url: str) -> bool:
    return bool(re.search(r'(?:^|[/.])(?:douyin\.com|iesdouyin\.com)(?:[/:?#]|$)', url))


def extract_video_id(url: str) -> str | None:
    m = DOUYIN_ID_RE.search(url)
    return m.group(1) if m else None


def load_cookies_for_playwright(cookiefile: str | None, domain: str = 'douyin.com') -> list[dict]:
    if not cookiefile:
        return []
    cookies = []
    for line in Path(cookiefile).read_text(encoding='utf-8-sig', errors='replace').splitlines():
        http_only = line.startswith('#HttpOnly_')
        if http_only:
            line = line[len('#HttpOnly_'):]
        elif line.startswith('#') or not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 7:
            continue
        host, _, path, secure, expires, name, value = parts[:7]
        if not host.lstrip('.').endswith(domain):
            continue
        cookie = {'name': name, 'value': value, 'domain': host, 'path': path or '/',
                  'secure': secure.upper() == 'TRUE', 'httpOnly': http_only}
        if expires.isdigit() and int(expires) > 0:
            cookie['expires'] = int(expires)
        cookies.append(cookie)
    return cookies


def fetch_aweme_detail(video_id: str, cookiefile: str | None, *, headless: bool = True,
                       timeout: float = 45, log=print) -> dict:
    try:
        from playwright.sync_api import Error as PWError
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise BrowserUnavailable('未安装浏览器组件，请运行：pip install -e "creatorkit[browser]"') from e

    with sync_playwright() as p:
        browser = None
        for kwargs in ({'channel': 'chrome'}, {'channel': 'msedge'}, {}):
            try:
                browser = p.chromium.launch(headless=headless, **kwargs)
                break
            except PWError:
                continue
        if browser is None:
            raise BrowserUnavailable('找不到可用的浏览器：请安装 Chrome，或运行 playwright install chromium')
        try:
            ctx = browser.new_context(locale='zh-CN', viewport={'width': 1366, 'height': 820})
            ctx.add_cookies(load_cookies_for_playwright(cookiefile))
            page = ctx.new_page()
            log(f'  用浏览器打开抖音页面（{"后台" if headless else "可见窗口"}）……')

            def is_detail(resp):
                return DETAIL_API in resp.url and f'aweme_id={video_id}' in resp.url

            try:
                with page.expect_response(is_detail, timeout=timeout * 1000) as resp_info:
                    page.goto(f'https://www.douyin.com/video/{video_id}', wait_until='domcontentloaded',
                              timeout=timeout * 1000)
                resp = resp_info.value
                data = resp.json() if resp.ok else {}
            except PWTimeout:
                data = {}
            except (PWError, ValueError):
                data = {}
            detail = (data or {}).get('aweme_detail')
            if not detail:
                captcha = page.locator('[id*="captcha"], [class*="captcha"], iframe[src*="verify"]').count() > 0
                if captcha:
                    raise BrowserFetchError('抖音弹出了验证码。请加 --show-browser 重新运行，在弹出的窗口里手动完成验证')
                if data.get('filter_detail') or data.get('status_code'):
                    raise BrowserFetchError(f'抖音返回：{data.get("filter_detail") or data.get("status_msg") or data}')
                raise BrowserFetchError('没有拿到作品数据（作品可能已删除/私密，或 cookie 已过期，请重新导出 douyin.txt）')
            return detail
        finally:
            browser.close()
