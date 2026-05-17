# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Error as PlaywrightError, Playwright, TimeoutError as PlaywrightTimeoutError, async_playwright
import os
import asyncio

from conf import LOCAL_CHROME_PATH
from utils.base_social_media import (
    set_init_script,
    launch_chromium_with_codecs,
    launch_publish_browser,
    new_publish_context,
    goto_and_reveal,
    keep_browser_open_for_dry_run,
)
from utils.files_times import get_absolute_path
from utils.log import tencent_logger
from utils.publish_limits import normalize_publish_tags


def format_str_for_short_title(origin_title: str) -> str:
    # 定义允许的特殊字符
    allowed_special_chars = "《》“”:+?%°"

    # 移除不允许的特殊字符
    filtered_chars = [char if char.isalnum() or char in allowed_special_chars else ' ' if char == ',' else '' for
                      char in origin_title]
    formatted_string = ''.join(filtered_chars)

    # 调整字符串长度
    if len(formatted_string) > 16:
        # 截断字符串
        formatted_string = formatted_string[:16]
    elif len(formatted_string) < 6:
        # 使用空格来填充字符串
        formatted_string += ' ' * (6 - len(formatted_string))

    return formatted_string


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        try:
            await page.wait_for_selector('div.title-name:has-text("微信小店")', timeout=5000)  # 等待5秒
            tencent_logger.error("[+] 等待5秒 cookie 失效")
            return False
        except:
            tencent_logger.success("[+] cookie 有效")
            return True


async def get_tencent_cookie(account_file):
    async with async_playwright() as playwright:
        browser = await launch_chromium_with_codecs(playwright, headless=False, executable_path=None)
        # Setup context however you like.
        context = await browser.new_context(
            permissions=[],  # 禁用所有权限请求
            geolocation=None,  # 禁用地理位置
            locale='zh-CN',  # 设置语言为中文
            timezone_id='Asia/Shanghai'  # 设置时区
        )  # Pass any options
        # Pause the page, and start recording manually.
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


async def weixin_setup(account_file, handle=False):
    account_file = get_absolute_path(account_file, "tencent_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        tencent_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await get_tencent_cookie(account_file)
    return True


class TencentVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, category=None, thumbnail_path=None, thumbnail_paths=None, dry_run=False, dry_run_hold_browser=True):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = normalize_publish_tags(tags)
        self.publish_date = publish_date
        self.account_file = account_file
        self.category = category
        self.thumbnail_path = thumbnail_path
        self.thumbnail_paths = dict(thumbnail_paths or {})
        if thumbnail_path and "4:3" not in self.thumbnail_paths:
            self.thumbnail_paths["4:3"] = thumbnail_path
        self.dry_run = dry_run
        self.dry_run_hold_browser = dry_run_hold_browser
        self.local_executable_path = LOCAL_CHROME_PATH

    async def set_schedule_time_tencent(self, page, publish_date):
        label_element = page.locator("label").filter(has_text="定时").nth(1)
        await label_element.click()
        await page.wait_for_timeout(500)

        await page.click('input[placeholder="请选择发表时间"]')

        str_month = str(publish_date.month) if publish_date.month > 9 else "0" + str(publish_date.month)
        current_month = str_month + "月"
        # 获取当前的月份
        page_month = await page.inner_text('span.weui-desktop-picker__panel__label:has-text("月")')

        # 检查当前月份是否与目标月份相同
        if page_month != current_month:
            await page.click('button.weui-desktop-btn__icon__right')

        # 获取页面元素
        elements = await page.query_selector_all('table.weui-desktop-picker__table a')

        # 遍历元素并点击匹配的元素
        for element in elements:
            if 'weui-desktop-picker__disabled' in await element.evaluate('el => el.className'):
                continue
            text = await element.inner_text()
            if text.strip() == str(publish_date.day):
                await element.click()
                break

        # 输入完整时间，不能只写小时，否则随机分钟会被平台重置到整点。
        time_input = page.locator('input[placeholder="请选择时间"]').first
        await time_input.click()
        await page.keyboard.press("Control+KeyA")
        await time_input.fill(publish_date.strftime("%H:%M"))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)

        # 选择标题栏（令定时时间生效）
        await page.locator("div.input-editor").click()
        await page.keyboard.press("Escape")
        tencent_logger.info(f"视频号定时发布时间已设置：{publish_date.strftime('%Y-%m-%d %H:%M')}")

    async def handle_upload_error(self, page):
        tencent_logger.info("视频出错了，重新上传中")
        await page.locator('div.media-status-content div.tag-inner:has-text("删除")').click()
        await page.get_by_role('button', name="删除", exact=True).click()
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)

    async def upload(self, playwright: Playwright) -> None:
        page = getattr(self, "external_page", None)
        context = getattr(self, "external_context", None)
        browser = getattr(self, "external_browser", None)
        managed_browser = page is None
        if managed_browser:
            # 使用系统浏览器优先，避免 H.264 错误
            browser = await launch_publish_browser(playwright, executable_path=self.local_executable_path)
        try:
            if managed_browser:
                # 创建一个浏览器上下文，使用指定的 cookie 文件
                context = await new_publish_context(
                    browser,
                    storage_state=f"{self.account_file}",
                )
                context = await set_init_script(context)

                # 创建一个新的页面
                page = await context.new_page()
            # 访问指定的 URL
            await goto_and_reveal(page, "https://channels.weixin.qq.com/platform/post/create")
            tencent_logger.info(f'[+]正在上传-------{self.title}.mp4')
            # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
            await page.wait_for_url("https://channels.weixin.qq.com/platform/post/create")
            # await page.wait_for_selector('input[type="file"]', timeout=10000)
            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(self.file_path)
            tencent_logger.info("视频号视频上传中...")

            # 填充标题和话题
            await self.add_title_tags(page)
            # 添加短标题
            await self.add_short_title(page)

            await self.set_thumbnail_if_needed(page)

            # 添加商品
            # await self.add_product(page)
            # 合集功能
            await self.add_collection(page)
            # 原创选择
            await self.add_original(page)
            if self.publish_date != 0:
                await self.set_schedule_time_tencent(page, self.publish_date)
            # 检测上传状态和表单就绪状态
            await self.detect_upload_status(page)

            if self.dry_run:
                if managed_browser:
                    await keep_browser_open_for_dry_run(
                        page,
                        context,
                        browser,
                        account_file=self.account_file,
                        logger=tencent_logger,
                        platform_name="视频号",
                        block_until_close=self.dry_run_hold_browser,
                    )
                return

            await self.click_publish(page)

            await context.storage_state(path=f"{self.account_file}")  # 保存cookie
            tencent_logger.success('  [-]cookie更新完毕！')
            await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        finally:
            # 关闭浏览器上下文和浏览器实例
            try:
                if managed_browser and 'context' in locals():
                    try:
                        await context.close()
                    except Exception:
                        pass
            finally:
                try:
                    if managed_browser:
                        await browser.close()
                except Exception:
                    pass

    async def set_thumbnail_if_needed(self, page):
        cover_targets = [
            (ratio, self.thumbnail_paths.get(ratio))
            for ratio in ("3:4", "4:3")
            if self.thumbnail_paths.get(ratio)
        ]
        if not cover_targets:
            tencent_logger.info("未设置视频号封面，跳过封面编辑")
            return

        tencent_logger.info("等待封面生成完成...")
        try:
            await page.wait_for_selector('.gen-text:has-text("生成中")', state='hidden', timeout=30000)
            tencent_logger.info("封面生成完成")
        except PlaywrightTimeoutError:
            tencent_logger.info("未检测到生成中文本，继续等待")

        await self.wait_for_cover_options_ready(page, [ratio for ratio, _ in cover_targets])

        for ratio, thumbnail_path in cover_targets:
            await self.set_one_thumbnail(page, ratio, thumbnail_path)

    async def wait_for_cover_options_ready(self, page, ratios, timeout=12000):
        started_at = asyncio.get_running_loop().time()
        pending = set(ratios)
        while pending and asyncio.get_running_loop().time() - started_at < timeout / 1000:
            for ratio in list(pending):
                if await self.find_cover_edit_button(page, ratio):
                    pending.remove(ratio)
            if pending:
                await asyncio.sleep(0.2)
        if pending:
            tencent_logger.warning(f"视频号封面入口等待超时，继续尝试处理：{sorted(pending)}")

    async def set_one_thumbnail(self, page, ratio, thumbnail_path):
        started_at = asyncio.get_running_loop().time()
        entry_state = None
        last_error = None
        for attempt in range(1, 4):
            edit_button = await self.find_cover_edit_button(page, ratio)
            if not edit_button:
                last_error = f"未检测到视频号{ratio}封面编辑入口"
                await asyncio.sleep(0.4)
                continue

            try:
                await self.click_cover_edit_button(edit_button, ratio)
            except Exception as e:
                last_error = str(e)
                await asyncio.sleep(0.4)
                continue

            entry_state = await self.wait_for_cover_entry_state(page, ratio, timeout=2500)
            if entry_state == "direct_edit":
                if await self.click_cover_direct_edit_if_needed(page):
                    entry_state = await self.wait_for_cover_entry_state(page, ratio, timeout=5000)

            if entry_state == "dialog":
                break
            tencent_logger.warning(f"视频号{ratio}第 {attempt} 次点击编辑后未出现裁剪弹窗，准备重试")
            await asyncio.sleep(0.5)

        if entry_state != "dialog" and not await self.wait_for_cover_dialog(page, ratio, timeout=3000):
            current_title = await self.get_visible_cover_dialog_title(page)
            raise RuntimeError(f"点击视频号{ratio}封面编辑后打开的弹窗不匹配：{current_title or last_error or '未检测到封面弹窗'}")

        thumbnail_input = await self.find_cover_upload_input(page, ratio)
        if not thumbnail_input:
            raise RuntimeError(f"未检测到视频号{ratio}封面上传入口")
        await thumbnail_input.set_input_files(thumbnail_path)
        if not await self.click_cover_confirm(page, ratio):
            raise RuntimeError(f"视频号{ratio}封面上传后无法确认")
        elapsed = asyncio.get_running_loop().time() - started_at
        tencent_logger.info(f"已设置视频号{ratio}封面，耗时 {elapsed:.1f} 秒")
        await page.wait_for_timeout(500)

    async def click_cover_edit_button(self, edit_button, ratio):
        try:
            await edit_button.wait_for(state='visible', timeout=5000)
            await edit_button.evaluate(
                """element => {
                    element.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
                    element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                    element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                    element.click();
                }"""
            )
            tencent_logger.info(f"DOM事件点击{ratio}编辑封面弹窗成功")
        except Exception as e:
            tencent_logger.warning(f"[tencent]DOM事件点击{ratio}编辑封面失败: {e}, 尝试强制点击")
            try:
                await edit_button.click(force=True, timeout=5000)
                tencent_logger.info(f"强制点击{ratio}编辑封面弹窗成功")
            except Exception as e2:
                raise RuntimeError(f"点击视频号{ratio}封面编辑失败：{e2}") from e2

    def get_cover_roots(self, page):
        content_frames = [
            frame for frame in page.frames
            if "channels.weixin.qq.com/micro/content/post/create" in frame.url
        ]
        other_frames = [frame for frame in page.frames if frame not in content_frames]
        return [*content_frames, *other_frames, page]

    def get_cover_meta(self, ratio):
        if ratio == "3:4":
            return {
                "wrap_class": "vertical-cover-wrap",
                "card_title": "个人主页卡片",
                "dialog_title": "编辑个人主页卡片",
            }
        if ratio == "4:3":
            return {
                "wrap_class": "horizon-cover-wrap",
                "card_title": "分享卡片",
                "dialog_title": "编辑分享卡片",
            }
        return {
            "wrap_class": "",
            "card_title": "",
            "dialog_title": "",
        }

    def get_cover_dialog_selectors(self, dialog_title):
        return [
            f'.weui-desktop-dialog:has-text("{dialog_title}")',
            f'.finder-common-dialog:has-text("{dialog_title}")',
            f'.edit-cover-dialog:has-text("{dialog_title}")',
        ]

    async def wait_for_cover_dialog(self, page, ratio, timeout=8000):
        dialog_title = self.get_cover_meta(ratio)["dialog_title"]
        if not dialog_title:
            return False
        started_at = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - started_at < timeout / 1000:
            if await self.is_cover_dialog_visible(page, dialog_title):
                return True
            await asyncio.sleep(0.15)
        return False

    async def wait_for_cover_entry_state(self, page, ratio, timeout=2500):
        dialog_title = self.get_cover_meta(ratio)["dialog_title"]
        started_at = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - started_at < timeout / 1000:
            if await self.is_cover_dialog_visible(page, dialog_title):
                return "dialog"
            if await self.is_cover_direct_edit_visible(page):
                return "direct_edit"
            await asyncio.sleep(0.15)
        return None

    async def is_cover_dialog_visible(self, page, dialog_title=None):
        for root in self.get_cover_roots(page):
            selectors = self.get_cover_dialog_selectors(dialog_title) if dialog_title else [
                ".weui-desktop-dialog",
                ".finder-common-dialog",
                ".edit-cover-dialog",
            ]
            for selector in selectors:
                locator = root.locator(selector).last
                try:
                    if await locator.count() and await locator.is_visible():
                        return True
                except PlaywrightError:
                    continue
        return False

    async def wait_for_cover_dialog_closed(self, page, dialog_title, timeout=12000):
        started_at = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - started_at < timeout / 1000:
            if not await self.is_cover_dialog_visible(page, dialog_title):
                return True
            await asyncio.sleep(0.2)
        return False

    async def get_visible_cover_dialog_title(self, page):
        for root in self.get_cover_roots(page):
            for title in ("编辑个人主页卡片", "编辑分享卡片"):
                for selector in self.get_cover_dialog_selectors(title):
                    locator = root.locator(selector).last
                    try:
                        if await locator.count() and await locator.is_visible():
                            return title
                    except PlaywrightError:
                        continue
        return None

    async def find_cover_upload_input(self, page, ratio):
        dialog_title = self.get_cover_meta(ratio)["dialog_title"]
        for root in self.get_cover_roots(page):
            for selector in self.get_cover_dialog_selectors(dialog_title):
                dialog = root.locator(selector).last
                try:
                    if await dialog.count() and await dialog.is_visible():
                        file_input = dialog.locator('input[type="file"][accept*="image"]').last
                        if await file_input.count():
                            return file_input
                except PlaywrightError:
                    continue
        for root in self.get_cover_roots(page):
            file_input = root.locator('input[type="file"][accept*="image"]').last
            try:
                if await file_input.count():
                    return file_input
            except PlaywrightError:
                continue
        return None

    async def click_cover_direct_edit_if_needed(self, page):
        for root in self.get_cover_roots(page):
            try:
                direct_edit = root.get_by_text("直接编辑", exact=True).last
                if not await direct_edit.count() or not await direct_edit.is_visible():
                    continue
                await direct_edit.click(force=True, timeout=5000)
                tencent_logger.info("检测到视频号封面素材浮层，已点击直接编辑")
                return True
            except PlaywrightError:
                continue
        return False

    async def is_cover_direct_edit_visible(self, page):
        for root in self.get_cover_roots(page):
            try:
                direct_edit = root.get_by_text("直接编辑", exact=True).last
                if await direct_edit.count() and await direct_edit.is_visible():
                    return True
            except PlaywrightError:
                continue
        return False

    async def click_cover_confirm(self, page, ratio):
        dialog_title = self.get_cover_meta(ratio)["dialog_title"]
        selectors = [
            'button.weui-desktop-btn_primary:has-text("确认")',
            'button.weui-desktop-btn_primary:has-text("确定")',
            'button:has-text("确认")',
            'button:has-text("确定")',
            '.weui-desktop-btn:has-text("确认")',
            '.weui-desktop-btn:has-text("确定")',
        ]
        for attempt in range(1, 4):
            for root in self.get_cover_roots(page):
                for dialog_selector in self.get_cover_dialog_selectors(dialog_title):
                    dialog = root.locator(dialog_selector).last
                    try:
                        if not await dialog.count() or not await dialog.is_visible():
                            continue
                    except PlaywrightError:
                        continue
                    for selector in selectors:
                        locator = dialog.locator(selector).last
                        try:
                            if await locator.count():
                                await locator.click(force=True, timeout=5000)
                                if await self.wait_for_cover_dialog_closed(page, dialog_title):
                                    return True
                                tencent_logger.warning(f"视频号{ratio}封面第 {attempt} 次确认后弹窗仍未关闭，准备重试")
                        except PlaywrightError:
                            continue
        return False

    async def find_cover_edit_button(self, page, ratio):
        meta = self.get_cover_meta(ratio)
        if not meta["wrap_class"]:
            return None
        selectors = [
            f'div.{meta["wrap_class"]}:has-text("{meta["card_title"]}"):has-text("{ratio}") .edit-btn',
            f'div.{meta["wrap_class"]}:has-text("{ratio}") .edit-btn',
            f'div.{meta["wrap_class"]}:has-text("{meta["card_title"]}") .edit-btn',
        ]
        for root in self.get_cover_roots(page):
            for selector in selectors:
                locator = root.locator(selector).first
                try:
                    if await locator.count():
                        return locator
                except PlaywrightError:
                    continue

            ratio_label = root.get_by_text(ratio, exact=True).first
            try:
                if await ratio_label.count():
                    locator = ratio_label.locator(
                        "xpath=ancestor::*[contains(@class, 'img-popover-wrap')][1]//*[contains(@class, 'edit-btn')]"
                    ).first
                    if await locator.count():
                        return locator
            except PlaywrightError:
                continue
        return None

    async def add_short_title(self, page):
        short_title_element = page.locator('input[placeholder*="概括视频主要内容"]').first
        if await short_title_element.count():
            short_title = format_str_for_short_title(self.title)
            await short_title_element.fill(short_title)

    async def click_publish(self, page):
        for attempt in range(1, 7):
            if page.is_closed():
                raise RuntimeError("视频号发布页已关闭，无法继续点击发表")
            try:
                publish_buttion = page.locator('div.form-btns button:has-text("发表")')
                if not await publish_buttion.count():
                    publish_buttion = page.get_by_role("button", name="发表", exact=True)
                if not await publish_buttion.count():
                    raise RuntimeError("未找到视频号发表按钮")

                await publish_buttion.first.wait_for(state="visible", timeout=10000)
                button_class = await publish_buttion.first.get_attribute("class") or ""
                if "disabled" in button_class or "weui-desktop-btn_disabled" in button_class:
                    raise RuntimeError("视频号发表按钮仍不可用，请检查视频是否上传完成或必填项是否填写")

                await publish_buttion.first.click()
                await page.wait_for_url("https://channels.weixin.qq.com/platform/post/list", timeout=8000)
                tencent_logger.success("  [-]视频发布成功")
                return
            except PlaywrightTimeoutError as e:
                current_url = "" if page.is_closed() else page.url
                if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                    tencent_logger.success("  [-]视频发布成功")
                    return
                tencent_logger.warning(f"  [-] 视频号第 {attempt} 次点击发表后未跳转: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                current_url = "" if page.is_closed() else page.url
                if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                    tencent_logger.success("  [-]视频发布成功")
                    return
                if page.is_closed() or "Target page" in str(e):
                    raise RuntimeError(f"视频号发布页已关闭：{e}") from e
                tencent_logger.warning(f"  [-] 视频号第 {attempt} 次发表失败: {e}")
                await asyncio.sleep(1)
        raise RuntimeError("视频号发布未完成：多次点击发表后仍未进入作品列表")

    async def detect_upload_status(self, page):
        max_wait_seconds = 20 * 60
        started_at = asyncio.get_running_loop().time()
        while True:
            if page.is_closed():
                raise RuntimeError("视频号发布页已关闭，无法确认上传状态")
            if asyncio.get_running_loop().time() - started_at > max_wait_seconds:
                raise RuntimeError("视频号上传等待超时")
            # 匹配删除按钮，代表视频上传完毕，如果不存在，代表视频正在上传，则等待
            try:
                # 匹配删除按钮，代表视频上传完毕
                publish_button_class = await page.get_by_role("button", name="发表").get_attribute('class') or ""
                if "weui-desktop-btn_disabled" not in publish_button_class and "disabled" not in publish_button_class:
                    tencent_logger.info("  [-]视频上传完毕")
                    break
                else:
                    tencent_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)
                    # 出错了视频出错
                    if await page.locator('div.status-msg.error').count() and await page.locator(
                            'div.media-status-content div.tag-inner:has-text("删除")').count():
                        tencent_logger.error("  [-] 发现上传出错了...准备重试")
                        await self.handle_upload_error(page)
            except PlaywrightError as e:
                if page.is_closed() or "Target page" in str(e):
                    raise RuntimeError(f"视频号发布页已关闭：{e}") from e
                tencent_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)
            except Exception as e:
                tencent_logger.warning(f"  [-] 检查视频号上传状态失败，继续等待: {e}")
                await asyncio.sleep(2)

    async def add_title_tags(self, page):
        description = self.build_description_text()
        editor = await self.find_description_editor(page)
        await self.fill_editor(page, editor, description)
        actual_text = await self.get_editor_text(editor)
        if self.title.strip() and self.title.strip() not in actual_text:
            raise RuntimeError("视频号视频描述填写失败：标题未写入描述框")
        missing_tags = [
            tag for tag in self.normalized_tags()
            if f"#{tag}" not in actual_text and tag not in actual_text
        ]
        if missing_tags:
            raise RuntimeError(f"视频号视频描述填写失败：话题未写入 {missing_tags}")
        tencent_logger.info(f"成功添加hashtag: {len(self.tags)}")

    def normalized_tags(self):
        normalized = []
        for tag in self.tags or []:
            tag = str(tag).strip().lstrip("#")
            if tag:
                normalized.append(tag)
        return normalized

    def build_description_text(self):
        title = str(self.title or "").strip()
        tags_text = " ".join(f"#{tag}" for tag in self.normalized_tags())
        return " ".join(part for part in (title, tags_text) if part).strip()

    async def find_description_editor(self, page):
        candidates = [
            page.get_by_text("视频描述", exact=True)
            .locator("xpath=following-sibling::div")
            .locator('[contenteditable="true"], textarea, input, div.input-editor')
            .first,
            page.locator('div.input-editor[placeholder*="添加描述"]').first,
            page.locator('[placeholder*="添加描述"]').first,
            page.locator('[contenteditable="true"][data-placeholder*="添加描述"]').first,
            page.locator('div.input-editor[contenteditable="true"]').first,
            page.locator('div.input-editor').first,
            page.locator('[contenteditable="true"]').first,
        ]
        for locator in candidates:
            try:
                if await locator.count():
                    await locator.wait_for(state="visible", timeout=5000)
                    return locator
            except PlaywrightError:
                continue
        raise RuntimeError("未找到视频号视频描述输入框")

    async def fill_editor(self, page, locator, text):
        await locator.scroll_into_view_if_needed()
        await locator.click(force=True, timeout=10000)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(text, delay=12)
        await page.wait_for_timeout(500)

    async def get_editor_text(self, locator):
        return await locator.evaluate(
            """(element) => {
                const target = element.matches('textarea,input,[contenteditable="true"]')
                    ? element
                    : element.querySelector('textarea,input,[contenteditable="true"]') || element;
                return target.value || target.innerText || target.textContent || '';
            }"""
        )

    async def add_collection(self, page):
        collection_elements = page.get_by_text("添加到合集").locator("xpath=following-sibling::div").locator(
            '.option-list-wrap > div')
        if await collection_elements.count() > 1:
            await page.get_by_text("添加到合集").locator("xpath=following-sibling::div").click()
            await collection_elements.first.click()

    async def add_original(self, page):
        if await page.get_by_label("视频为原创").count():
            await page.get_by_label("视频为原创").check()
        # 检查 "我已阅读并同意 《视频号原创声明使用条款》" 元素是否存在
        label_locator = await page.locator('label:has-text("我已阅读并同意 《视频号原创声明使用条款》")').is_visible()
        if label_locator:
            await page.get_by_label("我已阅读并同意 《视频号原创声明使用条款》").check()
            await page.get_by_role("button", name="声明原创").click()
        # 2023年11月20日 wechat更新: 可能新账号或者改版账号，出现新的选择页面
        if await page.locator('div.label span:has-text("声明原创")').count() and self.category:
            # 因处罚无法勾选原创，故先判断是否可用
            if not await page.locator('div.declare-original-checkbox input.ant-checkbox-input').is_disabled():
                await page.locator('div.declare-original-checkbox input.ant-checkbox-input').click()
                if not await page.locator(
                        'div.declare-original-dialog label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible').count():
                    await page.locator('div.declare-original-dialog input.ant-checkbox-input:visible').click()
            if await page.locator('div.original-type-form > div.form-label:has-text("原创类型"):visible').count():
                await page.locator('div.form-content:visible').click()  # 下拉菜单
                await page.locator(
                    f'div.form-content:visible ul.weui-desktop-dropdown__list li.weui-desktop-dropdown__list-ele:has-text("{self.category}")').first.click()
                await page.wait_for_timeout(1000)
            if await page.locator('button:has-text("声明原创"):visible').count():
                await page.locator('button:has-text("声明原创"):visible').click()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
