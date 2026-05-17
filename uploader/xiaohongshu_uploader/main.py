# -*- coding: utf-8 -*-
from datetime import datetime
import re

from playwright.async_api import Playwright, async_playwright, Page
import os
import asyncio

from conf import LOCAL_CHROME_PATH
from utils.base_social_media import (
    set_init_script,
    launch_publish_browser,
    new_publish_context,
    reveal_page_window,
    keep_browser_open_for_dry_run,
)
from utils.log import xiaohongshu_logger, XIAOHONGSHU_SCREENSHOT_DIR
from utils.publish_limits import normalize_publish_tags


def normalize_xhs_topic_text(raw_text: str) -> str:
    return "".join((raw_text or "").replace("\xa0", " ").split())


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

        await page.keyboard.press("Escape")
        try:
            await date_input.evaluate("node => node.blur()")
        except Exception:
            pass
        await page.wait_for_timeout(500)
        xiaohongshu_logger.info(f"小红书定时发布时间已确认: {actual_time}")

    def get_publish_button_text(self):
        return "定时发布" if self.publish_date != 0 else "发布"

    async def handle_upload_error(self, page):
        xiaohongshu_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def wait_publish_button_ready(self, page: Page):
        # 定时发布时新版页面底部主按钮会显示“定时发布”，不能继续只找“发布”。
        button_text = self.get_publish_button_text()
        xiaohongshu_logger.info(f"小红书开始定位底部{button_text}按钮")
        scroll_info = await self.scroll_publish_action_area_into_view(page, button_text)
        xiaohongshu_logger.info(f"小红书已尝试滚动到底部发布操作区: {scroll_info}")
        marked_button = page.locator('[data-sau-xhs-publish-button="1"]').first
        if await marked_button.count():
            await marked_button.scroll_into_view_if_needed(timeout=3000)
            info = await self.read_publish_button_info(marked_button)
            xiaohongshu_logger.info(f"小红书发布按钮按底部操作区定位: {info}")
            return marked_button

        reference_button = await self.find_reference_publish_button(page, button_text)
        if reference_button is not None:
            info = await self.read_publish_button_info(reference_button)
            xiaohongshu_logger.info(f"小红书发布按钮按开源项目策略定位: {info}")
            return reference_button

        async def mark_bottom_publish_button():
            return await page.evaluate(
                """
                (buttonText) => {
                  const normalize = text => String(text || '').replace(/\\s+/g, '').trim();
                  document.querySelectorAll('[data-sau-xhs-publish-button]').forEach(node => node.removeAttribute('data-sau-xhs-publish-button'));

                  const isDisabled = (node) => {
                    return Boolean(
                      node.disabled ||
                      node.getAttribute('disabled') !== null ||
                      node.getAttribute('aria-disabled') === 'true'
                    );
                  };

                  const isClickableLike = (node) => {
                    if (!node || node.nodeType !== Node.ELEMENT_NODE) return false;
                    const tag = node.tagName;
                    const role = node.getAttribute('role');
                    const cls = String(node.className || '').toLowerCase();
                    return tag === 'XHS-PUBLISH-BTN' ||
                      tag === 'BUTTON' ||
                      tag === 'A' ||
                      role === 'button' ||
                      /(^|[-_\\s])(btn|button|submit)([-_\\s]|$)/.test(cls) ||
                      cls.includes('d-button') ||
                      cls.includes('publish') ||
                      cls.includes('submit');
                  };

                  const isBottomCenterExact = (node) => {
                    if (!node || !(node instanceof HTMLElement)) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    const centerX = rect.left + rect.width / 2;
                    return normalize(node.innerText || node.textContent) === buttonText &&
                      rect.width >= 24 &&
                      rect.height >= 18 &&
                      rect.top > window.innerHeight * 0.58 &&
                      rect.bottom > window.innerHeight * 0.70 &&
                      rect.top < window.innerHeight &&
                      rect.right > 0 &&
                      centerX > window.innerWidth * 0.30 &&
                      centerX < window.innerWidth * 0.70 &&
                      style.display !== 'none' &&
                      style.visibility !== 'hidden' &&
                      Number(style.opacity || '1') > 0.2;
                  };

                  const closestClickable = (node) => {
                    let current = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
                    let bestExactBottom = null;
                    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
                      if (isBottomCenterExact(current)) {
                        bestExactBottom = current;
                        if (isClickableLike(current)) return current;
                      }
                    }
                    return bestExactBottom || (node.nodeType === Node.TEXT_NODE ? node.parentElement : node);
                  };

                  const visibleAndReady = (node) => {
                    if (!node || !(node instanceof HTMLElement) || isDisabled(node)) return null;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    const centerX = rect.left + rect.width / 2;
                    const xhsPublishHost =
                      node.tagName === 'XHS-PUBLISH-BTN' &&
                      normalize(node.getAttribute('submit-text')) === buttonText &&
                      node.getAttribute('submit-disabled') !== 'true';
                    const exactText = normalize(node.innerText || node.textContent) === buttonText;
                    const background = style.backgroundColor || '';
                    const xhsHostAction =
                      xhsPublishHost &&
                      rect.width >= 240 &&
                      rect.height >= 60 &&
                      rect.top > window.innerHeight * 0.55 &&
                      rect.bottom <= window.innerHeight + 30 &&
                      centerX > window.innerWidth * 0.30 &&
                      centerX < window.innerWidth * 0.70;
                    const redBottomAction =
                      /rgb\\(255,\\s*(36|35|44),\\s*(66|65|85)\\)/.test(background) &&
                      rect.width >= 70 &&
                      rect.width <= 260 &&
                      rect.height >= 32 &&
                      rect.height <= 80 &&
                      centerX > window.innerWidth * 0.30 &&
                      centerX < window.innerWidth * 0.70 &&
                      rect.top + window.scrollY > 300;
                    const bottomPrimaryAction =
                      rect.width >= 100 &&
                      rect.width <= 240 &&
                      rect.height >= 38 &&
                      rect.height <= 90 &&
                      rect.top > window.innerHeight * 0.72 &&
                      rect.bottom <= window.innerHeight + 20 &&
                      centerX > window.innerWidth * 0.45 &&
                      centerX < window.innerWidth * 0.65 &&
                      !/rgb\\(255,\\s*255,\\s*255\\)|rgba\\(0,\\s*0,\\s*0,\\s*0\\)/.test(background);
                    const visible = rect.width >= 24 && rect.height >= 18 &&
                      rect.right > 0 &&
                      centerX > window.innerWidth * 0.30 &&
                      centerX < window.innerWidth * 0.70 &&
                      style.display !== 'none' &&
                      style.visibility !== 'hidden' &&
                      Number(style.opacity || '1') > 0.2;
                    if (!visible || (!xhsHostAction && !exactText && !redBottomAction && !bottomPrimaryAction)) return null;
                    return { rect, style };
                  };

                  const directNodes = Array.from(document.querySelectorAll(
                    'xhs-publish-btn, button, [role="button"], [class*="btn"], [class*="button"], [class*="submit"], .d-button'
                  )).filter(node =>
                    normalize(node.innerText || node.textContent) === buttonText ||
                    (
                      node.tagName === 'XHS-PUBLISH-BTN' &&
                      normalize(node.getAttribute('submit-text')) === buttonText &&
                      node.getAttribute('submit-disabled') !== 'true'
                    )
                  );
                  const redActionNodes = Array.from(document.querySelectorAll('xhs-publish-btn, button, [role="button"], [class*="btn"], [class*="button"], [class*="submit"], div, span'))
                    .filter(node => {
                      if (!(node instanceof HTMLElement)) return false;
                      const rect = node.getBoundingClientRect();
                      const style = window.getComputedStyle(node);
                      const centerX = rect.left + rect.width / 2;
                      const xhsPublishHost =
                        node.tagName === 'XHS-PUBLISH-BTN' &&
                        normalize(node.getAttribute('submit-text')) === buttonText &&
                        node.getAttribute('submit-disabled') !== 'true';
                      if (xhsPublishHost) {
                        return rect.width >= 240 &&
                          rect.height >= 60 &&
                          rect.top > window.innerHeight * 0.55 &&
                          rect.bottom <= window.innerHeight + 30 &&
                          centerX > window.innerWidth * 0.30 &&
                          centerX < window.innerWidth * 0.70 &&
                          style.display !== 'none' &&
                          style.visibility !== 'hidden' &&
                          Number(style.opacity || '1') > 0.2;
                      }
                      return /rgb\\(255,\\s*(36|35|44),\\s*(66|65|85)\\)/.test(style.backgroundColor || '') &&
                        rect.width >= 70 &&
                        rect.width <= 260 &&
                        rect.height >= 32 &&
                        rect.height <= 80 &&
                        centerX > window.innerWidth * 0.30 &&
                        centerX < window.innerWidth * 0.70 &&
                        rect.top + window.scrollY > 300 &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        Number(style.opacity || '1') > 0.2;
                    });

                  const textNodes = [];
                  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
                    acceptNode(node) {
                      return normalize(node.nodeValue) === buttonText
                        ? NodeFilter.FILTER_ACCEPT
                        : NodeFilter.FILTER_REJECT;
                    }
                  });
                  while (walker.nextNode()) textNodes.push(walker.currentNode);

                  const rawTargets = [...directNodes, ...textNodes.map(closestClickable), ...redActionNodes];
                  const candidates = Array.from(new Set(rawTargets)).map((node) => {
                    const ready = visibleAndReady(node);
                    if (!ready) return null;
                    const { rect, style } = ready;
                    const background = style.backgroundColor || '';
                    const text = normalize(node.innerText || node.textContent);
                    const xhsPublishHost =
                      node.tagName === 'XHS-PUBLISH-BTN' &&
                      normalize(node.getAttribute('submit-text')) === buttonText &&
                      node.getAttribute('submit-disabled') !== 'true';
                    const docTop = rect.top + window.scrollY;
                    const cls = String(node.className || '').toLowerCase();
                    const score =
                      docTop * 2 +
                      rect.width +
                      (xhsPublishHost ? 4000 : 0) +
                      (text === buttonText ? 800 : 0) +
                      (/rgb\\(255,\\s*36,\\s*66\\)|rgb\\(255,\\s*35,\\s*65\\)|rgb\\(255,\\s*44,\\s*85\\)/.test(background) ? 1000 : 0) +
                      (['BUTTON', 'A'].includes(node.tagName) || node.getAttribute('role') === 'button' ? 300 : 0) +
                      (cls.includes('submit') || cls.includes('publish') ? 300 : 0) +
                      (cls.includes('d-button') || cls.includes('btn') ? 150 : 0);
                    return { node, score };
                  }).filter(Boolean).sort((a, b) => b.score - a.score);
                  if (!candidates.length) return false;
                  candidates[0].node.setAttribute('data-sau-xhs-publish-button', '1');
                  return true;
                }
                """,
                button_text,
            )

        for attempt in range(60):
            if await mark_bottom_publish_button():
                locator = page.locator('[data-sau-xhs-publish-button="1"]').first
                await locator.scroll_into_view_if_needed(timeout=3000)
                info = await self.read_publish_button_info(locator)
                xiaohongshu_logger.info(f"小红书发布按钮已定位: {info}")
                return locator

            if attempt == 0 or (attempt + 1) % 10 == 0:
                candidates = await self.read_publish_button_candidates(page, button_text)
                xiaohongshu_logger.info(f"小红书底部发布按钮兜底定位等待中，第{attempt + 1}秒，候选={candidates}")
            await page.wait_for_timeout(1000)

        candidates = await self.read_publish_button_candidates(page, button_text)
        screenshot_path = os.path.join(
            XIAOHONGSHU_SCREENSHOT_DIR,
            f"xiaohongshu_publish_button_unavailable_{int(asyncio.get_event_loop().time()*1000)}.png",
        )
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
        except Exception as e:
            screenshot_path = f"截图失败: {e}"
        xiaohongshu_logger.warning(f"小红书发布按钮未命中，候选={candidates}，截图={screenshot_path}")
        raise RuntimeError(f"小红书{button_text}按钮长时间不可用，候选={candidates}，截图={screenshot_path}")

    async def scroll_publish_action_area_into_view(self, page: Page, button_text: str):
        try:
            return await page.evaluate(
                """
                (buttonText) => {
                  const normalize = text => String(text || '').replace(/\\s+/g, '').trim();
                  const describe = (node) => {
                    if (!node || !(node instanceof HTMLElement)) return null;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return {
                      tag: node.tagName,
                      role: node.getAttribute('role'),
                      className: String(node.className || ''),
                      text: normalize(node.innerText || node.textContent),
                      pointerEvents: style.pointerEvents,
                      rect: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                      },
                      scrollY: Math.round(window.scrollY),
                    };
                  };
                  const isDisabled = node => Boolean(
                    node.disabled ||
                    node.getAttribute('disabled') !== null ||
                    node.getAttribute('aria-disabled') === 'true'
                  );
                  const isSidebar = node => {
                    const rect = node.getBoundingClientRect();
                    const text = normalize(node.innerText || node.textContent);
                    return text.includes('发布笔记') ||
                      (rect.left < window.innerWidth * 0.22 && rect.top < window.innerHeight * 0.35);
                  };
                  const isActionLike = node => {
                    const cls = String(node.className || '').toLowerCase();
                    return node.tagName === 'XHS-PUBLISH-BTN' ||
                      node.tagName === 'BUTTON' ||
                      node.getAttribute('role') === 'button' ||
                      cls.includes('btn') ||
                      cls.includes('button') ||
                      cls.includes('submit') ||
                      cls.includes('publish') ||
                      cls.includes('footer') ||
                      cls.includes('action');
                  };
                  const findTarget = () => Array.from(document.querySelectorAll(
                    'xhs-publish-btn, button, [role="button"], [class*="btn"], [class*="button"], [class*="submit"], [class*="publish"], div, span'
                  )).map(node => {
                    if (!(node instanceof HTMLElement) || isDisabled(node) || isSidebar(node)) return null;
                    const text = normalize(node.innerText || node.textContent);
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    if (rect.width < 24 || rect.height < 16 || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') <= 0.2) return null;
                    const cls = String(node.className || '').toLowerCase();
                    const centerX = rect.left + rect.width / 2;
                    const docTop = rect.top + window.scrollY;
                    const background = style.backgroundColor || '';
                    const xhsPublishHost =
                      node.tagName === 'XHS-PUBLISH-BTN' &&
                      normalize(node.getAttribute('submit-text')) === buttonText &&
                      node.getAttribute('submit-disabled') !== 'true' &&
                      rect.width >= 240 &&
                      rect.height >= 60 &&
                      rect.top > window.innerHeight * 0.55 &&
                      rect.bottom <= window.innerHeight + 30 &&
                      centerX > window.innerWidth * 0.30 &&
                      centerX < window.innerWidth * 0.70;
                    const redBottomAction =
                      /rgb\\(255,\\s*(36|35|44),\\s*(66|65|85)\\)/.test(background) &&
                      rect.width >= 70 &&
                      rect.width <= 260 &&
                      rect.height >= 32 &&
                      rect.height <= 80 &&
                      centerX > window.innerWidth * 0.30 &&
                      centerX < window.innerWidth * 0.70 &&
                      rect.top > window.innerHeight * 0.45;
                    const bottomPrimaryAction =
                      rect.width >= 100 &&
                      rect.width <= 240 &&
                      rect.height >= 38 &&
                      rect.height <= 90 &&
                      rect.top > window.innerHeight * 0.72 &&
                      rect.bottom <= window.innerHeight + 20 &&
                      centerX > window.innerWidth * 0.45 &&
                      centerX < window.innerWidth * 0.65 &&
                      !/rgb\\(255,\\s*255,\\s*255\\)|rgba\\(0,\\s*0,\\s*0,\\s*0\\)/.test(background);
                    if (!xhsPublishHost && text !== buttonText && !redBottomAction && !bottomPrimaryAction) return null;
                    const score =
                      Math.max(docTop, rect.top) * 2 +
                      (centerX > window.innerWidth * 0.30 && centerX < window.innerWidth * 0.70 ? 2000 : 0) +
                      (xhsPublishHost ? 5000 : 0) +
                      (/rgb\\(255,\\s*(36|35|44),\\s*(66|65|85)\\)/.test(background) ? 1200 : 0) +
                      (text === buttonText ? 800 : 0) +
                      (bottomPrimaryAction ? 700 : 0) +
                      (isActionLike(node) ? 800 : 0) +
                      (cls.includes('btn') || cls.includes('submit') || cls.includes('publish') ? 600 : 0) +
                      (rect.width >= 70 && rect.height >= 32 ? 500 : 0);
                    return { node, score };
                  }).filter(Boolean).sort((a, b) => b.score - a.score)[0]?.node;

                  let target = findTarget();
                  if (!target) {
                    const scrollables = Array.from(document.querySelectorAll('*'))
                      .filter(node => {
                        if (!(node instanceof HTMLElement)) return false;
                        const style = window.getComputedStyle(node);
                        return node.scrollHeight > node.clientHeight + 20 &&
                          !['hidden', 'clip'].includes(style.overflowY);
                      })
                      .sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
                    for (const scroller of scrollables.slice(0, 5)) {
                      scroller.scrollTop = scroller.scrollHeight;
                      scroller.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }
                    target = findTarget();
                    if (!target) {
                      return {
                        fallback: 'scroll-internal-containers',
                        scrollY: Math.round(window.scrollY),
                        scrollables: scrollables.slice(0, 5).map(node => ({
                          tag: node.tagName,
                          className: String(node.className || '').slice(0, 120),
                          scrollTop: Math.round(node.scrollTop),
                          scrollHeight: Math.round(node.scrollHeight),
                          clientHeight: Math.round(node.clientHeight),
                        })),
                      };
                    }
                  }
                  if (target) {
                    document.querySelectorAll('[data-sau-xhs-publish-button]').forEach(node => node.removeAttribute('data-sau-xhs-publish-button'));
                    target.setAttribute('data-sau-xhs-publish-button', '1');
                    target.scrollIntoView({ block: 'center', inline: 'center' });
                    return describe(target);
                  }
                  window.scrollTo({ top: document.documentElement.scrollHeight || document.body.scrollHeight, left: 0, behavior: 'instant' });
                  return { fallback: 'scroll-to-document-bottom', scrollY: Math.round(window.scrollY) };
                }
                """,
                button_text,
            )
        except Exception as e:
            return f"滚动到底部发布操作区失败: {e}"

    async def find_reference_publish_button(self, page: Page, button_text: str):
        exact_text = re.compile(rf"^\s*{re.escape(button_text)}\s*$")
        locators = [
            page.get_by_role("button", name=button_text, exact=True),
            page.locator("button").filter(has_text=exact_text),
            page.locator('[role="button"]').filter(has_text=exact_text),
            page.get_by_text(button_text, exact=True),
        ]

        xiaohongshu_logger.info("小红书尝试按开源项目策略定位发布按钮")
        for attempt in range(30):
            for locator in locators:
                try:
                    count = await locator.count()
                except Exception:
                    continue

                for index in range(count - 1, -1, -1):
                    candidate = locator.nth(index)
                    try:
                        if not await candidate.is_visible(timeout=300):
                            continue
                        await candidate.scroll_into_view_if_needed(timeout=2000)
                        if await self.is_sidebar_publish_entry(candidate):
                            continue
                        return candidate
                    except Exception:
                        continue
            if attempt == 0 or (attempt + 1) % 10 == 0:
                candidates = await self.read_publish_button_candidates(page, button_text)
                xiaohongshu_logger.info(f"小红书开源策略发布按钮定位等待中，第{attempt + 1}秒，候选={candidates}")
            await page.wait_for_timeout(1000)

        return None

    async def is_sidebar_publish_entry(self, locator):
        try:
            return await locator.evaluate(
                """
                (node) => {
                  const normalize = text => String(text || '').replace(/\\s+/g, '').trim();
                  const rect = node.getBoundingClientRect();
                  const text = normalize(node.innerText || node.textContent);
                  return text.includes('发布笔记') ||
                    (rect.left < window.innerWidth * 0.20 && rect.top < window.innerHeight * 0.30);
                }
                """
            )
        except Exception:
            return False

    async def read_publish_button_candidates(self, page: Page, button_text: str):
        try:
            return await page.evaluate(
                """
                (buttonText) => {
                  const normalize = text => String(text || '').replace(/\\s+/g, '').trim();
                  const describe = (node) => {
                    if (!node || !(node instanceof HTMLElement)) return null;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return {
                      tag: node.tagName,
                      role: node.getAttribute('role'),
                      attrs: node.tagName === 'XHS-PUBLISH-BTN' ? {
                        submitText: node.getAttribute('submit-text'),
                        submitDisabled: node.getAttribute('submit-disabled'),
                        saveText: node.getAttribute('save-text'),
                      } : null,
                      className: String(node.className || '').slice(0, 140),
                      text: normalize(node.innerText || node.textContent).slice(0, 60),
                      disabled: Boolean(node.disabled || node.getAttribute('disabled') !== null || node.getAttribute('aria-disabled') === 'true'),
                      pointerEvents: style.pointerEvents,
                      opacity: style.opacity,
                      rect: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        centerX: Math.round(rect.left + rect.width / 2),
                      },
                      bottomCandidate:
                        rect.top > window.innerHeight * 0.58 &&
                        rect.bottom > window.innerHeight * 0.70 &&
                        rect.left + rect.width / 2 > window.innerWidth * 0.30 &&
                        rect.left + rect.width / 2 < window.innerWidth * 0.70,
                    };
                  };

                  const nodes = Array.from(document.querySelectorAll('xhs-publish-btn, button, [role="button"], [class*="btn"], [class*="button"], [class*="submit"], .d-button, div, span'))
                    .filter(node =>
                      normalize(node.innerText || node.textContent).includes(buttonText) ||
                      (
                        node.tagName === 'XHS-PUBLISH-BTN' &&
                        normalize(node.getAttribute('submit-text')) === buttonText
                      )
                    )
                    .map(describe)
                    .filter(Boolean)
                    .sort((a, b) => b.rect.y - a.rect.y);
                  return {
                    viewport: { width: window.innerWidth, height: window.innerHeight },
                    matches: nodes.slice(0, 20),
                  };
                }
                """,
                button_text,
            )
        except Exception as e:
            return f"读取发布候选失败: {e}"

    async def read_publish_button_info(self, locator):
        try:
            return await locator.evaluate(
                """
                (node) => {
                  const rect = node.getBoundingClientRect();
                  const style = window.getComputedStyle(node);
                  return {
                    tag: node.tagName,
                    role: node.getAttribute('role'),
                    className: String(node.className || ''),
                    attrs: node.tagName === 'XHS-PUBLISH-BTN' ? {
                      submitText: node.getAttribute('submit-text'),
                      submitDisabled: node.getAttribute('submit-disabled'),
                      saveText: node.getAttribute('save-text'),
                    } : null,
                    text: String(node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim(),
                    disabledAttr: node.getAttribute('disabled'),
                    ariaDisabled: node.getAttribute('aria-disabled'),
                    pointerEvents: style.pointerEvents,
                    opacity: style.opacity,
                    rect: {
                      x: Math.round(rect.x),
                      y: Math.round(rect.y),
                      width: Math.round(rect.width),
                      height: Math.round(rect.height),
                    },
                  };
                }
                """
            )
        except Exception as e:
            return f"读取按钮信息失败: {e}"

    async def trigger_publish_button(self, locator):
        target_info = await self.promote_publish_click_target(locator)
        xiaohongshu_logger.info(f"小红书发布点击目标已提升: {target_info}")
        if isinstance(target_info, dict) and target_info.get("tag") == "XHS-PUBLISH-BTN":
            try:
                box = await locator.bounding_box()
                if not box:
                    raise RuntimeError("xhs-publish-btn bounding box 不可用")
                await locator.click(
                    position={"x": box["width"] * 0.64, "y": box["height"] * 0.50},
                    timeout=10000,
                )
                return f"trusted-click-on-xhs-publish-host target={target_info}"
            except Exception as click_error:
                xiaohongshu_logger.warning(f"小红书 WebComponent 发布按钮可信点击失败，尝试 DOM 激活: {click_error}")
                dom_method = await self.activate_publish_click_target(locator)
                return f"{dom_method} target={target_info}"
        try:
            await locator.click(timeout=10000)
            dom_method = await self.activate_publish_click_target(locator)
            return f"playwright-click+{dom_method} target={target_info}"
        except Exception as click_error:
            xiaohongshu_logger.warning(f"小红书发布按钮原生点击失败，尝试 DOM 激活: {click_error}")

        dom_method = await self.activate_publish_click_target(locator)
        return f"{dom_method} target={target_info}"

    async def promote_publish_click_target(self, locator):
        try:
            return await locator.evaluate(
                """
                (node) => {
                  const normalize = text => String(text || '').replace(/\\s+/g, '').trim();
                  const isElement = value => value && value.nodeType === Node.ELEMENT_NODE;
                  const describe = (el) => {
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    return {
                      tag: el.tagName,
                      role: el.getAttribute('role'),
                      className: String(el.className || ''),
                      attrs: el.tagName === 'XHS-PUBLISH-BTN' ? {
                        submitText: el.getAttribute('submit-text'),
                        submitDisabled: el.getAttribute('submit-disabled'),
                        saveText: el.getAttribute('save-text'),
                      } : null,
                      text: normalize(el.innerText || el.textContent),
                      rect: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                      },
                    };
                  };
                  const isActionLike = (el) => {
                    if (!isElement(el)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const cls = String(el.className || '').toLowerCase();
                    const text = normalize(el.innerText || el.textContent);
                    const centerX = rect.left + rect.width / 2;
                    const xhsPublishHost =
                      el.tagName === 'XHS-PUBLISH-BTN' &&
                      ['发布', '定时发布'].includes(normalize(el.getAttribute('submit-text'))) &&
                      el.getAttribute('submit-disabled') !== 'true' &&
                      rect.width >= 240 &&
                      rect.height >= 60 &&
                      rect.top > window.innerHeight * 0.50 &&
                      centerX > window.innerWidth * 0.25 &&
                      centerX < window.innerWidth * 0.75;
                    const bottomPublishArea =
                      ['发布', '定时发布'].includes(text) &&
                      rect.width >= 70 &&
                      rect.height >= 32 &&
                      rect.top > window.innerHeight * 0.50 &&
                      centerX > window.innerWidth * 0.25 &&
                      centerX < window.innerWidth * 0.75 &&
                      style.display !== 'none' &&
                      style.visibility !== 'hidden';
                    return xhsPublishHost ||
                      el.tagName === 'BUTTON' ||
                      el.getAttribute('role') === 'button' ||
                      cls.includes('btn') ||
                      cls.includes('button') ||
                      cls.includes('submit') ||
                      cls.includes('publish') ||
                      bottomPublishArea;
                  };

                  document.querySelectorAll('[data-sau-xhs-publish-click-target]').forEach(el => {
                    el.removeAttribute('data-sau-xhs-publish-click-target');
                  });

                  let current = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
                  let target = current;
                  for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
                    const text = normalize(current.innerText || current.textContent);
                    if (text.includes('发布笔记')) break;
                    if (isActionLike(current)) {
                      target = current;
                      break;
                    }
                  }
                  target.setAttribute('data-sau-xhs-publish-click-target', '1');
                  return describe(target);
                }
                """
            )
        except Exception as e:
            return f"提升发布点击目标失败: {e}"

    async def activate_publish_click_target(self, locator):
        return await locator.evaluate(
            """
            (node) => {
              const target = document.querySelector('[data-sau-xhs-publish-click-target]') ||
                (node instanceof HTMLElement ? node : node.parentElement);
              if (!target) return 'no-target';
              target.focus?.();
              const rect = target.getBoundingClientRect();
              const isXhsPublishHost =
                target.tagName === 'XHS-PUBLISH-BTN' &&
                target.getAttribute('submit-disabled') !== 'true';
              const clientX = isXhsPublishHost
                ? Math.round(rect.left + rect.width * 0.64)
                : Math.round(rect.left + rect.width / 2);
              const clientY = isXhsPublishHost
                ? Math.round(rect.top + rect.height * 0.50)
                : Math.round(rect.top + rect.height / 2);
              const eventInit = {
                bubbles: true,
                cancelable: true,
                composed: true,
                view: window,
                clientX,
                clientY,
              };
              for (const type of ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'pointerdown', 'mousedown', 'pointerup', 'mouseup']) {
                target.dispatchEvent(new MouseEvent(type, eventInit));
              }
              target.click?.();
              target.dispatchEvent(new MouseEvent('click', eventInit));
              return 'dom-activation-on-promoted-target';
            }
            """
        )

    async def wait_cover_generation_ready(self, page: Page):
        xiaohongshu_logger.info("小红书开始检查智能推荐封面生成状态")
        started_at = asyncio.get_running_loop().time()
        warned = False
        while True:
            body_text = ""
            try:
                body_text = await page.locator("body").inner_text(timeout=1000)
            except Exception:
                pass

            generating = any(
                text in body_text
                for text in ("智能推荐封面生成中", "封面生成中", "生成中，请稍等")
            )
            if not generating:
                xiaohongshu_logger.info("小红书智能推荐封面未阻塞发布，继续点击发布")
                return

            elapsed = asyncio.get_running_loop().time() - started_at
            if elapsed >= 90:
                xiaohongshu_logger.warning("小红书智能推荐封面生成等待超过90秒，已上传自定义封面，继续尝试发布")
                return
            if not warned or int(elapsed) % 10 == 0:
                xiaohongshu_logger.info("小红书智能推荐封面仍在生成，等待发布按钮真正生效")
                warned = True
            await page.wait_for_timeout(1000)

    async def click_publish_until_accepted(self, page: Page):
        button_text = self.get_publish_button_text()
        for attempt in range(1, 4):
            publish_button = await self.wait_publish_button_ready(page)
            trigger_method = await self.trigger_publish_button(publish_button)
            xiaohongshu_logger.info(f"小红书{button_text}按钮已触发，第{attempt}次，方式={trigger_method}")
            await self.confirm_publish_dialog_if_needed(page)

            try:
                await page.wait_for_url(
                    "https://creator.xiaohongshu.com/publish/success?**",
                    timeout=5000,
                )
                return True
            except Exception:
                pass

            try:
                body_text = await page.locator("body").inner_text(timeout=1000)
            except Exception:
                body_text = ""

            accepted_markers = ("发布中", "提交中", "审核中", "正在发布", "发布成功")
            if any(marker in body_text for marker in accepted_markers):
                xiaohongshu_logger.info("小红书发布请求已被页面接收，继续等待成功页")
                return True

            button_info = await self.read_publish_button_info(page.locator('[data-sau-xhs-publish-button="1"]').first)
            xiaohongshu_logger.warning(f"小红书{button_text}点击后5秒未进入发布流程，准备重试，按钮状态={button_info}")

        return False

    async def confirm_publish_dialog_if_needed(self, page: Page):
        confirm_texts = ("继续发布", "确认发布", "确定发布", "仍要发布", "仍然发布")
        dialog_selectors = (
            '[role="dialog"]',
            '.d-modal',
            '.reds-modal',
            '.modal',
            '.dialog',
            '[class*="modal"]',
            '[class*="dialog"]',
        )

        for _ in range(20):
            if "creator.xiaohongshu.com/publish/success" in page.url:
                return True

            for dialog_selector in dialog_selectors:
                dialog = page.locator(dialog_selector).last
                try:
                    if not await dialog.count() or not await dialog.is_visible(timeout=300):
                        continue
                except Exception:
                    continue

                for text in confirm_texts:
                    candidates = [
                        dialog.get_by_role("button", name=text, exact=True).last,
                        dialog.locator(f'button:has-text("{text}")').last,
                        dialog.locator(f'[role="button"]:has-text("{text}")').last,
                        dialog.locator(f'.d-button:has-text("{text}")').last,
                    ]
                    for candidate in candidates:
                        try:
                            if await candidate.count() and await candidate.is_visible(timeout=300) and await candidate.is_enabled(timeout=300):
                                await candidate.click(timeout=5000)
                                xiaohongshu_logger.info(f"小红书发布二次确认已点击: {text}")
                                return True
                        except Exception:
                            continue

            await page.wait_for_timeout(500)

        return False

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
        # 访问指定的 URL。批量共享浏览器时先在后台完成首次加载和刷新，再切到前台，减少标签闪烁。
        await page.goto(
            "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video",
            wait_until="commit",
            timeout=90000,
        )
        xiaohongshu_logger.info("[+] 小红书发布页已打开，先刷新一次再开始上传")
        await page.reload(wait_until="commit", timeout=90000)
        await page.wait_for_timeout(1000)
        await reveal_page_window(page)
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
            xiaohongshu_logger.info(f"小红书发布模式：定时发布，publish_date={self.publish_date}")
            await self.set_schedule_time_xiaohongshu(page, self.publish_date)
        else:
            xiaohongshu_logger.info("小红书发布模式：立即发布，最终按钮仍固定点击底部“发布”")

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

        await self.wait_cover_generation_ready(page)
        publish_accepted = await self.click_publish_until_accepted(page)
        if not publish_accepted:
            xiaohongshu_logger.warning("小红书发布按钮已连续触发3次但页面未反馈，继续等待成功页并保留超时截图")
        xiaohongshu_logger.info("小红书发布按钮已触发，等待发布结果")
        try:
            await page.wait_for_url(
                "https://creator.xiaohongshu.com/publish/success?**",
                timeout=90000,
            )
            xiaohongshu_logger.success("  [-]视频发布成功")
        except Exception as e:
            screenshot_path = os.path.join(XIAOHONGSHU_SCREENSHOT_DIR, f"xiaohongshu_publish_timeout_{int(asyncio.get_event_loop().time()*1000)}.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            raise RuntimeError(f"小红书点击发布后未确认成功，已保留截图：{screenshot_path}") from e

        await context.storage_state(path=self.account_file)  # 保存cookie
        xiaohongshu_logger.success('  [-]cookie更新完毕！')
        # 关闭浏览器上下文和浏览器实例
        if managed_browser:
            await context.close()
            await browser.close()

    async def wait_upload_ready(self, page: Page):
        started_at = asyncio.get_running_loop().time()
        max_wait_seconds = 8 * 60
        last_log_second = -1
        while True:
            if asyncio.get_running_loop().time() - started_at > max_wait_seconds:
                raise RuntimeError("小红书视频上传等待超时：未检测到上传成功或可编辑表单")

            if await page.locator('text=上传失败').count():
                raise RuntimeError("小红书视频上传失败")

            try:
                body_text = await page.locator("body").inner_text(timeout=1000)
            except Exception:
                body_text = ""
            compact_body_text = body_text.replace("\xa0", " ").replace("\n", " ")
            uploading_visible = any(
                marker in compact_body_text
                for marker in ("上传中", "剩余时间", "当前速度")
            )
            elapsed = int(asyncio.get_running_loop().time() - started_at)
            upload_complete_visible = "上传成功" in compact_body_text

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
                        if not uploading_visible and (upload_complete_visible or elapsed >= 8):
                            xiaohongshu_logger.info("[+] 小红书上传已进入可编辑状态")
                            return
                except Exception:
                    continue

            if elapsed != last_log_second and (elapsed < 5 or elapsed % 10 == 0):
                upload_excerpt = compact_body_text[:180]
                xiaohongshu_logger.info(f"  [-] 小红书视频仍在上传或页面未就绪，已等待{elapsed}秒，页面={upload_excerpt}")
                last_log_second = elapsed
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
                texts.append(normalize_xhs_topic_text(raw_text))
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

        accepted_topic_nodes = []

        # 小红书话题必须进入官方节点状态，普通 "#话题" 文本没有话题意义。
        # 优先点击精确候选；如果平台没有精确候选但生成了官方话题节点，也接受这个节点继续发布。
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
                    accepted_topic_nodes.append(new_nodes[-1])
                    accepted = True
                    break
                if new_nodes:
                    accepted_topic_nodes.append(new_nodes[-1])
                    xiaohongshu_logger.warning(
                        f"小红书话题 {topic} 未匹配到精确官方候选，已接受页面生成的有效话题节点: {new_nodes[-1]}"
                    )
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
                    f"小红书话题节点生成失败，缺失有效话题节点：{topic}，当前内容：{editor_text[:120]}，节点={topic_nodes}"
                )

        editor_text = (await editor.inner_text()).replace("\xa0", " ").strip()
        topic_nodes = await get_topic_node_texts()

        if len(topic_nodes) < len(topic_parts):
            raise RuntimeError(
                f"小红书话题节点写入校验失败，期望节点数={len(topic_parts)}，实际节点={topic_nodes}，当前内容={editor_text[:120]}"
            )

        xiaohongshu_logger.info(f"小红书话题已生成有效节点: {topic_nodes}")

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


