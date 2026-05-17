import asyncio
import os
from pathlib import Path
from typing import List, Optional

from conf import BASE_DIR, DEBUG_DRY_RUN_HOLD_SECONDS, USE_SYSTEM_BROWSER

SOCIAL_MEDIA_DOUYIN = "douyin"
SOCIAL_MEDIA_TENCENT = "tencent"
SOCIAL_MEDIA_TIKTOK = "tiktok"
SOCIAL_MEDIA_BILIBILI = "bilibili"
SOCIAL_MEDIA_KUAISHOU = "kuaishou"


def get_supported_social_media() -> List[str]:
    return [
        SOCIAL_MEDIA_DOUYIN,
        SOCIAL_MEDIA_TENCENT,
        SOCIAL_MEDIA_TIKTOK,
        SOCIAL_MEDIA_BILIBILI,
        SOCIAL_MEDIA_KUAISHOU,
    ]


def get_cli_action() -> List[str]:
    return ["upload", "login", "watch"]


async def set_init_script(context):
    stealth_js_path = Path(BASE_DIR / "utils/stealth.min.js")
    await context.add_init_script(path=stealth_js_path)
    return context


PUBLISH_WINDOW_WIDTH = 1600
PUBLISH_WINDOW_HEIGHT = 1000
PUBLISH_WINDOW_X = 48
PUBLISH_WINDOW_Y = 36
PUBLISH_WINDOW_MARGIN = 24
HIDDEN_WINDOW_X = -32000
HIDDEN_WINDOW_Y = -32000
_REVEALED_WINDOW_IDS = set()


async def launch_chromium_with_codecs(
    playwright,
    headless: bool = False,
    executable_path: Optional[str] = None,
    hide_until_ready: bool = False,
):
    """
    Prefer launching with system Chrome/Edge for proprietary codecs (H.264) and stable media playback.
    Falls back to bundled Chromium if neither is available.
    """
    launch_args = [
        "--window-size=1600,1000",
        "--autoplay-policy=no-user-gesture-required",
        "--enable-gpu",
        "--ignore-gpu-blocklist",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--mute-audio",
        "--lang=zh-CN",
    ]
    if not headless:
        if hide_until_ready:
            launch_args.append(f"--window-position={HIDDEN_WINDOW_X},{HIDDEN_WINDOW_Y}")
        else:
            launch_args.append(f"--window-position={PUBLISH_WINDOW_X},{PUBLISH_WINDOW_Y}")

    # If user prefers bundled/runtime-only mode, skip system channels and try third_party or bundled Chromium
    if not USE_SYSTEM_BROWSER:
        # Point Playwright to in-repo browsers if present
        third_party_pw = Path(BASE_DIR / "third_party" / "playwright" / "ms-playwright")
        if third_party_pw.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(third_party_pw)
            print(f"[launch] Using bundled browsers at {third_party_pw}")

        # Probe portable Chrome/Edge under third_party (with proprietary codecs)
        portable_candidates = [
            Path(BASE_DIR / "third_party" / "chrome-win" / "chrome.exe"),
            Path(BASE_DIR / "third_party" / "chrome" / "chrome.exe"),
            Path(BASE_DIR / "third_party" / "edge" / "msedge.exe"),
            Path(BASE_DIR / "third_party" / "msedge" / "msedge.exe"),
        ]
        for candidate in portable_candidates:
            try:
                if candidate.exists():
                    print(f"[launch] Using portable browser: {candidate}")
                    browser = await playwright.chromium.launch(
                        headless=headless,
                        executable_path=str(candidate),
                        args=launch_args,
                    )
                    try:
                        # Probe by opening and closing a dummy browser context
                        context = await browser.new_context()
                        await context.close()
                        print(f"[launch] Portable browser ready: {candidate}")
                    except Exception as e:
                        print(f"[launch] Portable browser probe failed: {e}")
                    return browser
            except Exception as e:
                print(f"[launch] portable exec failed {candidate}: {e}")

        print("[launch] Forcing bundled Chromium (no system browser). H.264 may be unavailable.")
        return await playwright.chromium.launch(headless=headless, args=launch_args)

    # 1) Explicit executable path wins
    try:
        if executable_path and executable_path.strip():
            return await playwright.chromium.launch(
                headless=headless,
                executable_path=executable_path,
                args=launch_args,
            )
    except Exception as e:
        print(f"[launch] executable_path failed: {e}")

    # 2) Try installed Chrome
    try:
        return await playwright.chromium.launch(
            headless=headless,
            channel="chrome",
            args=launch_args,
        )
    except Exception as e:
        print(f"[launch] channel=chrome failed: {e}")

    # 3) Try installed Edge (also supports proprietary codecs on Windows)
    try:
        return await playwright.chromium.launch(
            headless=headless,
            channel="msedge",
            args=launch_args,
        )
    except Exception as e:
        print(f"[launch] channel=msedge failed: {e}")

    # 4) Fallback to bundled Chromium (may lack H.264)
    print("[launch] Falling back to bundled Chromium; H.264 may be unavailable.")
    return await playwright.chromium.launch(headless=headless, args=launch_args)


async def launch_publish_browser(playwright, executable_path: Optional[str] = None):
    """Launch a headed browser off-screen until the target publish page is ready."""
    return await launch_chromium_with_codecs(
        playwright,
        headless=False,
        executable_path=executable_path,
        hide_until_ready=True,
    )


async def new_publish_context(browser, storage_state: Optional[str] = None, **kwargs):
    context_options = {
        "no_viewport": True,
        "permissions": [],
        "geolocation": None,
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }
    if storage_state:
        context_options["storage_state"] = str(storage_state) if isinstance(storage_state, (str, Path)) else storage_state
    context_options.update(kwargs)
    return await browser.new_context(**context_options)


async def reveal_page_window(page):
    """Move the off-screen browser window into view once, then only switch tabs."""
    try:
        session = await page.context.new_cdp_session(page)
        window_info = await session.send("Browser.getWindowForTarget")
        window_id = window_info["windowId"]
        if window_id in _REVEALED_WINDOW_IDS:
            await page.bring_to_front()
            return

        await session.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "windowState": "normal",
                    "left": PUBLISH_WINDOW_X,
                    "top": PUBLISH_WINDOW_Y,
                    "width": PUBLISH_WINDOW_WIDTH,
                    "height": PUBLISH_WINDOW_HEIGHT,
                },
            },
        )
        _REVEALED_WINDOW_IDS.add(window_id)
        await page.bring_to_front()
        return
    except Exception as e:
        print(f"[launch] reveal via cdp failed: {e}")

    try:
        await page.evaluate(
            """([margin]) => {
                const left = Math.max(0, window.screen.availLeft || 0) + margin;
                const top = Math.max(0, window.screen.availTop || 0) + margin;
                const width = Math.max(1024, window.screen.availWidth - margin * 2);
                const height = Math.max(720, window.screen.availHeight - margin * 2);
                window.moveTo(left, top);
                window.resizeTo(width, height);
            }""",
            [PUBLISH_WINDOW_MARGIN],
        )
    except Exception as e:
        print(f"[launch] reveal via window api failed: {e}")


async def goto_and_reveal(page, url: str, wait_until: str = "domcontentloaded", timeout: Optional[int] = None):
    goto_options = {"wait_until": wait_until}
    if timeout is not None:
        goto_options["timeout"] = timeout
    try:
        return await page.goto(url, **goto_options)
    finally:
        await reveal_page_window(page)


async def prevent_new_tabs(page, logger=None, label: str = "发布"):
    """Prevent platform submit clicks from opening transient blank/helper tabs."""
    try:
        await page.evaluate(
            """(label) => {
                if (window.__sauPreventNewTabsInstalled) return;
                window.__sauPreventNewTabsInstalled = true;
                window.__sauOriginalWindowOpen = window.open;
                window.open = (...args) => {
                    console.debug(`[SAU] blocked window.open during ${label}`, args);
                    return null;
                };
                const normalizeTargets = () => {
                    document.querySelectorAll('a[target="_blank"], form[target="_blank"]').forEach(node => {
                        node.setAttribute('target', '_self');
                    });
                };
                normalizeTargets();
                const observer = new MutationObserver(normalizeTargets);
                observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['target'] });
            }""",
            label,
        )
    except Exception as e:
        if logger:
            logger.warning(f"{label} 新标签拦截脚本注入失败: {e}")
        else:
            print(f"{label} new-tab blocker inject failed: {e}")


async def keep_browser_open_for_dry_run(
    page,
    context,
    browser,
    account_file=None,
    logger=None,
    platform_name: str = "平台",
    block_until_close: bool = True,
    auto_close_seconds: Optional[int] = None,
):
    """Keep the headed publish window open after dry-run so the operator can inspect the filled form."""
    if account_file:
        await context.storage_state(path=str(account_file))

    if auto_close_seconds is None:
        auto_close_seconds = DEBUG_DRY_RUN_HOLD_SECONDS

    if block_until_close:
        message = f"{platform_name} dry_run 已完成：已跳过最终发布，浏览器窗口会保持打开；检查完成后请手动关闭窗口。"
    else:
        message = f"{platform_name} dry_run 已完成：已跳过最终发布，窗口保留 {auto_close_seconds} 秒后自动关闭以继续批量预发布。"
    if logger:
        logger.info(message)
    else:
        print(message)

    try:
        if block_until_close:
            while browser.is_connected():
                pages = []
                try:
                    for item in browser.contexts:
                        pages.extend(item.pages)
                except Exception:
                    pages = [page]
                if pages and all(p.is_closed() for p in pages):
                    break
                await asyncio.sleep(1)
        elif auto_close_seconds and auto_close_seconds > 0:
            await asyncio.sleep(auto_close_seconds)
    finally:
        try:
            await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass
