import asyncio
import sqlite3

from playwright.async_api import async_playwright

from myUtils.auth import check_cookie
from myUtils.avatar import capture_identity_from_page
from utils.base_social_media import launch_chromium_with_codecs, set_init_script
import uuid
from pathlib import Path
from conf import BASE_DIR


async def launch_login_browser(playwright, **options):
    options.pop("executable_path", None)
    headless = options.pop("headless", False)
    args = options.pop("args", None)
    browser = await launch_chromium_with_codecs(playwright, headless=headless, executable_path=None)
    return browser


async def new_login_context(browser):
    return await browser.new_context(
        no_viewport=True,
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )


async def wait_for_login_or_cancel(url_changed_event, cancel_event=None, timeout=200):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return "cancelled"

        remaining = deadline - loop.time()
        if remaining <= 0:
            return "timeout"

        try:
            await asyncio.wait_for(url_changed_event.wait(), timeout=min(0.5, remaining))
            return "logged_in"
        except asyncio.TimeoutError:
            continue


async def close_login_resources(page=None, context=None, browser=None):
    for resource in (page, context, browser):
        if resource is None:
            continue
        try:
            await resource.close()
        except Exception:
            pass


async def finish_cancelled_login(status_queue, page=None, context=None, browser=None):
    print("登录流程已取消")
    status_queue.put("CANCELLED")
    await close_login_resources(page, context, browser)


async def capture_login_identity(page, platform_type, avatar_key):
    try:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(1200)
        return await capture_identity_from_page(page, f"account_{avatar_key}.png", platform_type)
    except Exception as e:
        print(f"[login] capture identity failed platform={platform_type}: {e}")
        return None, None


def save_login_account(platform_type, cookie_file, profile_name, update_mode=False, record_id=None, avatar_path=None, display_name=None):
    user_name = display_name or profile_name
    saved_account_id = int(record_id) if update_mode and record_id else None
    db_path = Path(BASE_DIR / "db" / "database.db")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if update_mode and record_id:
            cursor.execute(
                """
                UPDATE user_info
                SET type = ?,
                    filePath = ?,
                    userName = ?,
                    status = ?,
                    profileName = ?,
                    avatarPath = COALESCE(?, avatarPath),
                    avatarUpdatedAt = CASE WHEN ? IS NOT NULL THEN CURRENT_TIMESTAMP ELSE avatarUpdatedAt END
                WHERE id = ?
                """,
                (platform_type, cookie_file, user_name, 1, profile_name, avatar_path, avatar_path, int(record_id)),
            )
        elif avatar_path:
            cursor.execute(
                """
                INSERT INTO user_info (type, filePath, userName, status, profileName, avatarPath, avatarUpdatedAt)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (platform_type, cookie_file, user_name, 1, profile_name, avatar_path),
            )
            saved_account_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                INSERT INTO user_info (type, filePath, userName, status, profileName)
                VALUES (?, ?, ?, ?, ?)
                """,
                (platform_type, cookie_file, user_name, 1, profile_name),
            )
            saved_account_id = cursor.lastrowid
        conn.commit()
        print("[OK] 用户状态已记录")
    return saved_account_id

# 抖音登录
async def douyin_cookie_gen(id,status_queue, update_mode=False, record_id=None, cancel_event=None):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()
    async with async_playwright() as playwright:
        options = {
            'headless': False
        }
        # Make sure to run headed.
        browser = await launch_login_browser(playwright, **options)
        # Setup context however you like.
        context = await new_login_context(browser)
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        original_url = page.url
        img_locator = page.get_by_role("img", name="二维码")
        # 获取 src 属性值
        src = await img_locator.get_attribute("src")
        print("[OK] 图片地址:", src)
        status_queue.put(src)
        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)
        wait_result = await wait_for_login_or_cancel(url_changed_event, cancel_event)
        if wait_result == "logged_in":
            print("监听页面跳转成功")
        elif wait_result == "cancelled":
            await finish_cancelled_login(status_queue, page, context, browser)
            return None
        else:
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            status_queue.put("500")
            return None
        uuid_v1 = uuid.uuid1()
        cookie_file = f"{uuid_v1}.json"
        print(f"UUID v1: {uuid_v1}")
        await context.storage_state(path=Path(BASE_DIR / "cookiesFile" / cookie_file))
        result = await check_cookie(3, cookie_file)
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        avatar_path, display_name = await capture_login_identity(page, 3, uuid_v1)
        await page.close()
        await context.close()
        await browser.close()
        account_id = save_login_account(3, cookie_file, id, update_mode, record_id, avatar_path, display_name)
        if account_id:
            status_queue.put(f"ACCOUNT_ID:{account_id}")
        status_queue.put("200")


# 视频号登录
async def get_tencent_cookie(id,status_queue, update_mode=False, record_id=None, cancel_event=None):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': False,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await launch_login_browser(playwright, **options)
        # Setup context however you like.
        context = await new_login_context(browser)
        # Pause the page, and start recording manually.
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        original_url = page.url

        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        # 等待 iframe 出现（最多等 60 秒）
        iframe_locator = page.frame_locator("iframe").first

        # 获取 iframe 中的第一个 img 元素
        img_locator = iframe_locator.get_by_role("img").first

        # 获取 src 属性值
        src = await img_locator.get_attribute("src")
        print("[OK] 图片地址:", src)
        status_queue.put(src)

        wait_result = await wait_for_login_or_cancel(url_changed_event, cancel_event)
        if wait_result == "logged_in":
            print("监听页面跳转成功")
        elif wait_result == "cancelled":
            await finish_cancelled_login(status_queue, page, context, browser)
            return None
        else:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        cookie_file = f"{uuid_v1}.json"
        print(f"UUID v1: {uuid_v1}")
        await context.storage_state(path=Path(BASE_DIR / "cookiesFile" / cookie_file))
        result = await check_cookie(2, cookie_file)
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        avatar_path, display_name = await capture_login_identity(page, 2, uuid_v1)
        await page.close()
        await context.close()
        await browser.close()
        account_id = save_login_account(2, cookie_file, id, update_mode, record_id, avatar_path, display_name)
        if account_id:
            status_queue.put(f"ACCOUNT_ID:{account_id}")
        status_queue.put("200")

# 快手登录
async def get_ks_cookie(id,status_queue, update_mode=False, record_id=None, cancel_event=None):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()
    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': False,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await launch_login_browser(playwright, **options)
        # Setup context however you like.
        context = await new_login_context(browser)
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://cp.kuaishou.com")

        # 定位并点击“立即登录”按钮（类型为 link）
        await page.get_by_role("link", name="立即登录").click()
        await page.get_by_text("扫码登录").click()
        img_locator = page.get_by_role("img", name="qrcode")
        # 获取 src 属性值
        src = await img_locator.get_attribute("src")
        original_url = page.url
        print("[OK] 图片地址:", src)
        status_queue.put(src)
        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        wait_result = await wait_for_login_or_cancel(url_changed_event, cancel_event)
        if wait_result == "logged_in":
            print("监听页面跳转成功")
        elif wait_result == "cancelled":
            await finish_cancelled_login(status_queue, page, context, browser)
            return None
        else:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        cookie_file = f"{uuid_v1}.json"
        print(f"UUID v1: {uuid_v1}")
        await context.storage_state(path=Path(BASE_DIR / "cookiesFile" / cookie_file))
        result = await check_cookie(4, cookie_file)
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        avatar_path, display_name = await capture_login_identity(page, 4, uuid_v1)
        await page.close()
        await context.close()
        await browser.close()
        account_id = save_login_account(4, cookie_file, id, update_mode, record_id, avatar_path, display_name)
        if account_id:
            status_queue.put(f"ACCOUNT_ID:{account_id}")
        status_queue.put("200")

# 小红书登录
async def xiaohongshu_cookie_gen(id,status_queue, update_mode=False, record_id=None, cancel_event=None):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': False,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await launch_login_browser(playwright, **options)
        # Setup context however you like.
        context = await new_login_context(browser)
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.xiaohongshu.com/")
        await page.locator('img.css-wemwzq').click()

        img_locator = page.get_by_role("img").nth(2)
        # 获取 src 属性值
        src = await img_locator.get_attribute("src")
        original_url = page.url
        print("[OK] 图片地址:", src)
        status_queue.put(src)
        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        wait_result = await wait_for_login_or_cancel(url_changed_event, cancel_event)
        if wait_result == "logged_in":
            print("监听页面跳转成功")
        elif wait_result == "cancelled":
            await finish_cancelled_login(status_queue, page, context, browser)
            return None
        else:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        cookie_file = f"{uuid_v1}.json"
        print(f"UUID v1: {uuid_v1}")
        await context.storage_state(path=Path(BASE_DIR / "cookiesFile" / cookie_file))
        result = await check_cookie(1, cookie_file)
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        avatar_path, display_name = await capture_login_identity(page, 1, uuid_v1)
        await page.close()
        await context.close()
        await browser.close()
        account_id = save_login_account(1, cookie_file, id, update_mode, record_id, avatar_path, display_name)
        if account_id:
            status_queue.put(f"ACCOUNT_ID:{account_id}")
        status_queue.put("200")

# a = asyncio.run(xiaohongshu_cookie_gen(4,None))
# print(a)

# B站登录
async def bilibili_cookie_gen(id, status_queue, update_mode=False, record_id=None, cancel_event=None):
    from utils.log import bilibili_logger
    
    bilibili_logger.info(f"[bilibili_login] 开始B站登录流程，用户ID: {id}")
    
    url_changed_event = asyncio.Event()

    async def on_url_change():
        bilibili_logger.info(f"[bilibili_login] 页面URL变化: {page.url}")
        if page.url != original_url:
            bilibili_logger.info(f"[bilibili_login] 检测到URL变化，原始URL: {original_url}, 新URL: {page.url}")
            url_changed_event.set()

    async with async_playwright() as playwright:
        options = {
            'headless': False
        }
        bilibili_logger.info("[bilibili_login] 启动浏览器...")
        browser = await launch_login_browser(playwright, **options)
        context = await new_login_context(browser)
        context = await set_init_script(context)
        page = await context.new_page()
        
        bilibili_logger.info("[bilibili_login] 导航到B站上传页面...")
        await page.goto("https://member.bilibili.com/platform/upload/video/frame")
        original_url = page.url
        bilibili_logger.info(f"[bilibili_login] 初始页面URL: {original_url}")

        # 尝试抓取二维码
        bilibili_logger.info("[bilibili_login] 尝试查找二维码...")
        try:
            img_locator = page.locator('img[src*="qrcode"]').first
            if await img_locator.count() == 0:
                bilibili_logger.info("[bilibili_login] 未找到qrcode图片，尝试查找其他img元素")
                img_locator = page.locator('img').first
                
            if await img_locator.count() > 0:
                src = await img_locator.get_attribute("src")
                if src:
                    bilibili_logger.info(f"[bilibili_login] 找到二维码图片: {src[:50]}...")
                    status_queue.put(src)
                else:
                    bilibili_logger.warning("[bilibili_login] 找到img元素但无src属性")
            else:
                bilibili_logger.warning("[bilibili_login] 未找到任何img元素")
        except Exception as e:
            bilibili_logger.error(f"[bilibili_login] 查找二维码时出错: {e}")

        bilibili_logger.info("[bilibili_login] 等待用户扫码登录...")
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)
        wait_result = await wait_for_login_or_cancel(url_changed_event, cancel_event)
        if wait_result == "logged_in":
            bilibili_logger.info("[bilibili_login] 检测到页面跳转，登录可能成功")
        elif wait_result == "cancelled":
            bilibili_logger.info("[bilibili_login] 登录流程已取消")
            await finish_cancelled_login(status_queue, page, context, browser)
            return None
        else:
            bilibili_logger.error("[bilibili_login] 登录超时（200秒）")
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None

        bilibili_logger.info("[bilibili_login] 保存登录状态...")
        uuid_v1 = uuid.uuid1()
        cookie_file = f"{uuid_v1}.json"
        await context.storage_state(path=Path(BASE_DIR / "cookiesFile" / cookie_file))
        bilibili_logger.info(f"[bilibili_login] 登录状态已保存到: {cookie_file}")
        
        bilibili_logger.info("[bilibili_login] 验证cookie有效性...")
        result = await check_cookie(5, cookie_file)
        bilibili_logger.info(f"[bilibili_login] cookie验证结果: {result}")
        
        if not result:
            bilibili_logger.error("[bilibili_login] cookie验证失败，登录失败")
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None

        avatar_path, display_name = await capture_login_identity(page, 5, uuid_v1)
        bilibili_logger.info("[bilibili_login] 关闭浏览器...")
        await page.close()
        await context.close()
        await browser.close()

        bilibili_logger.info("[bilibili_login] 保存用户信息到数据库...")
        account_id = save_login_account(5, cookie_file, id, update_mode, record_id, avatar_path, display_name)
        if account_id:
            status_queue.put(f"ACCOUNT_ID:{account_id}")
        bilibili_logger.info("[OK] [bilibili_login] 用户状态已记录到数据库")
        
        bilibili_logger.info("[bilibili_login] B站登录流程完成，返回成功状态")
        status_queue.put("200")
