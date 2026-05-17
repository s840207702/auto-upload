# -*- coding: utf-8 -*-
from datetime import datetime
from time import sleep

from playwright.async_api import Playwright, async_playwright, Page
import os
import asyncio

from conf import LOCAL_CHROME_PATH
from utils.base_social_media import (
    set_init_script,
    launch_publish_browser,
    new_publish_context,
    goto_and_reveal,
    keep_browser_open_for_dry_run,
)
from utils.log import douyin_logger, DOUYIN_SCREENSHOT_DIR
from utils.publish_limits import normalize_publish_tags


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=5000)
        except:
            print("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 2024.06.17 抖音创作者中心改版
        if await page.get_by_text('手机号登录').count() or await page.get_by_text('扫码登录').count():
            print("[+] 等待5秒 cookie 失效")
            return False
        else:
            print("[+] cookie 有效")
            return True


async def douyin_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        douyin_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await douyin_cookie_gen(account_file)
    return True


async def douyin_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {
            'headless': False,
            # 'args': ['--start-maximized']  # 启动时最大化窗口
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context(
            permissions=[],  # 禁用所有权限请求
            geolocation=None,  # 禁用地理位置
            locale='zh-CN',  # 设置语言为中文
            timezone_id='Asia/Shanghai'  # 设置时区
        )
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


class DouYinVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, category=None, thumbnail_path=None, thumbnail_paths=None, dry_run=False, dry_run_hold_browser=True):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = normalize_publish_tags(tags)
        self.publish_date = publish_date
        self.account_file = account_file
        self.category = category  # 新增category参数
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path
        self.thumbnail_paths = dict(thumbnail_paths or {})
        if thumbnail_path and "3:4" not in self.thumbnail_paths:
            self.thumbnail_paths["3:4"] = thumbnail_path
        self.dry_run = dry_run
        self.dry_run_hold_browser = dry_run_hold_browser

    async def set_schedule_time_douyin(self, page, publish_date):
        target_time = publish_date.strftime("%Y-%m-%d %H:%M")
        douyin_logger.info(f"正在设置抖音定时发布时间：{target_time}")

        schedule_radio = page.locator("[class^='radio']:has-text('定时发布')").last
        await schedule_radio.wait_for(state="visible", timeout=15000)
        for _ in range(3):
            radio_class = await schedule_radio.get_attribute("class") or ""
            radio_text = await schedule_radio.inner_text(timeout=2000)
            if "checked" in radio_class or "已选" in radio_text:
                break
            await schedule_radio.click(force=True, timeout=5000)
            await page.wait_for_timeout(1000)

        date_input = page.locator('.semi-input[placeholder="日期和时间"]').last
        await date_input.wait_for(state="visible", timeout=15000)
        await date_input.click(force=True, timeout=5000)
        await date_input.fill(target_time, timeout=5000)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(800)

        try:
            await date_input.evaluate(
                """
                node => {
                  node.dispatchEvent(new Event('input', { bubbles: true }));
                  node.dispatchEvent(new Event('change', { bubbles: true }));
                  node.blur();
                }
                """
            )
        except Exception:
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(800)

        try:
            actual_time = (await date_input.input_value(timeout=3000)).strip()
        except Exception:
            actual_time = ""

        if self._schedule_time_matches(actual_time, target_time):
            douyin_logger.success(f"抖音定时发布时间已确认：{actual_time or target_time}")
            return

        raise RuntimeError(f"抖音定时发布时间写入失败，目标={target_time}，实际={actual_time}")

    @staticmethod
    def _schedule_time_matches(actual_time: str, target_time: str) -> bool:
        normalized_actual = "".join(str(actual_time or "").split())
        normalized_target = "".join(str(target_time or "").split())
        return bool(normalized_actual) and (
            normalized_actual == normalized_target
            or normalized_actual.startswith(normalized_target)
            or normalized_target in normalized_actual
        )

    async def handle_upload_error(self, page):
        douyin_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def clear_platform_title(self, page):
        title_input = page.locator("div[class^='container-'] input[type=text]").first
        try:
            if await title_input.count():
                await title_input.fill("")
                douyin_logger.info("抖音独立标题已留空，统一使用作品描述承载标题和话题")
        except Exception as e:
            douyin_logger.warning(f"抖音独立标题清空失败，继续填写作品描述: {e}")

    async def fill_description_and_topics(self, page):
        douyin_logger.info("正在填充抖音作品描述...")
        editor = page.locator(".zone-container").first
        await editor.wait_for(state="visible", timeout=15000)
        await editor.click(force=True)
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")

        title = (self.title or "").strip()
        if title:
            await page.keyboard.insert_text(title)

        added = 0
        for tag in self.tags:
            tag_name = str(tag).strip().lstrip("#")
            if not tag_name:
                continue
            if title or added:
                await page.keyboard.insert_text(" ")
            await page.keyboard.type("#" + tag_name, delay=40)
            await page.keyboard.press("Space")
            await page.wait_for_timeout(500)
            added += 1
        douyin_logger.info(f"抖音作品描述已写入标题和{added}个话题")

    async def wait_publish_button_ready(self, page):
        publish_button = page.get_by_role('button', name="发布", exact=True).last
        await publish_button.wait_for(state="visible", timeout=60000)

        for attempt in range(60):
            try:
                button_class = await publish_button.get_attribute("class") or ""
                disabled_attr = await publish_button.get_attribute("disabled")
                aria_disabled = await publish_button.get_attribute("aria-disabled")
                is_enabled = await publish_button.is_enabled(timeout=1000)
                if (
                    is_enabled
                    and disabled_attr is None
                    and aria_disabled != "true"
                    and "disabled" not in button_class.lower()
                ):
                    await publish_button.scroll_into_view_if_needed(timeout=3000)
                    return publish_button
            except Exception as e:
                douyin_logger.warning(f"抖音发布按钮状态检测失败，第{attempt + 1}次重试: {e}")
            await page.wait_for_timeout(1000)

        raise RuntimeError("抖音发布按钮长时间不可用，已停止点击，避免重复触发页面闪动")

    async def upload(self, playwright: Playwright) -> None:
        page = getattr(self, "external_page", None)
        context = getattr(self, "external_context", None)
        browser = getattr(self, "external_browser", None)
        managed_browser = page is None
        if managed_browser:
            # 使用 Chromium 浏览器启动一个浏览器实例
            browser = await launch_publish_browser(playwright, executable_path=self.local_executable_path)
            # 创建一个浏览器上下文，使用指定的 cookie 文件
            context = await new_publish_context(
                browser,
                storage_state=f"{self.account_file}",
            )
            context = await set_init_script(context)

            # 创建一个新的页面
            page = await context.new_page()

        try:
            await goto_and_reveal(
                page,
                "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                timeout=30000,
            )
            douyin_logger.info("[+] 成功进入version_2发布页面!")
        except Exception as e:
            douyin_logger.error(f"  [-] 超时未进入视频发布页面，cookies过期或者其他原因，重新尝试...{e}")

        await page.locator("div[class^='upload-card'] input[type=file]").set_input_files(self.file_path)  #上传视频
        douyin_logger.info(f'[+]正在上传-------{self.title}.mp4')
        await asyncio.sleep(1)

        await self.clear_platform_title(page)
        await self.fill_description_and_topics(page)

        while True:
            # 判断重新上传按钮是否存在，如果不存在，代表视频正在上传，则等待
            try:
                #  新版：定位重新上传
                number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
                if number > 0:
                    douyin_logger.success("  [-]视频上传完毕")
                    break
                else:
                    douyin_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)

                    if await page.locator('div.progress-div > div:has-text("上传失败")').count():
                        douyin_logger.error("  [-] 发现上传出错了... 准备重试")
                        await self.handle_upload_error(page)
            except:
                douyin_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)
        
        #上传视频封面
        await self.set_thumbnail(page, self.thumbnail_path)
        await asyncio.sleep(1)
        # # 頭條/西瓜
        # third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        # # 定位是否有第三方平台
        # if await page.locator(third_part_element).count():
        #     # 检测是否是已选中状态
        #     if 'semi-switch-checked' not in await page.eval_on_selector(third_part_element, 'div => div.className'):
        #         await page.locator(third_part_element).locator('input.semi-switch-native-control').click()

        if self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        if self.dry_run:
            if managed_browser:
                await keep_browser_open_for_dry_run(
                    page,
                    context,
                    browser,
                    account_file=self.account_file,
                    logger=douyin_logger,
                    platform_name="抖音",
                    block_until_close=self.dry_run_hold_browser,
                )
            return

        publish_button = await self.wait_publish_button_ready(page)
        douyin_logger.info("抖音发布按钮已可用，准备点击发布")

        async def close_unexpected_publish_popup(popup):
            try:
                await popup.wait_for_load_state("commit", timeout=1500)
            except Exception:
                pass
            try:
                douyin_logger.warning(f"抖音发布瞬间检测到异常新标签页，已关闭: {popup.url}")
                await popup.close()
            except Exception:
                pass

        def on_new_page(popup):
            asyncio.create_task(close_unexpected_publish_popup(popup))

        context.on("page", on_new_page)
        try:
            await publish_button.click(timeout=10000)
            await page.wait_for_url(
                "https://creator.douyin.com/creator-micro/content/manage**",
                timeout=90000,
            )
            douyin_logger.success("  [-]视频发布成功")
        except Exception as e:
            screenshot_path = os.path.join(DOUYIN_SCREENSHOT_DIR, f"douyin_publish_timeout_{int(asyncio.get_event_loop().time()*1000)}.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            raise RuntimeError(f"抖音点击发布后未确认跳转，已保留截图：{screenshot_path}") from e
        finally:
            try:
                context.remove_listener("page", on_new_page)
            except Exception:
                pass

        await context.storage_state(path=self.account_file)  # 保存cookie
        douyin_logger.success('  [-]cookie更新完毕！')
        # 关闭浏览器上下文和浏览器实例
        if managed_browser:
            await context.close()
            await browser.close()
    
    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        targets = []
        if self.thumbnail_paths.get("4:3"):
            targets.append(("4:3", self.thumbnail_paths["4:3"]))
        if self.thumbnail_paths.get("3:4"):
            targets.append(("3:4", self.thumbnail_paths["3:4"]))
        if not targets and thumbnail_path:
            targets.append(("3:4", thumbnail_path))

        if not targets:
            douyin_logger.info("没上传封面，就不要封面了，让系统自动生成吧...")
            await asyncio.sleep(1)
            return

        first_ratio, first_path = targets[0]
        await self.open_cover_editor(page, first_ratio)
        switched_by_action = False
        for index, (ratio, cover_path) in enumerate(targets):
            if index > 0 and not switched_by_action:
                await self.switch_cover_ratio(page, ratio)
            switched_by_action = False
            await self.wait_cover_editor_ready(page, ratio)
            await self.upload_cover_image(page, cover_path, ratio)
            if ratio == "4:3" and index < len(targets) - 1:
                await self.click_cover_action(page, "设置竖封面")
                switched_by_action = True
            else:
                await self.click_cover_action(page, "完成")
        await asyncio.sleep(1)

    async def open_cover_editor(self, page: Page, ratio: str):
        label = "横封面4:3" if ratio == "4:3" else "竖封面3:4"
        card = page.locator(f'div.coverControl-CjlzqC:has-text("{label}")').first
        if not await card.count():
            card = page.locator('div').filter(has_text=label).locator("div[class^='cover']").first
        await card.wait_for(state='visible', timeout=15000)
        await card.click(force=True, timeout=5000)
        douyin_logger.info(f"点击成功->{label}选择封面")
        await page.wait_for_timeout(2000)

    async def wait_cover_editor_ready(self, page: Page, ratio: str):
        upload_button = page.get_by_text("上传封面", exact=True).last
        await upload_button.wait_for(state="visible", timeout=15000)
        await page.locator('input[type="file"][accept*="image"]').last.wait_for(state="attached", timeout=15000)
        douyin_logger.info(f"抖音{ratio}封面编辑器已就绪")
        await page.wait_for_timeout(800)

    async def switch_cover_ratio(self, page: Page, ratio: str):
        action_text = "设置横封面" if ratio == "4:3" else "设置竖封面"
        button = page.locator(f'button:has-text("{action_text}")').last
        if await button.count():
            await button.click(force=True, timeout=5000)
            await page.wait_for_timeout(1000)
            return
        tab = page.get_by_text(action_text, exact=True).last
        if await tab.count():
            await tab.click(force=True, timeout=5000)
            await page.wait_for_timeout(1000)
            return
        raise RuntimeError(f"抖音封面弹窗无法切换到 {ratio}")

    async def upload_cover_image(self, page: Page, cover_path: str, ratio: str):
        before_error_count = await page.locator('text=不支持的图片格式').count()
        try:
            upload_button = page.get_by_text("上传封面", exact=True).last
            async with page.expect_file_chooser(timeout=8000) as fc_info:
                await upload_button.click(force=True, timeout=5000)
            file_chooser = await fc_info.value
            await file_chooser.set_files(cover_path)
        except Exception as e:
            douyin_logger.warning(f"点击正式上传封面入口失败，尝试隐藏文件入口: {e}")
            file_input = page.locator('input[type="file"][accept*="image"]').last
            await file_input.wait_for(state='attached', timeout=15000)
            await file_input.set_input_files(cover_path)
        douyin_logger.info(f"上传抖音{ratio}封面成功")
        await page.wait_for_timeout(2500)
        after_error_count = await page.locator('text=不支持的图片格式').count()
        if after_error_count > before_error_count:
            raise RuntimeError(f"抖音{ratio}封面上传失败：平台提示不支持的图片格式")

    async def click_cover_action(self, page: Page, action_text: str):
        button = page.locator(f'button:has-text("{action_text}")').last
        await button.wait_for(state='visible', timeout=15000)
        await button.click(force=True, timeout=5000)
        douyin_logger.info(f"点击抖音封面按钮成功：{action_text}")
        await page.wait_for_timeout(2500 if action_text != "完成" else 1500)

    async def set_location(self, page: Page, location: str = "杭州市"):
        # todo supoort location later
        # await page.get_by_text('添加标签').locator("..").locator("..").locator("xpath=following-sibling::div").locator(
        #     "div.semi-select-single").nth(0).click()
        await page.locator('div.semi-select span:has-text("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


