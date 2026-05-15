# -*- coding: utf-8 -*-
from datetime import datetime

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
from utils.log import xiaohongshu_logger, XIAOHONGSHU_SCREENSHOT_DIR
from utils.publish_limits import normalize_publish_tags


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.xiaohongshu.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.xiaohongshu.com/creator-micro/content/upload", timeout=5000)
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


async def xiaohongshu_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        xiaohongshu_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await xiaohongshu_cookie_gen(account_file)
    return True


async def xiaohongshu_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {
            'headless': False
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
        await page.goto("https://creator.xiaohongshu.com/")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


class XiaoHongShuVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, thumbnail_path=None, thumbnail_paths=None, dry_run=False, dry_run_hold_browser=True):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = normalize_publish_tags(tags)
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path
        self.thumbnail_paths = thumbnail_paths or {}
        self.dry_run = dry_run
        self.dry_run_hold_browser = dry_run_hold_browser

    async def set_schedule_time_xiaohongshu(self, page, publish_date):
        target_time = publish_date.strftime("%Y-%m-%d %H:%M")
        xiaohongshu_logger.info(f"  [-] 正在设置小红书定时发布时间: {target_time}")

        wrapper = page.locator(".post-time-wrapper").first
        await wrapper.wait_for(state="visible", timeout=10000)
        await wrapper.scroll_into_view_if_needed()
        await page.wait_for_timeout(300)

        switch_checked = wrapper.locator(".d-switch-simulator.checked, input[type='checkbox']:checked").first
        if not await switch_checked.count():
            switcher = wrapper.locator(".d-switch").first
            await switcher.click(force=True, timeout=5000)
            await page.wait_for_timeout(800)

        date_input = wrapper.locator(".d-datepicker input.d-text").first
        await date_input.wait_for(state="visible", timeout=8000)
        await date_input.click(force=True, timeout=5000)
        await date_input.fill(target_time)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(700)

        actual_time = (await date_input.input_value()).strip()
        if actual_time != target_time:
            await date_input.click(force=True, timeout=5000)
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.type(target_time, delay=15)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1000)
            actual_time = (await date_input.input_value()).strip()

        if actual_time != target_time:
            body_excerpt = (await page.locator("body").inner_text())[-500:]
            raise RuntimeError(
                f"小红书定时发布时间写入校验失败，目标={target_time}，实际={actual_time}，页面尾部={body_excerpt}"
            )

        if not await wrapper.locator(".d-switch-simulator.checked, input[type='checkbox']:checked").count():
            raise RuntimeError("小红书定时发布开关未保持开启")

        xiaohongshu_logger.info(f"小红书定时发布时间已确认: {actual_time}")

    async def handle_upload_error(self, page):
        xiaohongshu_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

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
        # 访问指定的 URL
        await goto_and_reveal(
            page,
            "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video",
            wait_until="commit",
            timeout=90000,
        )
        xiaohongshu_logger.info("[+] 小红书发布页已打开，先刷新一次再开始上传")
        await page.reload(wait_until="commit", timeout=90000)
        await page.wait_for_timeout(1000)
        xiaohongshu_logger.info(f'[+]正在上传-------{self.title}.mp4')

        # 点击 "上传视频" 按钮
        upload_input = page.locator("div[class^='upload-content'] input[class='upload-input']").first
        await upload_input.wait_for(state="attached", timeout=90000)
        await upload_input.set_input_files(self.file_path)

        await self.wait_upload_ready(page)

        await self.set_thumbnail(page, self.thumbnail_path, self.thumbnail_paths)
        await asyncio.sleep(3)

        xiaohongshu_logger.info(f'  [-] 正在填充作品简介和话题...')
        await self.clear_platform_title(page)
        await self.fill_description(page)
        await self.fill_topics(page)

        if self.publish_date != 0:
            await self.set_schedule_time_xiaohongshu(page, self.publish_date)

        if self.dry_run:
            if managed_browser:
                await keep_browser_open_for_dry_run(
                    page,
                    context,
                    browser,
                    account_file=self.account_file,
                    logger=xiaohongshu_logger,
                    platform_name="小红书",
                    block_until_close=self.dry_run_hold_browser,
                )
            return

        # 判断视频是否发布成功
        while True:
            try:
                # 等待包含"定时发布"文本的button元素出现并点击
                if self.publish_date != 0:
                    await page.locator('button:has-text("定时发布")').click()
                else:
                    await page.locator('button:has-text("发布")').click()
                await page.wait_for_url(
                    "https://creator.xiaohongshu.com/publish/success?**",
                    timeout=3000
                )  # 如果自动跳转到作品页面，则代表发布成功
                xiaohongshu_logger.success("  [-]视频发布成功")
                break
            except:
                xiaohongshu_logger.info("  [-] 视频正在发布中...")
                screenshot_path = os.path.join(XIAOHONGSHU_SCREENSHOT_DIR, f"xiaohongshu_{int(asyncio.get_event_loop().time()*1000)}.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                await asyncio.sleep(0.5)

        await context.storage_state(path=self.account_file)  # 保存cookie
        xiaohongshu_logger.success('  [-]cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        if managed_browser:
            await context.close()
            await browser.close()

    async def wait_upload_ready(self, page: Page):
        started_at = asyncio.get_running_loop().time()
        max_wait_seconds = 8 * 60
        while True:
            if asyncio.get_running_loop().time() - started_at > max_wait_seconds:
                raise RuntimeError("小红书视频上传等待超时：未检测到上传成功或可编辑表单")

            if await page.locator('text=上传失败').count():
                raise RuntimeError("小红书视频上传失败")

            uploading_visible = False
            uploading = page.locator('text=上传中')
            for index in range(await uploading.count()):
                try:
                    if await uploading.nth(index).is_visible():
                        uploading_visible = True
                        break
                except Exception:
                    continue

            success_markers = [
                page.locator('text=上传成功').first,
                page.locator('div.preview-new:has-text("上传成功")').first,
                page.locator('input.d-text[placeholder*="标题"]').first,
                page.locator('.notranslate').first,
                page.locator('div:has-text("设置封面")').first,
                page.locator('button:has-text("发布")').first,
            ]
            for marker in success_markers:
                try:
                    if await marker.count() and await marker.is_visible():
                        if not uploading_visible:
                            xiaohongshu_logger.info("[+] 小红书上传已进入可编辑状态")
                            return
                except Exception:
                    continue

            xiaohongshu_logger.info("  [-] 小红书视频仍在上传或页面未就绪...")
            await asyncio.sleep(1)

    async def set_thumbnail(self, page: Page, thumbnail_path: str, thumbnail_paths=None):
        if thumbnail_path or thumbnail_paths:
            if await self.set_thumbnail_from_cover_editor(page, thumbnail_path, thumbnail_paths):
                return

            fallback_thumbnail_path = thumbnail_path
            if not fallback_thumbnail_path and isinstance(thumbnail_paths, dict):
                fallback_thumbnail_path = thumbnail_paths.get("3:4") or thumbnail_paths.get("4:3") or next(
                    (path for path in thumbnail_paths.values() if path),
                    None,
                )
            if not fallback_thumbnail_path:
                xiaohongshu_logger.warning("小红书封面未找到可用图片路径，跳过封面设置")
                return

            image_input = page.locator(
                'input[type="file"][accept*="image"], '
                'input[type="file"][accept*=".png"], '
                'input[type="file"][accept*=".jpg"], '
                'input[type="file"][accept*=".jpeg"]'
            ).first
            if await image_input.count():
                await image_input.set_input_files(fallback_thumbnail_path)
                xiaohongshu_logger.info(f"小红书封面文件已通过图片 input 设置: {fallback_thumbnail_path}")
                await page.wait_for_timeout(1500)
                return

            upload_buttons = [
                'button:has-text("上传图片")',
                'button:has-text("上传封面")',
                'div:has-text("上传图片")',
                'div:has-text("上传封面")',
                'div:has-text("本地上传")',
            ]
            for selector in upload_buttons:
                button = page.locator(selector).first
                try:
                    if not await button.count() or not await button.is_visible():
                        continue
                    async with page.expect_file_chooser(timeout=5000) as fc_info:
                        await button.click(timeout=3000)
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(fallback_thumbnail_path)
                    xiaohongshu_logger.info(f"小红书封面文件已通过上传按钮设置: {fallback_thumbnail_path}")
                    await page.wait_for_timeout(1500)
                    return
                except Exception as e:
                    xiaohongshu_logger.debug(f"小红书封面上传入口尝试失败 {selector}: {e}")

            raise RuntimeError("小红书封面设置失败：未能打开封面编辑器或上传本地封面")

    async def set_thumbnail_from_cover_editor(self, page: Page, thumbnail_path: str, thumbnail_paths=None):
        cover_card = await self.find_xhs_cover_card(page)
        if cover_card is None:
            xiaohongshu_logger.debug("小红书当前封面卡片未出现，跳过封面编辑入口")
            return False

        for _ in range(60):
            try:
                text = (await cover_card.inner_text(timeout=1000)).replace("\xa0", " ")
                if "上传中" not in text:
                    break
            except Exception:
                pass
            await page.wait_for_timeout(1000)

        if not await self.open_xhs_cover_editor(page, cover_card):
            xiaohongshu_logger.debug("小红书封面编辑弹窗未打开")
            return False

        try:
            await page.get_by_text("上传图片", exact=True).last.wait_for(state="visible", timeout=8000)
        except Exception as e:
            xiaohongshu_logger.debug(f"小红书封面编辑弹窗未出现: {e}")
            return False

        thumbnail_path = await self.choose_xhs_cover_path_for_editor(page, thumbnail_path, thumbnail_paths)
        if not thumbnail_path:
            xiaohongshu_logger.warning("小红书封面未找到可用图片路径，跳过封面设置")
            return False

        image_input = page.locator('input[type="file"][accept*="image"]').last
        try:
            await image_input.wait_for(state="attached", timeout=5000)
            await image_input.set_input_files(thumbnail_path)
            xiaohongshu_logger.info(f"小红书封面图片已上传到封面编辑器: {thumbnail_path}")
        except Exception as e:
            xiaohongshu_logger.debug(f"小红书封面编辑器图片 input 设置失败: {e}")
            return False

        confirm = page.get_by_text("确定", exact=True).last
        try:
            await page.wait_for_timeout(1200)
            await confirm.click(force=True, timeout=5000)
            await page.get_by_text("上传图片", exact=True).last.wait_for(state="hidden", timeout=15000)
            xiaohongshu_logger.info("小红书封面编辑器已确认")
            return True
        except Exception as e:
            xiaohongshu_logger.debug(f"小红书封面编辑器确认失败: {e}")
            return False

    async def find_xhs_cover_card(self, page: Page):
        candidates = [
            ".cover-plugin-preview .default.row",
            ".cover-plugin-preview .cover",
            ".cover-plugin-preview [class*='cover']",
        ]
        for selector in candidates:
            cards = page.locator(selector)
            for index in range(await cards.count()):
                card = cards.nth(index)
                try:
                    if await card.is_visible():
                        return card
                except Exception:
                    continue
        return None

    async def open_xhs_cover_editor(self, page: Page, cover_card):
        for attempt in range(3):
            try:
                await cover_card.scroll_into_view_if_needed()
                await cover_card.hover(timeout=3000)
                await page.wait_for_timeout(500 + attempt * 300)

                modify_text = page.get_by_text("修改封面", exact=True).first
                if await modify_text.count():
                    try:
                        await modify_text.click(force=True, timeout=2000)
                    except Exception:
                        await modify_text.evaluate("el => el.click()")
                else:
                    box = await cover_card.bounding_box()
                    if not box:
                        continue
                    await cover_card.click(
                        position={"x": min(max(box["width"] / 2, 12), box["width"] - 12), "y": min(max(box["height"] / 2, 12), box["height"] - 12)},
                        force=True,
                        timeout=3000,
                    )

                await page.get_by_text("上传图片", exact=True).last.wait_for(state="visible", timeout=8000)
                return True
            except Exception as e:
                xiaohongshu_logger.debug(f"小红书封面编辑入口第{attempt + 1}次打开失败: {e}")
                await page.wait_for_timeout(700)
        return False

    async def choose_xhs_cover_path_for_editor(self, page: Page, fallback_path: str, thumbnail_paths=None):
        paths = {
            str(ratio): path
            for ratio, path in (thumbnail_paths or {}).items()
            if ratio in {"3:4", "4:3"} and path
        }
        if not paths:
            return fallback_path

        desired_ratio = "3:4" if paths.get("3:4") else "4:3"
        current_ratio = await self.read_xhs_cover_editor_ratio(page)
        selected_ratio = current_ratio

        if desired_ratio and current_ratio != desired_ratio:
            selected_ratio = await self.select_xhs_cover_editor_ratio(page, desired_ratio)

        if selected_ratio not in paths:
            current_ratio = await self.read_xhs_cover_editor_ratio(page)
            selected_ratio = current_ratio if current_ratio in paths else desired_ratio

        selected_path = paths.get(selected_ratio) or paths.get(desired_ratio) or fallback_path
        xiaohongshu_logger.info(f"小红书封面比例={selected_ratio or '未知'}，上传对应封面: {selected_path}")
        return selected_path

    async def read_xhs_cover_editor_ratio(self, page: Page):
        ratio_text = page.locator(".cover-modal .ratio-text").first
        try:
            await ratio_text.wait_for(state="visible", timeout=3000)
            ratio = (await ratio_text.inner_text()).strip()
            return ratio if ratio in {"3:4", "4:3"} else None
        except Exception as e:
            xiaohongshu_logger.debug(f"小红书封面比例读取失败: {e}")
            return None

    async def select_xhs_cover_editor_ratio(self, page: Page, ratio: str):
        if ratio not in {"3:4", "4:3"}:
            return await self.read_xhs_cover_editor_ratio(page)

        try:
            await page.locator(".cover-modal .ratio-select").first.click(force=True, timeout=3000)
        except Exception as e:
            xiaohongshu_logger.warning(f"小红书封面比例下拉未定位到，保留当前比例上传: {ratio}")
            return await self.read_xhs_cover_editor_ratio(page)

        await page.wait_for_timeout(300)
        option_selector = ".ratio-select-menu .ratio-item.ratio-3-4" if ratio == "3:4" else ".ratio-select-menu .ratio-item.ratio-4-3"
        try:
            await page.locator(option_selector).last.click(force=True, timeout=3000)
        except Exception as e:
            xiaohongshu_logger.warning(f"小红书封面比例 {ratio} 选项未点击成功，保留当前比例")
            return await self.read_xhs_cover_editor_ratio(page)

        await page.wait_for_timeout(500)
        current = await self.read_xhs_cover_editor_ratio(page)
        xiaohongshu_logger.info(f"小红书封面比例已确认: {current or ratio}")
        return current or ratio

    async def clear_platform_title(self, page: Page):
        title_input = page.locator('input.d-text[placeholder*="标题"]').first
        try:
            if await title_input.count():
                await title_input.fill("")
                xiaohongshu_logger.info("小红书独立标题已留空，统一使用作品简介承载标题和话题")
        except Exception as e:
            xiaohongshu_logger.warning(f"小红书独立标题清空失败，继续填写作品简介: {e}")

    async def fill_description(self, page: Page):
        title = (self.title or "").strip()
        if not title:
            return

        editor = page.locator(".tiptap.ProseMirror").first
        await editor.wait_for(state="visible", timeout=8000)
        await editor.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
        await page.keyboard.insert_text(title)
        xiaohongshu_logger.info("小红书作品简介已写入标题内容")

    async def fill_topics(self, page: Page):
        if not self.tags:
            return

        topic_parts = [
            f"#{str(tag).strip().lstrip('#')}"
            for tag in self.tags
            if str(tag).strip().lstrip("#")
        ]
        if not topic_parts:
            return

        editor = page.locator(".tiptap.ProseMirror").first
        await editor.wait_for(state="visible", timeout=8000)
        await editor.click()
        existing_text = (await editor.inner_text()).replace("\xa0", " ").strip()

        if existing_text:
            await page.keyboard.insert_text(" ")
            await page.wait_for_timeout(120)

        async def get_topic_node_texts():
            nodes = editor.locator("a.tiptap-topic")
            texts = []
            for index in range(await nodes.count()):
                raw_text = await nodes.nth(index).inner_text()
                texts.append("".join(raw_text.replace("\xa0", " ").split()))
            return texts

        async def click_exact_topic_candidate(tag_name: str) -> bool:
            expected = f"#{tag_name}"
            candidates = page.locator(".tippy-box .items .item")
            for index in range(await candidates.count()):
                item = candidates.nth(index)
                try:
                    if not await item.is_visible():
                        continue
                    name = (await item.locator(".name").first.inner_text(timeout=1000)).strip()
                    if name == expected:
                        await item.click(force=True, timeout=3000)
                        await page.wait_for_timeout(900)
                        return True
                except Exception:
                    continue
            return False

        # 小红书需要尽量模拟人工键盘节奏：先用键盘组合输入 "#"，等待编辑器进入话题模式，
        # 再逐字输入标签并按空格确认。普通文本 "#话题" 不算成功。
        for topic in topic_parts:
            tag_name = topic.lstrip("#")
            expected_node_text = f"#{tag_name}[话题]#"
            accepted = False

            for attempt, wait_ms in enumerate((1800, 2200, 2800), start=1):
                before_nodes = await get_topic_node_texts()
                await editor.click(force=True, timeout=3000)
                await page.keyboard.press("End")
                await page.keyboard.press("Space")
                await page.wait_for_timeout(200)
                await page.keyboard.press("Shift+Digit3")
                await page.wait_for_timeout(800)
                await page.keyboard.type(tag_name, delay=110)
                await page.wait_for_timeout(wait_ms)
                if not await click_exact_topic_candidate(tag_name):
                    await page.keyboard.press("Space")
                    await page.wait_for_timeout(900)

                after_nodes = await get_topic_node_texts()
                new_nodes = after_nodes[len(before_nodes):]
                if new_nodes and new_nodes[-1] == expected_node_text:
                    accepted = True
                    break

                actual = new_nodes[-1] if new_nodes else "未生成话题节点"
                xiaohongshu_logger.warning(
                    f"小红书话题验收失败，撤销后重试: 期望={expected_node_text}，实际={actual}，第{attempt}次等待={wait_ms}ms"
                )
                await page.keyboard.press("Control+Z")
                await page.wait_for_timeout(700)

            if not accepted:
                editor_text = (await editor.inner_text()).replace("\xa0", " ").strip()
                topic_nodes = await get_topic_node_texts()
                raise RuntimeError(
                    f"小红书话题节点生成失败，缺失：{topic}，当前内容：{editor_text[:120]}，节点={topic_nodes}"
                )

        editor_text = (await editor.inner_text()).replace("\xa0", " ").strip()
        topic_nodes = await get_topic_node_texts()
        expected_node_texts = {
            f"#{str(tag).strip().lstrip('#')}[话题]#"
            for tag in self.tags
            if str(tag).strip().lstrip("#")
        }
        wrong_nodes = [
            node for node in topic_nodes
            if node not in expected_node_texts
        ]
        missing = [
            tag for tag in self.tags
            if f"#{str(tag).strip().lstrip('#')}" not in editor_text
        ]

        if wrong_nodes or missing:
            raise RuntimeError(
                f"小红书话题节点写入校验失败，错误节点={wrong_nodes}，缺失={missing}，当前内容={editor_text[:120]}，节点={topic_nodes}"
            )

        xiaohongshu_logger.info(f"小红书话题已按原文生成节点: {' '.join(topic_parts)}")

    async def set_location(self, page: Page, location: str = "青岛市"):
        print(f"开始设置位置: {location}")
        
        # 点击地点输入框
        print("等待地点输入框加载...")
        loc_ele = await page.wait_for_selector('div.d-text.d-select-placeholder.d-text-ellipsis.d-text-nowrap')
        print(f"已定位到地点输入框: {loc_ele}")
        await loc_ele.click()
        print("点击地点输入框完成")
        
        # 输入位置名称
        print(f"等待1秒后输入位置名称: {location}")
        await page.wait_for_timeout(1000)
        await page.keyboard.type(location)
        print(f"位置名称输入完成: {location}")
        
        # 等待下拉列表加载
        print("等待下拉列表加载...")
        dropdown_selector = 'div.d-popover.d-popover-default.d-dropdown.--size-min-width-large'
        await page.wait_for_timeout(3000)
        try:
            await page.wait_for_selector(dropdown_selector, timeout=3000)
            print("下拉列表已加载")
        except:
            print("下拉列表未按预期显示，可能结构已变化")
        
        # 增加等待时间以确保内容加载完成
        print("额外等待1秒确保内容渲染完成...")
        await page.wait_for_timeout(1000)
        
        # 尝试更灵活的XPath选择器
        print("尝试使用更灵活的XPath选择器...")
        flexible_xpath = (
            f'//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
            f'//div[contains(@class, "d-options-wrapper")]'
            f'//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
            f'//div[contains(@class, "name") and text()="{location}"]'
        )
        await page.wait_for_timeout(3000)
        
        # 尝试定位元素
        print(f"尝试定位包含'{location}'的选项...")
        try:
            # 先尝试使用更灵活的选择器
            location_option = await page.wait_for_selector(
                flexible_xpath,
                timeout=3000
            )
            
            if location_option:
                print(f"使用灵活选择器定位成功: {location_option}")
            else:
                # 如果灵活选择器失败，再尝试原选择器
                print("灵活选择器未找到元素，尝试原始选择器...")
                location_option = await page.wait_for_selector(
                    f'//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
                    f'//div[contains(@class, "d-options-wrapper")]'
                    f'//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
                    f'/div[1]//div[contains(@class, "name") and text()="{location}"]',
                    timeout=2000
                )
            
            # 滚动到元素并点击
            print("滚动到目标选项...")
            await location_option.scroll_into_view_if_needed()
            print("元素已滚动到视图内")
            
            # 增加元素可见性检查
            is_visible = await location_option.is_visible()
            print(f"目标选项是否可见: {is_visible}")
            
            # 点击元素
            print("准备点击目标选项...")
            await location_option.click()
            print(f"成功选择位置: {location}")
            return True
            
        except Exception as e:
            print(f"定位位置失败: {e}")
            
            # 打印更多调试信息
            print("尝试获取下拉列表中的所有选项...")
            try:
                all_options = await page.query_selector_all(
                    '//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
                    '//div[contains(@class, "d-options-wrapper")]'
                    '//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
                    '/div'
                )
                print(f"找到 {len(all_options)} 个选项")
                
                # 打印前3个选项的文本内容
                for i, option in enumerate(all_options[:3]):
                    option_text = await option.inner_text()
                    print(f"选项 {i+1}: {option_text.strip()[:50]}...")
                    
            except Exception as e:
                print(f"获取选项列表失败: {e}")
                
            # 截图保存（取消注释使用）
            # await page.screenshot(path=f"location_error_{location}.png")
            return False

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


