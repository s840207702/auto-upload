import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
import time

from playwright.async_api import Error as PlaywrightError, Playwright, TimeoutError as PlaywrightTimeoutError

from conf import LOCAL_CHROME_PATH
from utils.base_social_media import (
    set_init_script,
    launch_publish_browser,
    new_publish_context,
    goto_and_reveal,
    prevent_new_tabs,
    keep_browser_open_for_dry_run,
)
from utils.log import bilibili_logger
from utils.publish_limits import normalize_publish_tags


OPEN_DEBUG_BROWSERS: list = []


class BilibiliVideo:
    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list[str],
        publish_date: datetime | int,
        account_file: Path,
        thumbnail_path: str | None = None,
        thumbnail_paths: dict[str, str] | None = None,
        desc: str | None = None,
        bili_type: str | None = None,
        partition: str | None = None,
        dry_run: bool = False,
        dry_run_hold_browser: bool = True,
    ) -> None:
        self.title = title
        self.file_path = file_path
        self.tags = normalize_publish_tags(tags)
        self.publish_date = publish_date
        self.account_file = account_file
        self.thumbnail_path = thumbnail_path
        self.thumbnail_paths = {
            str(ratio): str(path)
            for ratio, path in (thumbnail_paths or {}).items()
            if path
        }
        self.local_executable_path = LOCAL_CHROME_PATH
        self.desc = desc or ""
        self.bili_type = (bili_type or "自制").strip()
        self.partition = (partition or "").strip()
        self.dry_run = dry_run
        self.dry_run_hold_browser = dry_run_hold_browser

    async def _fill_title(self, page) -> None:
        started_at = time.perf_counter()
        # 基于实际B站页面的选择器（探测结果：placeholder="请输入稿件标题"）
        candidates = [
            'input[placeholder="请输入稿件标题"]',  # 精确匹配
            'input[placeholder*="标题"]',  # 回退
        ]
        for selector in candidates:
            try:
                locator = page.locator(selector).first
                if await locator.count():
                    try:
                        await locator.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await locator.fill(self.title[:80])
                    bilibili_logger.info(f"[bilibili] 标题已填写，耗时 {time.perf_counter() - started_at:.1f} 秒: {self.title[:80]}")
                    return
                bilibili_logger.warning(f"[bilibili] 未能找到标题输入框: {selector}")
            except Exception:
                continue
        raise RuntimeError("B站标题输入框未找到")

    async def _fill_tags(self, page) -> None:
        if not self.tags:
            return
        started_at = time.perf_counter()
        # 基于实际B站页面的选择器（探测结果：placeholder="按回车键Enter创建标签"）
        candidates = [
            'input[placeholder*="按回车键Enter创建标签"]',  # 精确匹配
            'input[placeholder*="标签"]',  # 回退
        ]
        for selector in candidates:
            try:
                locator = page.locator(selector).first
                if await locator.count():
                    try:
                        await locator.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    try:
                        await locator.click(force=True, timeout=3000)
                        await locator.fill("")
                        await self._clear_existing_tags(page, locator)
                        bilibili_logger.info("[bilibili] 已清空标签输入框和页面默认标签")
                    except Exception as e:
                        bilibili_logger.warning(f"[bilibili] 清空标签失败: {e}")
                    for tag in self.tags:
                        tag = str(tag).strip().lstrip("#")
                        if not tag:
                            continue
                        await locator.fill(tag)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(120)
                        bilibili_logger.info(f"[bilibili] 标签已填写: {tag}")
                    bilibili_logger.info(f"[bilibili] 标签填写完成，耗时 {time.perf_counter() - started_at:.1f} 秒")
                    return
                bilibili_logger.warning(f"[bilibili] 未能找到标签输入框: {selector}")
            except Exception:
                continue
        raise RuntimeError("B站标签输入框未找到")

    async def _clear_existing_tags(self, page, input_locator) -> None:
        """B站会自动带出推荐标签；发布时只保留用户传入的预设标签。"""
        try:
            before_text = await page.evaluate(
                """(input) => {
                    const root = input.closest('.form-item') || input.parentElement;
                    return root ? (root.innerText || '') : '';
                }""",
                await input_locator.element_handle(),
            )
        except Exception:
            before_text = ""

        # 优先点已选标签 chip 自带的关闭按钮；范围限定在顶部已选标签容器，避免误触推荐标签/话题。
        try:
            clicked = await page.evaluate(
                """(input) => {
                    const root = input.closest('.form-item') || input.parentElement;
                    if (!root) return 0;
                    const selectedWrap = root.querySelector('.tag-pre-wrp') || root.querySelector('.input-container');
                    if (!selectedWrap) return 0;
                    let count = 0;
                    const candidates = Array.from(selectedWrap.querySelectorAll(
                        '.label-item-v2-container svg, .label-item-v2-container [class*="close"], .label-item-v2-container [class*="delete"], .label-item-v2-container [class*="remove"]'
                    ));
                    for (const el of candidates) {
                        const rect = el.getBoundingClientRect();
                        const text = (el.innerText || el.textContent || '').trim();
                        if (rect.width > 0 && rect.width <= 28 && rect.height > 0 && rect.height <= 28 && !text) {
                            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                            count += 1;
                        }
                    }
                    return count;
                }""",
                await input_locator.element_handle(),
            )
            if clicked:
                bilibili_logger.info(f"[bilibili] 已点击默认标签关闭按钮: {clicked} 个")
                await page.wait_for_timeout(300)
        except Exception as e:
            bilibili_logger.debug(f"[bilibili] 标签关闭按钮清理跳过: {e}")

        # 再用空输入框 Backspace 兜底删除 chip。
        try:
            await input_locator.click(force=True, timeout=2000)
            await input_locator.fill("")
            for _ in range(12):
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(60)
        except Exception as e:
            bilibili_logger.debug(f"[bilibili] 标签 Backspace 清理跳过: {e}")

        try:
            after_text = await page.evaluate(
                """(input) => {
                    const root = input.closest('.form-item') || input.parentElement;
                    return root ? (root.innerText || '') : '';
                }""",
                await input_locator.element_handle(),
            )
            if before_text != after_text:
                bilibili_logger.info("[bilibili] 页面默认标签已尝试清理")
        except Exception:
            pass

    async def _fill_desc(self, page) -> None:
        if not self.desc:
            return
        
        bilibili_logger.info(f"[bilibili] 正在填写简介: {self.desc[:50]}...")
        
        # 基于实际B站页面的Quill编辑器结构
        desc_selectors = [
            '.ql-editor[contenteditable="true"]',  # 精确匹配Quill编辑器
            '.ql-editor',  # Quill富文本编辑器
            '[contenteditable="true"][data-placeholder*="简介"]',  # 有简介placeholder的可编辑元素
            '[contenteditable="true"]',  # 通用可编辑div
        ]
        
        for selector in desc_selectors:
            try:
                if await page.locator(selector).first.count():
                    bilibili_logger.info(f"[bilibili] 找到简介输入框: {selector}")
                    
                    # 滚动到元素可见位置
                    try:
                        await page.locator(selector).first.scroll_into_view_if_needed()
                        bilibili_logger.info(f"[bilibili] 简介输入框已滚动到可见位置: {selector}")
                    except Exception:
                        pass
                    
                    # 输入内容
                    await page.locator(selector).first.fill(self.desc[:2000])
                    bilibili_logger.info(f"[bilibili] 简介已填写: {self.desc[:2000]}")
                    return

            except Exception as e:
                bilibili_logger.warning(f"[bilibili] 简介选择器 {selector} 失败: {e}")
                continue
        
        bilibili_logger.warning("[bilibili] 未能找到简介输入框")

    async def _set_type(self, page) -> None:
        # 基于实际B站页面的类型选择（自制/转载）
        if not self.bili_type:
            return
        
        try:
            bilibili_logger.info(f"[bilibili] 正在选择类型: {self.bili_type}")

            # 先限制在微应用容器内，避免命中弹窗/批量填充对话框中的同名项
            container = page.locator('#video-up-app').first

            if self.bili_type == "自制":
                # 更精确：仅点击类型单选的名称节点
                locator = container.locator('.check-radio-v2-name:has-text("自制")').first
                if not await locator.count() or not await locator.is_visible():
                    bilibili_logger.info("[bilibili] 未检测到旧版自制单选项，跳过类型选择")
                    return
                await locator.click(force=True, timeout=3000)
                bilibili_logger.info("[bilibili] 成功选择类型: 自制")
            elif self.bili_type == "转载":
                locator = container.locator('.check-radio-v2-name:has-text("转载")').first
                if not await locator.count() or not await locator.is_visible():
                    bilibili_logger.info("[bilibili] 未检测到旧版转载单选项，跳过类型选择")
                    return
                await locator.click(force=True, timeout=3000)
                bilibili_logger.info("[bilibili] 成功选择类型: 转载")
            else:
                bilibili_logger.warning(f"[bilibili] 未知的类型: {self.bili_type}，支持的类型: 自制, 转载")

        except Exception as e:
            bilibili_logger.warning(f"[bilibili] 类型选择失败: {e}")

    async def _set_creation_statement(self, page) -> None:
        """选择当前 B 站新版必填的“创作声明”。"""
        try:
            container = page.locator('#video-up-app').first
            statement = container.locator('.creation-statement-container').first
            if not await statement.count():
                bilibili_logger.info("[bilibili] 未检测到新版创作声明组件，跳过")
                return

            target_texts = ["内容无需标注"]
            if self.bili_type == "转载":
                target_texts = ["内容为转载"]

            before_text = ""
            try:
                before_text = (await statement.locator('input.bcc-select-input-inner').first.input_value()).strip()
            except Exception:
                pass
            if any(text in before_text for text in target_texts):
                bilibili_logger.info(f"[bilibili] 创作声明已是目标值: {before_text}")
                return

            opener = statement.locator('.bcc-select').first
            if not await opener.count():
                opener = statement.locator('input.bcc-select-input-inner').first
            if not await opener.count():
                bilibili_logger.warning("[bilibili] 未找到创作声明下拉框")
                return

            await opener.scroll_into_view_if_needed()
            await opener.click(force=True, timeout=3000)
            await page.wait_for_timeout(250)

            for text in target_texts:
                try:
                    option = statement.locator(f'li.bcc-option:has-text("{text}")').first
                    if not await option.count():
                        continue
                    await option.scroll_into_view_if_needed(timeout=3000)
                    await option.click(timeout=5000)
                    await page.wait_for_timeout(300)
                    after_text = (await statement.locator('input.bcc-select-input-inner').first.input_value()).strip()
                    if text in after_text:
                        bilibili_logger.info(f"[bilibili] 创作声明已选择并回读确认: {after_text}")
                        return
                    bilibili_logger.warning(f"[bilibili] 创作声明点击后未回读到目标值: target={text}, after={after_text}")
                except PlaywrightError:
                    continue

            bilibili_logger.warning("[bilibili] 未能选择创作声明选项")
        except Exception as e:
            bilibili_logger.warning(f"[bilibili] 创作声明选择失败: {e}")

    async def _set_partition(self, page) -> None:
        # 基于实际B站页面的分区选择
        if not self.partition:
            return
        
        try:
            bilibili_logger.info(f"[bilibili] 正在选择分区: {self.partition}")
            
            # 1. 点击下拉框展开选项（限定在微应用容器且定位到“分区”这一项）
            container = page.locator('#video-up-app').first
            partition_item = container.locator('.form-item:has(.section-title-content-main:has-text("分区"))').first
            if await partition_item.count():
                try:
                    current_text = await partition_item.inner_text()
                    if self.partition and self.partition in current_text:
                        bilibili_logger.info(f"[bilibili] 分区已是目标值: {self.partition}")
                        return
                except Exception:
                    pass

            opener_candidates = [
                (partition_item, '.select-controller'),
                (partition_item, '.bcc-select'),
                (container, '.setting-item:has-text("分区") .select-controller'),
                (container, '.select-area:has-text("分区") .select-controller'),
            ]
            clicked = False
            for scope, oc in opener_candidates:
                try:
                    if not await scope.count():
                        continue
                    locator = scope.locator(oc).first
                    if await locator.count() and await locator.is_visible():
                        await locator.scroll_into_view_if_needed()
                        await locator.click(force=True, timeout=3000)
                        bilibili_logger.info(f"[bilibili] 分区下拉框已点击: {oc}")
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                bilibili_logger.warning("[bilibili] 未找到分区下拉触发器")
                return
            
            # 等待下拉菜单展开
            await page.wait_for_timeout(500)
            
            # 2. 选择指定的分区选项
            # 使用多种选择器尝试匹配分区
            partition_selectors = [
                f'.drop-list-v2-item:has-text("{self.partition}")',
                f'.drop-list-v2-item-cont:has-text("{self.partition}")',
                f'p.item-cont-main:has-text("{self.partition}")',
                f'div.select-dropdown >> text={self.partition}',  # 精确匹配，在当前下拉菜单中
                f'.select-dropdown .select-item-cont:has-text("{self.partition}")',
                f'.select-item-cont:has-text("{self.partition}")',  # 回退
                f'text={self.partition}',  # 最后回退
            ]
            
            option_selected = False
            for selector in partition_selectors:
                try:
                    locator = page.locator(selector).first
                    if await locator.count():
                        bilibili_logger.info(f"[bilibili] 找到分区选项: {selector}")
                        try:
                            await locator.scroll_into_view_if_needed(timeout=1500)
                        except Exception:
                            pass
                        await locator.click(force=True, timeout=3000)
                        option_selected = True
                        bilibili_logger.info(f"[bilibili] 成功选择分区: {self.partition}")
                        break
                except Exception as e:
                    bilibili_logger.warning(f"[bilibili] 分区选项 {selector} 点击失败: {e}")
                    continue
            
            if not option_selected:
                try:
                    await page.evaluate(
                        """() => {
                            const items = Array.from(document.querySelectorAll('#video-up-app .form-item'));
                            const item = items.find((el) => (el.innerText || '').includes('分区'));
                            const opener = item && item.querySelector('.select-controller, .bcc-select');
                            if (opener) {
                                opener.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                            }
                        }"""
                    )
                    await page.wait_for_timeout(300)
                    clicked_text = await page.evaluate(
                        """(target) => {
                            const items = Array.from(document.querySelectorAll('.drop-list-v2-item, .drop-list-v2-item-cont, .select-item-cont'));
                            const item = items.find((el) => (el.innerText || el.textContent || '').trim().includes(target));
                            if (!item) return '';
                            item.scrollIntoView({ block: 'center', inline: 'nearest' });
                            item.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                            return (item.innerText || item.textContent || '').trim();
                        }""",
                        self.partition,
                    )
                    if clicked_text:
                        option_selected = True
                        bilibili_logger.info(f"[bilibili] 成功选择分区(JS兜底): {clicked_text}")
                except Exception as e:
                    bilibili_logger.debug(f"[bilibili] JS 兜底选择分区失败: {e}")

            if not option_selected:
                bilibili_logger.warning(f"[bilibili] 未能找到分区选项: {self.partition}")
                # 尝试点击页面其他位置关闭下拉菜单
                try:
                    await page.click('body', timeout=1000)
                except Exception:
                    pass
            
        except Exception as e:
            bilibili_logger.warning(f"[bilibili] 分区选择失败: {e}")

    async def _set_schedule(self, page) -> None:
        # 仅当提供了具体发布时间才尝试
        if not self.publish_date or self.publish_date == 0:
            return

        try:
            bilibili_logger.info("[bilibili] 开始设置定时发布")

            ts = self._parse_publish_datetime()
            if ts is None:
                return
            ts = self._round_bilibili_time(ts)
            date_str = ts.strftime('%Y-%m-%d')
            time_str = ts.strftime('%H:%M')

            bilibili_logger.info(f"[bilibili] 设置发布时间: {date_str} {time_str}")

            await self._enable_bilibili_schedule_switch(page)
            await self._set_bilibili_schedule_date(page, ts)
            await self._set_bilibili_schedule_time(page, ts)
            await self._assert_bilibili_schedule(page, date_str, time_str)

            bilibili_logger.info("[bilibili] 定时发布设置完成")

        except Exception as e:
            raise RuntimeError(f"B站定时发布设置失败: {e}") from e

    def _parse_publish_datetime(self) -> datetime | None:
        if isinstance(self.publish_date, str):
            try:
                return datetime.strptime(self.publish_date, '%Y-%m-%d %H:%M')
            except Exception:
                bilibili_logger.warning(f"[bilibili] 时间格式解析失败: {self.publish_date}")
                return None
        if isinstance(self.publish_date, datetime):
            return self.publish_date
        if isinstance(self.publish_date, (int, float)):
            return datetime.fromtimestamp(self.publish_date)
        bilibili_logger.warning(f"[bilibili] 不支持的时间格式: {type(self.publish_date)}")
        return None

    def _round_bilibili_time(self, ts: datetime) -> datetime:
        # B站时间选择器分钟粒度为 5 分钟，随机分钟需要就近落到可选项。
        remainder = ts.minute % 5
        if remainder == 0:
            return ts.replace(second=0, microsecond=0)
        delta = 5 - remainder if remainder >= 3 else -remainder
        rounded = ts + timedelta(minutes=delta)
        rounded = rounded.replace(second=0, microsecond=0)
        bilibili_logger.info(
            f"[bilibili] 目标分钟 {ts.strftime('%H:%M')} 已按平台粒度就近调整为 {rounded.strftime('%H:%M')}"
        )
        return rounded

    async def _enable_bilibili_schedule_switch(self, page) -> None:
        switch = page.locator('.time-switch-wrp .switch-container').first
        await switch.wait_for(state='visible', timeout=10000)
        cls = await switch.get_attribute('class') or ''
        if 'active' not in cls:
            await switch.click(force=True, timeout=5000)
            await page.wait_for_timeout(500)
        cls = await switch.get_attribute('class') or ''
        if 'active' not in cls:
            raise RuntimeError("定时发布开关未成功打开")

    async def _set_bilibili_schedule_date(self, page, ts: datetime) -> None:
        await page.locator('.date-picker-date .date-show').first.click(force=True, timeout=5000)
        await page.wait_for_timeout(300)
        picker = page.locator('.date-picker-container').first
        await picker.wait_for(state='visible', timeout=5000)

        target_month = f"{ts.year}年{ts.month}月"
        title = picker.locator('.date-picker-nav-title').first
        for _ in range(3):
            current_month = (await title.inner_text()).strip()
            if current_month == target_month:
                break
            next_button = picker.locator('[class*="right"], [class*="next"], .bcc-icon-ic_next').first
            if not await next_button.count():
                raise RuntimeError(f"日期选择器当前为 {current_month}，未找到切换到 {target_month} 的按钮")
            await next_button.click(force=True, timeout=3000)
            await page.wait_for_timeout(300)

        day_items = picker.locator('.date-wrp .date-picker-body-item')
        for index in range(await day_items.count()):
            item = day_items.nth(index)
            text = (await item.inner_text()).strip()
            cls = await item.get_attribute('class') or ''
            if text == str(ts.day) and 'disabled' not in cls:
                await item.click(force=True, timeout=3000)
                await page.wait_for_timeout(300)
                return
        raise RuntimeError(f"未能在 B站日期选择器中选择 {ts.strftime('%Y-%m-%d')}")

    async def _set_bilibili_schedule_time(self, page, ts: datetime) -> None:
        await page.locator('.date-picker-timer .date-show').first.click(force=True, timeout=5000)
        await page.wait_for_timeout(300)
        await self._select_bilibili_time_value(page, 0, f"{ts.hour:02d}")
        await self._select_bilibili_time_value(page, 1, f"{ts.minute:02d}")
        await page.locator('#video-up-app').first.click(position={"x": 20, "y": 20}, force=True)
        await page.wait_for_timeout(300)

    async def _select_bilibili_time_value(self, page, column_index: int, value: str) -> None:
        panel = page.locator('.time-picker-container .time-picker-panel-select-wrp').nth(column_index)
        await panel.wait_for(state='visible', timeout=5000)
        items = panel.locator('.time-picker-panel-select-item')
        for index in range(await items.count()):
            item = items.nth(index)
            text = (await item.inner_text()).strip()
            cls = await item.get_attribute('class') or ''
            if text == value and 'disabled' not in cls:
                await item.scroll_into_view_if_needed(timeout=3000)
                await item.click(force=True, timeout=3000)
                await page.wait_for_timeout(200)
                return
        raise RuntimeError(f"B站时间选择器未找到可用选项 {value}")

    async def _assert_bilibili_schedule(self, page, date_str: str, time_str: str) -> None:
        container = page.locator('#video-up-app').first
        date_text = (await container.locator('.date-picker-date .date-show').first.inner_text()).strip()
        time_text = (await container.locator('.date-picker-timer .date-show').first.inner_text()).strip()
        bilibili_logger.info(f"[bilibili] 回读定时：date={date_text or '-'} time={time_text or '-'}  (目标: {date_str} {time_str})")
        if date_text != date_str or time_text != time_str:
            raise RuntimeError(f"定时回读不一致，目标 {date_str} {time_str}，当前 {date_text} {time_text}")

    async def _dismiss_unsubmitted_prompt(self, page) -> None:
        """轮询几次，如果存在“未提交的视频”提示则点击“不用了”。避免瞬时出现被错过。"""
        try:
            # 最长轮询 ~3 秒（10 次，每次 300ms）
            for _ in range(10):
                try:
                    tip = page.locator('.upload-wrp .entrance-tip').first
                    if await tip.count():
                        bilibili_logger.info('[bilibili] 检测到未提交视频提示，尝试关闭')
                        candidates = [
                            '.upload-wrp .entrance-tip .entrance-tip-btn[data-reporter-id="32"]',
                            '.upload-wrp .entrance-tip .entrance-tip-btn:has-text("不用了")',
                            'text=不用了',
                        ]
                        clicked = False
                        for sel in candidates:
                            try:
                                btn = page.locator(sel).first
                                if await btn.count():
                                    await btn.scroll_into_view_if_needed()
                                    await btn.click()
                                    bilibili_logger.info(f"[bilibili] 已点击‘不用了’: {sel}")
                                    clicked = True
                                    break
                            except Exception:
                                continue
                        if clicked:
                            # 给页面一点时间收起提示
                            await asyncio.sleep(0.3)
                            return
                except Exception:
                    pass
                await asyncio.sleep(0.3)
        except Exception as e:
            bilibili_logger.warning(f"[bilibili] 关闭未提交提示失败: {e}")

    async def _wait_upload_complete(self, page) -> None:
        bilibili_logger.info("[bilibili] 等待视频上传完成...")
        
        # 轮询检测上传完成状态（要求完成状态稳定出现多次，避免误判）
        success_stable_ticks = 0
        container = page.locator('#video-up-app').first
        
        for i in range(180):  # 最多轮询 ~3 分钟
            try:
                # 读取状态容器文本（若有）
                status_text = None
                try:
                    if await container.locator('.file-item-content-status-text').first.count():
                        status_text = (await container.locator('.file-item-content-status-text').first.inner_text() or '').strip()
                except Exception:
                    status_text = None

                # 1) 判断是否仍在上传中
                in_progress = False
                # 文案信号
                if status_text and any(key in status_text for key in ("上传中", "当前速度", "剩余时间")):
                    in_progress = True

                # 2) 判断是否上传完成（结合容器文本/图标/百分比）
                success_found = False
                # 图标/文本标识
                if await container.locator('.file-item-content-status-text .success:has-text("上传完成")').count():
                    success_found = True
                elif status_text and ("上传完成" in status_text):
                    success_found = True

                # 稳定判定：需非上传中且连续3次检测到完成
                bilibili_logger.info(f"[bilibili] success_found: {success_found}, in_progress: {in_progress}")
                if success_found and not in_progress:
                    success_stable_ticks += 1
                    if success_stable_ticks >= 3:
                        bilibili_logger.info("[bilibili] 上传完成状态稳定，继续后续流程")
                        return
                else:
                    success_stable_ticks = 0

                # 每3秒打印一次当前状态
                if i % 3 == 0:
                    if status_text:
                        bilibili_logger.info(f"[bilibili] 上传状态: {status_text}")
                    else:
                        # 回退打印部分结构存在性
                        exists = await container.locator('.upload-audit-progress').count()
                        bilibili_logger.info(f"[bilibili] 仍在等待上传完成... ({i}秒) progress_container={exists>0}")

            except Exception as e:
                bilibili_logger.warning(f"[bilibili] 检测上传状态时出错: {e}")
            
            await asyncio.sleep(1)
        
        bilibili_logger.warning("[bilibili] 上传完成检测超时（3分钟）")

    async def _click_publish(self, page) -> None:
        # 基于实际B站页面的发布按钮选择器
        bilibili_logger.info("[bilibili] 正在寻找发布按钮...")
        await prevent_new_tabs(page, logger=bilibili_logger, label="B站投稿")
        
        # 基于实际HTML结构，发布按钮是span元素
        publish_selectors = [
            'span.submit-add:has-text("立即投稿")',  # 精确匹配实际结构
        ]
        
        for selector in publish_selectors:
            try:
                if await page.locator(selector).count():
                    bilibili_logger.info(f"[bilibili] 找到发布按钮: {selector}")
                    await page.locator(selector).scroll_into_view_if_needed()
                    await page.locator(selector).click()
                    bilibili_logger.info(f"[bilibili] 成功点击发布按钮: {selector}")
                    return
            except Exception as e:
                bilibili_logger.warning(f"[bilibili] 发布按钮选择器失败 {selector}: {e}")
                continue
        
        raise RuntimeError("B站未找到立即投稿按钮")

    async def _wait_publish_result(self, page) -> bool:
        """等待发布结果，返回是否发布成功"""
        bilibili_logger.info("[bilibili] 等待发布结果...")
        
        # 轮询检测发布结果。发布按钮消失即可视为已提交，避免卡住后续平台。
        for i in range(20):
            try:
                # 1. 检测是否出现成功提示 - 基于实际HTML结构
                success_indicators = [
                    '.step-des:has-text("稿件投递成功")',  # 精确匹配实际成功页面
                    '.video-complete .step-des',  # 成功页面的容器
                    'text=稿件投递成功',  # 文本匹配
                ]
                
                for indicator in success_indicators:
                    if await page.locator(indicator).count():
                        bilibili_logger.info(f"[bilibili] 检测到发布成功标识: {indicator}")
                        return True
                
                # 2. 检测是否出现错误提示
                error_indicators = [
                    '.error-tip',
                    '.error-message',
                    '.upload-error',
                    'text=发布失败',
                    'text=投稿失败',
                    'text=上传失败',
                ]
                
                for indicator in error_indicators:
                    if await page.locator(indicator).count():
                        error_text = ""
                        try:
                            error_text = await page.locator(indicator).first.inner_text()
                        except Exception:
                            pass
                        bilibili_logger.error(f"[bilibili] 检测到发布失败标识: {indicator}, 错误信息: {error_text}")
                        return False
                
                # 3. 检测是否页面跳转（发布成功后通常会跳转）
                current_url = page.url
                if "upload" not in current_url and "member.bilibili.com" in current_url:
                    bilibili_logger.info(f"[bilibili] 页面已跳转，可能发布成功: {current_url}")
                    return True
                
                # 4. 检测发布按钮是否消失（表示已经提交到平台处理）
                publish_button_exists = False
                for selector in ['span.submit-add:has-text("立即投稿")', '.submit-add:has-text("立即投稿")']:
                    if await page.locator(selector).count():
                        publish_button_exists = True
                        break
                
                if not publish_button_exists:
                    bilibili_logger.info("[bilibili] 发布按钮已消失，视为投稿已提交")
                    return True
                
                if i % 5 == 0:
                    bilibili_logger.info(f"[bilibili] 仍在等待发布结果... ({i}秒)")
                
            except Exception as e:
                bilibili_logger.warning(f"[bilibili] 检测发布结果时出错: {e}")
            
            await asyncio.sleep(1)
        
        bilibili_logger.warning("[bilibili] 发布结果检测超时（20秒）")
        return False

    async def upload(self, playwright: Playwright) -> None:
        page = getattr(self, "external_page", None)
        context = getattr(self, "external_context", None)
        browser = getattr(self, "external_browser", None)
        managed_browser = page is None
        if managed_browser:
            browser = await launch_publish_browser(
                playwright,
                executable_path=self.local_executable_path,
            )
            context = await new_publish_context(
                browser,
                storage_state=str(self.account_file),
            )
            context = await set_init_script(context)
            page = await context.new_page()

        async def _handle_unexpected_filechooser(file_chooser) -> None:
            try:
                bilibili_logger.warning("[bilibili] 检测到意外文件选择器触发，已拦截并置空。请检查是否仍有可见上传按钮被误点。")
                await file_chooser.set_files([])
            except Exception as e:
                bilibili_logger.warning(f"[bilibili] 拦截意外文件选择器失败: {e}")

        page.on("filechooser", lambda file_chooser: asyncio.create_task(_handle_unexpected_filechooser(file_chooser)))

        bilibili_logger.info("[bilibili] goto upload page")
        # 打开B站创作中心上传页（优先带 page_from 参数）
        try:
            await goto_and_reveal(
                page,
                "https://member.bilibili.com/platform/upload/video/frame?page_from=creative_home_top_upload",
                timeout=15000,
            )
        except Exception:
            try:
                await goto_and_reveal(
                    page,
                    "https://member.bilibili.com/platform/upload/video/frame",
                    timeout=15000,
                )
            except Exception:
                # 回退到旧地址
                await goto_and_reveal(
                    page,
                    "https://member.bilibili.com/platform/upload/video",
                    timeout=20000,
                )

        bilibili_logger.info("[bilibili] wait page ready")
        
        # 若存在“未提交的视频”提示，优先关闭
        await self._dismiss_unsubmitted_prompt(page)

        # 选择视频上传输入框（第一个，接受视频格式的）
        video_input_selector = 'input[type="file"][accept*=".mp4"]'
        await page.locator(video_input_selector).first.set_input_files(self.file_path)
        bilibili_logger.info(f"[bilibili] 视频文件已设置: {self.file_path}")

        bilibili_logger.info("[bilibili] wait upload complete")
        # 等待上传完成或稳定
        await self._wait_upload_complete(page)
        # 设置封面（可选）
        await self._set_cover(page)
        await self._fill_title(page)
        await self._set_creation_statement(page)
        await self._set_type(page)
        await self._set_partition(page)
        await self._fill_tags(page)
        await self._fill_desc(page)
        await self._set_schedule(page)

        if self.dry_run:
            if managed_browser:
                await keep_browser_open_for_dry_run(
                    page,
                    context,
                    browser,
                    account_file=self.account_file,
                    logger=bilibili_logger,
                    platform_name="B站",
                    block_until_close=self.dry_run_hold_browser,
                )
            return

        # 发布
        bilibili_logger.info("[bilibili] click publish")
        await self._click_publish(page)
        
        # 等待发布结果
        publish_success = await self._wait_publish_result(page)
        
        if publish_success:
            bilibili_logger.info("[bilibili] 视频发布成功！")
        else:
            raise RuntimeError("B站点击投稿后未确认提交成功")

        # 保存cookie
        await context.storage_state(path=str(self.account_file))
        # 关闭浏览器上下文和浏览器实例
        if managed_browser:
            await context.close()
            await browser.close()
        
    async def main(self) -> None:
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            await self.upload(playwright)

    async def _set_cover(self, page) -> None:
        cover_by_ratio = {
            ratio: path
            for ratio, path in {
                "4:3": self.thumbnail_paths.get("4:3"),
                "16:9": self.thumbnail_paths.get("16:9"),
            }.items()
            if path
        }
        fallback_path = self.thumbnail_path or cover_by_ratio.get("16:9") or cover_by_ratio.get("4:3")
        if not fallback_path:
            return
        started_at = time.perf_counter()
        try:
            if cover_by_ratio:
                bilibili_logger.info(f"[bilibili] 开始设置 B站双规格封面: {cover_by_ratio}")
            else:
                bilibili_logger.info(f"[bilibili] 开始设置封面: {fallback_path}")
            await self._open_cover_dialog(page)
            await self._switch_to_cover_upload_tab(page)

            if cover_by_ratio:
                if "4:3" not in cover_by_ratio or "16:9" not in cover_by_ratio:
                    bilibili_logger.warning(f"[bilibili] B站封面缺少比例，当前仅有: {list(cover_by_ratio.keys())}")
                await self._ensure_cover_sync_disabled(page)
                for ratio in ("4:3", "16:9"):
                    path = cover_by_ratio.get(ratio)
                    if not path:
                        continue
                    await self._select_cover_ratio(page, ratio)
                    before_signature = await self._get_cover_upload_area_signature(page)
                    await self._upload_cover_file(page, path)
                    await self._wait_cover_ratio_uploaded(page, ratio, before_signature=before_signature)
            else:
                await self._upload_cover_file(page, fallback_path)

            await self._confirm_cover_dialog(page)
            bilibili_logger.info(f"[bilibili] 封面设置完成，耗时 {time.perf_counter() - started_at:.1f} 秒")
        except Exception as e:
            bilibili_logger.error("[bilibili] 设置封面失败")
            bilibili_logger.error(e)
            raise RuntimeError(f"B站封面设置失败：{e}") from e

    async def _open_cover_dialog(self, page) -> None:
        selectors = [
            'text=封面设置',
            '.cover:has-text("封面设置")',
            'span:has-text("更换封面")',
            'button:has-text("更换封面")',
        ]
        for selector in selectors:
            locator = page.locator(selector).last
            try:
                if await locator.count() and await locator.is_visible():
                    await locator.scroll_into_view_if_needed()
                    await locator.click(force=True, timeout=5000)
                    await page.locator('.cover-editor.bcc-dialog__wrap-mask, .cover-editor').last.wait_for(
                        state="visible",
                        timeout=5000,
                    )
                    bilibili_logger.info(f"[bilibili] 已打开封面弹窗: {selector}")
                    return
            except PlaywrightError:
                continue
        raise RuntimeError("未找到 B站封面编辑入口")

    async def _switch_to_cover_upload_tab(self, page) -> None:
        editor = page.locator('.cover-editor.bcc-dialog__wrap-mask, .cover-editor').last
        await editor.wait_for(state="visible", timeout=5000)
        image_input = editor.locator('input[type="file"][accept*="image"]').last
        try:
            await image_input.wait_for(state="attached", timeout=5000)
            if await image_input.count():
                bilibili_logger.info("[bilibili] 已检测到封面图片 input，跳过上传封面 tab 切换")
                return
        except PlaywrightError:
            pass

        bilibili_logger.info("[bilibili] 未检测到封面图片 input，不点击上传封面按钮，避免弹出系统资源管理器")

    async def _ensure_cover_sync_disabled(self, page) -> None:
        try:
            editor = page.locator('.cover-editor.bcc-dialog__wrap-mask, .cover-editor').last
            checkbox = editor.locator('.cover-editor-panel-canvas input[type="checkbox"]').first
            if await checkbox.count() and await checkbox.is_checked():
                await checkbox.click(force=True, timeout=2000)
                bilibili_logger.info("[bilibili] 已关闭双比例同步改动，准备分别上传 4:3 和 16:9")
                await page.wait_for_timeout(150)
        except Exception as e:
            bilibili_logger.debug(f"[bilibili] 检查双比例同步状态失败，继续分别上传: {e}")

    async def _select_cover_ratio(self, page, ratio: str) -> None:
        editor = page.locator('.cover-editor.bcc-dialog__wrap-mask, .cover-editor').last
        await editor.wait_for(state="visible", timeout=5000)
        ratio_text = "首页推荐封面（4:3）" if ratio == "4:3" else "个人空间封面（16:9）"
        selectors = [
            f'.cover-editor-panel-canvas > div:has-text("{ratio_text}")',
            f'.cover-editor-panel-canvas-title:has-text("{ratio_text}")',
            f'.cover-editor-panel-canvas span.text:has-text("{ratio_text}")',
            f'text={ratio_text}',
        ]
        for selector in selectors:
            locator = editor.locator(selector).first
            try:
                if await locator.count():
                    await locator.scroll_into_view_if_needed()
                    await locator.click(force=True, timeout=3000)
                    bilibili_logger.info(f"[bilibili] 已切换封面比例: {ratio}")
                    await page.wait_for_timeout(200)
                    return
            except PlaywrightError:
                continue
        raise RuntimeError(f"未找到 B站 {ratio} 封面编辑区域")

    async def _upload_cover_file(self, page, cover_path: str) -> None:
        editor = page.locator('.cover-editor.bcc-dialog__wrap-mask, .cover-editor').last
        await editor.wait_for(state="visible", timeout=5000)
        selectors = [
            'input[type="file"][accept*="image"]',
            'input[type="file"][accept*=".png"]',
        ]
        for selector in selectors:
            locator = editor.locator(selector).last
            try:
                if await locator.count():
                    await locator.set_input_files(cover_path)
                    bilibili_logger.info(f"[bilibili] 封面文件已设置: {selector} -> {cover_path}")
                    return
            except PlaywrightError:
                continue
        raise RuntimeError("未找到 B站封面图片上传 input")

    async def _get_cover_upload_area_signature(self, page) -> str:
        try:
            return await page.evaluate(
                """() => {
                    const editor = document.querySelector('.cover-editor');
                    const area = editor?.querySelector('.cover-editor-panel-select .upload-area.has-image')
                        || editor?.querySelector('.cover-editor-panel-select .upload-area');
                    if (!area) return '';
                    const style = getComputedStyle(area);
                    return style.backgroundImage || area.getAttribute('style') || area.className || '';
                }""",
            ) or ""
        except Exception:
            return ""

    async def _wait_cover_ratio_uploaded(self, page, ratio: str, before_signature: str = "", timeout=8000) -> None:
        started_at = time.perf_counter()
        while time.perf_counter() - started_at < timeout / 1000:
            try:
                signature = await self._get_cover_upload_area_signature(page)
                if signature and (not before_signature or signature != before_signature):
                    await page.wait_for_timeout(1400)
                    bilibili_logger.info(f"[bilibili] {ratio} 封面上传素材已更新并等待应用")
                    return
            except PlaywrightError:
                pass
            await page.wait_for_timeout(200)
        await page.wait_for_timeout(1400)
        bilibili_logger.warning(f"[bilibili] 未检测到 {ratio} 上传素材变化，已额外等待后继续")

    async def _confirm_cover_dialog(self, page) -> None:
        editor = page.locator('.cover-editor.bcc-dialog__wrap-mask, .cover-editor').last
        await editor.wait_for(state="visible", timeout=5000)
        selectors = [
            '.cover-editor-button .button.submit:has-text("完成")',
            '.cover-editor-content-right-bottom .button.submit:has-text("完成")',
            '.cover-editor .button.submit:has-text("完成")',
        ]
        for selector in selectors:
            locator = editor.locator(selector).last
            try:
                await locator.wait_for(state="visible", timeout=5000)
                await locator.click(force=True, timeout=5000)
                if await self._wait_cover_dialog_closed(page):
                    bilibili_logger.info(f"[bilibili] 封面弹窗已确认: {selector}")
                    return
                bilibili_logger.warning(f"[bilibili] 点击封面完成后弹窗仍未关闭: {selector}")
            except PlaywrightError:
                continue
        raise RuntimeError("未找到 B站封面完成/确定按钮")

    async def _wait_cover_dialog_closed(self, page, timeout=8000) -> bool:
        started_at = time.perf_counter()
        while time.perf_counter() - started_at < timeout / 1000:
            dialog = page.locator('.cover-editor.bcc-dialog__wrap-mask, .bcc-dialog:has-text("封面制作")').first
            try:
                if not await dialog.count() or not await dialog.is_visible():
                    return True
            except PlaywrightError:
                return True
            await page.wait_for_timeout(200)
        return False


