# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Page, Playwright, async_playwright
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
from utils.files_times import get_absolute_path
from utils.log import kuaishou_logger, KUAISHOU_SCREENSHOT_DIR
from utils.publish_limits import KUAISHOU_TAG_COUNT, normalize_publish_tags


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://cp.kuaishou.com/article/publish/video")
        try:
            await page.wait_for_selector("div.names div.container div.name:text('机构服务')", timeout=5000)  # 等待5秒

            kuaishou_logger.info("[+] 等待5秒 cookie 失效")
            return False
        except:
            kuaishou_logger.success("[+] cookie 有效")
            return True


async def ks_setup(account_file, handle=False):
    account_file = get_absolute_path(account_file, "ks_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        kuaishou_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await get_ks_cookie(account_file)
    return True


async def get_ks_cookie(account_file):
    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': False,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context(
            permissions=[],  # 禁用所有权限请求
            geolocation=None,  # 禁用地理位置
            locale='zh-CN',  # 设置语言为中文
            timezone_id='Asia/Shanghai'  # 设置时区
        )  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://cp.kuaishou.com")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


class KSVideo(object):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime,
        account_file,
        thumbnail_path=None,
        thumbnail_paths=None,
        dry_run=False,
        dry_run_hold_browser=True,
    ):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = normalize_publish_tags(tags, max_count=KUAISHOU_TAG_COUNT)
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y-%m-%d %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path
        self.thumbnail_paths = {
            str(ratio): path
            for ratio, path in (thumbnail_paths or {}).items()
            if ratio in {"3:4", "4:3"} and path
        }
        self.dry_run = dry_run
        self.dry_run_hold_browser = dry_run_hold_browser

    async def handle_upload_error(self, page):
        kuaishou_logger.error("视频出错了，重新上传中")
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def upload(self, playwright: Playwright) -> None:
        page = getattr(self, "external_page", None)
        context = getattr(self, "external_context", None)
        browser = getattr(self, "external_browser", None)
        managed_browser = page is None
        if managed_browser:
            # 使用 Chromium 浏览器启动一个浏览器实例
            browser = await launch_publish_browser(playwright, executable_path=self.local_executable_path)
            context = await new_publish_context(
                browser,
                storage_state=f"{self.account_file}",
            )
            context = await set_init_script(context)
            # 创建一个新的页面
            page = await context.new_page()
        # 访问指定的 URL
        await goto_and_reveal(
            page,
            "https://cp.kuaishou.com/article/publish/video",
            wait_until="commit",
            timeout=90000,
        )
        kuaishou_logger.info("快手发布页已打开，先刷新一次再开始上传")
        await page.reload(wait_until="commit", timeout=90000)
        await page.wait_for_timeout(1000)
        kuaishou_logger.info('正在上传-------{}.mp4'.format(self.title))
        await self.upload_video_file(page)

        await page.locator("#work-description-edit").wait_for(state="visible", timeout=60000)

        # 等待按钮可交互
        new_feature_button = page.locator('button[type="button"] span:text("我知道了")')
        if await new_feature_button.count() > 0:
            await new_feature_button.click()

        await self.fill_description_and_topics(page)
        await self.wait_video_upload_done(page)

        if self.thumbnail_path or self.thumbnail_paths:
            await self.set_thumbnail_from_cover_dialog(page)

        # 定时任务
        if self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        if self.dry_run:
            if managed_browser:
                await keep_browser_open_for_dry_run(
                    page,
                    context,
                    browser,
                    account_file=self.account_file,
                    logger=kuaishou_logger,
                    platform_name="快手",
                    block_until_close=self.dry_run_hold_browser,
                )
            return

        # 判断视频是否发布成功
        while True:
            try:
                publish_button = page.get_by_text("发布", exact=True)
                if await publish_button.count() > 0:
                    await publish_button.click()

                await asyncio.sleep(1)
                confirm_button = page.get_by_text("确认发布")
                if await confirm_button.count() > 0:
                    await confirm_button.click()

                # 等待页面跳转，确认发布成功
                await page.wait_for_url(
                    "https://cp.kuaishou.com/article/manage/video?status=2&from=publish",
                    timeout=5000,
                )
                kuaishou_logger.success("视频发布成功")
                break
            except Exception as e:
                kuaishou_logger.info(f"视频正在发布中... 错误: {e}")
                screenshot_path = os.path.join(KUAISHOU_SCREENSHOT_DIR, f"ks_{int(asyncio.get_event_loop().time()*1000)}.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                await asyncio.sleep(1)

        await context.storage_state(path=self.account_file)  # 保存cookie
        kuaishou_logger.info('cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        if managed_browser:
            await context.close()
            await browser.close()

    async def upload_video_file(self, page):
        await self.dismiss_previous_draft_prompt(page)

        file_inputs = [
            'input[type="file"][accept*="video"]',
            'input[type="file"]',
            '[class^="upload-btn-input"]',
        ]
        upload_button_factories = [
            lambda: page.locator("button[class^='_upload-btn']").first,
            lambda: page.get_by_role("button", name="上传视频").first,
            lambda: page.get_by_text("上传视频", exact=True).first,
            lambda: page.locator('button:has-text("上传")').first,
        ]

        started_at = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - started_at < 60:
            await self.dismiss_previous_draft_prompt(page)

            for selector in file_inputs:
                locator = page.locator(selector).first
                try:
                    if await locator.count():
                        await locator.set_input_files(self.file_path)
                        kuaishou_logger.info(f"已通过文件输入框上传视频: {selector}")
                        return
                except Exception as e:
                    kuaishou_logger.warning(f"快手文件输入框上传失败 {selector}: {e}")

            for factory in upload_button_factories:
                upload_button = factory()
                try:
                    if await upload_button.count():
                        await upload_button.wait_for(state='visible', timeout=3000)
                        async with page.expect_file_chooser(timeout=5000) as fc_info:
                            await upload_button.click(force=True, timeout=5000)
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(self.file_path)
                        kuaishou_logger.info("已通过上传按钮选择视频")
                        return
                except Exception as e:
                    kuaishou_logger.warning(f"快手上传按钮尝试失败: {e}")
            await asyncio.sleep(1)
        raise RuntimeError("未找到快手视频上传入口")

    async def dismiss_previous_draft_prompt(self, page: Page):
        try:
            body_text = await page.locator("body").inner_text(timeout=2000)
        except Exception:
            return
        if "还有上次未发布的视频" not in body_text:
            return

        kuaishou_logger.info("检测到快手未发布草稿提示，放弃旧草稿后重新上传")
        abandon_button = page.get_by_text("放弃", exact=True).last
        try:
            await abandon_button.click(force=True, timeout=5000)
            await page.wait_for_timeout(1000)
        except Exception as e:
            kuaishou_logger.warning(f"快手旧草稿提示关闭失败，将继续尝试上传：{e}")

    async def fill_description_and_topics(self, page: Page):
        kuaishou_logger.info("正在填充快手作品描述和话题...")
        editor = page.locator("#work-description-edit").first
        await editor.wait_for(state="visible", timeout=30000)
        await editor.click(force=True, timeout=5000)
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")
        await page.keyboard.type(self.title, delay=25)

        async def get_tag_nodes():
            return await editor.locator(".at-tag-item").evaluate_all(
                r"""els => els.map(el => ({
                    text: (el.innerText || el.textContent || "").replace(/\s+/g, ""),
                    name: el.getAttribute("data-tag-name") || ""
                }))"""
            )

        async def has_tag_node(tag_name: str) -> bool:
            tag_nodes = await get_tag_nodes()
            return any(
                (item.get("name") or item.get("text", "").lstrip("#")) == tag_name
                for item in tag_nodes
            )

        for index, tag in enumerate(self.tags, start=1):
            clean_tag = str(tag).lstrip("#").strip()
            if not clean_tag:
                continue
            kuaishou_logger.info(f"正在添加快手第{index}个话题：#{clean_tag}")
            accepted = False
            for attempt in range(1, 4):
                await editor.click(force=True, timeout=3000)
                await page.keyboard.press("End")
                await page.keyboard.press("Space")
                await page.wait_for_timeout(200)
                await page.keyboard.press("Shift+Digit3")
                await page.wait_for_timeout(800)
                await page.keyboard.type(clean_tag, delay=110)
                await page.wait_for_timeout(1000)
                await page.keyboard.press("Space")
                await page.wait_for_timeout(900)
                if await has_tag_node(clean_tag):
                    accepted = True
                    break
                kuaishou_logger.warning(f"快手话题 #{clean_tag} 第{attempt}次未生成节点，准备重试")
                await page.keyboard.press("Control+Z")
                await page.wait_for_timeout(500)
            if not accepted:
                tag_nodes = await get_tag_nodes()
                text = (await editor.inner_text(timeout=3000)).replace("\xa0", " ")
                raise RuntimeError(f"快手话题节点写入校验失败，缺失：{clean_tag}，当前内容：{text}，节点={tag_nodes}")

        tag_nodes = await get_tag_nodes()
        tag_names = {item.get("name") or item.get("text", "").lstrip("#") for item in tag_nodes}
        missing_tags = [
            tag
            for tag in self.tags
            if str(tag).lstrip("#").strip() not in tag_names
        ]
        if missing_tags:
            text = (await editor.inner_text(timeout=3000)).replace("\xa0", " ")
            raise RuntimeError(f"快手话题节点写入校验失败，缺失：{missing_tags}，当前内容：{text}，节点={tag_nodes}")
        kuaishou_logger.success("快手作品描述和话题已写入")

    async def visible_text_count(self, page: Page, text: str) -> int:
        locator = page.locator(f"text={text}")
        try:
            return await locator.evaluate_all(
                """els => els.filter(el => {
                    const style = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                }).length"""
            )
        except Exception:
            return 0

    async def wait_video_upload_done(self, page: Page):
        started_at = asyncio.get_running_loop().time()
        last_log_second = -1
        while asyncio.get_running_loop().time() - started_at < 180:
            visible_uploading = await self.visible_text_count(page, "上传中")
            body_text = ""
            try:
                body_text = await page.locator("body").inner_text(timeout=2000)
            except Exception:
                pass

            if visible_uploading == 0 and "上传中" not in body_text and "重新上传" in body_text:
                kuaishou_logger.success("快手视频上传完毕")
                return

            elapsed = int(asyncio.get_running_loop().time() - started_at)
            if elapsed // 10 != last_log_second // 10:
                kuaishou_logger.info("快手视频仍在上传或处理封面帧...")
                last_log_second = elapsed
            await page.wait_for_timeout(1000)

        raise RuntimeError("快手视频上传等待超时，无法继续设置封面")

    def choose_thumbnail_for_cover_editor(self):
        if self.thumbnail_paths.get("3:4"):
            return "3:4", self.thumbnail_paths["3:4"]
        if self.thumbnail_paths.get("4:3"):
            return "4:3", self.thumbnail_paths["4:3"]
        return None, self.thumbnail_path

    async def get_cover_modal(self, page: Page):
        modal = page.locator(".ant-modal-content").filter(has_text="封面截取").filter(has_text="上传封面").last
        await modal.wait_for(state="visible", timeout=10000)
        return modal

    async def select_cover_ratio(self, page: Page, modal, ratio: str | None):
        if ratio not in {"3:4", "4:3"}:
            return

        kuaishou_logger.info(f"快手封面裁剪比例选择：{ratio}")
        ratio_item = modal.locator('div[class*="ratio-item"]').filter(has_text=ratio).first
        await ratio_item.wait_for(state="visible", timeout=5000)
        await ratio_item.click(force=True, timeout=5000)
        await page.wait_for_timeout(800)

    async def wait_cover_image_ready(self, page: Page, modal, previous_blob_count: int):
        for _ in range(50):
            try:
                modal_text = await modal.inner_text(timeout=2000)
            except Exception:
                modal_text = ""
            modal_blob_count = await modal.locator('img[src^="blob:"]').count()
            is_processing = any(text in modal_text for text in ("上传中", "加载中", "处理中"))
            if not is_processing and ("清空上传" in modal_text or modal_blob_count > previous_blob_count):
                return
            await page.wait_for_timeout(500)
        raise RuntimeError("快手封面图片上传后未进入可确认状态")

    async def wait_cover_confirm_ready(self, page: Page, confirm_button):
        for _ in range(60):
            try:
                visible = await confirm_button.is_visible(timeout=500)
                disabled = await confirm_button.evaluate(
                    """el => {
                        const button = el.closest('button') || el;
                        return Boolean(
                            button.disabled ||
                            button.getAttribute('aria-disabled') === 'true' ||
                            button.className.includes('disabled')
                        );
                    }"""
                )
                if visible and not disabled:
                    return
            except Exception:
                pass
            await page.wait_for_timeout(500)
        raise RuntimeError("快手封面确认按钮长时间不可用")

    async def wait_cover_modal_closed(self, page: Page, modal):
        for _ in range(90):
            try:
                if not await modal.is_visible(timeout=500):
                    await page.wait_for_timeout(1200)
                    return
            except Exception:
                await page.wait_for_timeout(1200)
                return
            await page.wait_for_timeout(500)
        raise RuntimeError("快手封面确认后弹窗未关闭，封面可能仍在上传或裁剪处理中")

    async def click_upload_cover_tab(self, page: Page, modal):
        upload_tab = modal.locator('[role="tab"]').filter(has_text="上传封面").first
        if not await upload_tab.count():
            upload_tab = modal.get_by_text("上传封面", exact=True).last
        await upload_tab.click(force=True, timeout=5000)
        await page.wait_for_timeout(1000)

    async def set_thumbnail_from_cover_dialog(self, page: Page):
        target_ratio, thumbnail_path = self.choose_thumbnail_for_cover_editor()
        if not thumbnail_path or not os.path.exists(thumbnail_path):
            kuaishou_logger.warning(f"快手封面文件不存在，已跳过：{thumbnail_path}")
            return

        kuaishou_logger.info("正在设置快手封面...")
        opener = page.locator('div[class*="cover-full-editor"]').first
        await opener.wait_for(state="visible", timeout=30000)
        await opener.scroll_into_view_if_needed()
        await opener.click(force=True, timeout=5000)

        modal = await self.get_cover_modal(page)
        await self.click_upload_cover_tab(page, modal)
        await self.select_cover_ratio(page, modal, target_ratio)
        started_at = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - started_at < 20:
            modal_text = await modal.inner_text(timeout=2000)
            if "加载中" not in modal_text:
                break
            await page.wait_for_timeout(500)

        previous_blob_count = await modal.locator('img[src^="blob:"]').count()
        image_input = modal.locator('input[type="file"][accept*="image"]').last
        if not await image_input.count():
            image_input = page.locator('input[type="file"][accept*="image"]').last
        await image_input.wait_for(state="attached", timeout=10000)
        await image_input.set_input_files(thumbnail_path)
        kuaishou_logger.info(f"快手封面已按 {target_ratio or '当前'} 比例上传：{thumbnail_path}")

        await self.wait_cover_image_ready(page, modal, previous_blob_count)
        await page.wait_for_timeout(3000)

        confirm_button = modal.locator("button").filter(has_text="确认").last
        if not await confirm_button.count():
            confirm_button = modal.get_by_text("确认", exact=True).last
        for attempt in range(1, 4):
            await self.wait_cover_confirm_ready(page, confirm_button)
            await confirm_button.click(force=True, timeout=5000)

            for _ in range(36):
                body_text = await page.locator("body").inner_text(timeout=2000)
                try:
                    modal_visible = await modal.is_visible(timeout=500)
                except Exception:
                    modal_visible = False
                if "请上传图片" in body_text:
                    raise RuntimeError("快手封面上传失败：平台提示请上传图片")
                if not modal_visible:
                    await self.wait_cover_modal_closed(page, modal)
                    kuaishou_logger.success("快手封面弹窗已关闭，封面应用完成")
                    return
                await page.wait_for_timeout(500)

            kuaishou_logger.warning(f"快手封面确认后弹窗未关闭，重试确认 {attempt}/3")

        raise RuntimeError("快手封面确认后未检测到应用成功")

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)

    async def set_schedule_time(self, page, publish_date):
        kuaishou_logger.info("click schedule")
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M:%S")
        await page.locator("label:text('发布时间')").locator('xpath=following-sibling::div').locator(
            '.ant-radio-input').nth(1).click()
        await asyncio.sleep(1)

        await page.locator('div.ant-picker-input input[placeholder="选择日期时间"]').click()
        await asyncio.sleep(1)

        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)
