import asyncio
import unittest
from datetime import datetime

from playwright.async_api import async_playwright

from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo


class XiaoHongShuPublishButtonSelectorTest(unittest.TestCase):
    def test_selects_bottom_publish_button_instead_of_sidebar_publish_note(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 2048, "height": 1152})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; width: 2048px; height: 1152px; font-family: sans-serif; }
                          .sidebar { position: fixed; left: 0; top: 0; width: 280px; height: 100vh; background: #f7f7f7; }
                          .sidebar-publish {
                            position: absolute; left: 30px; top: 100px; width: 220px; height: 58px;
                            border-radius: 30px; border: 0; background: #ff2442; color: white; font-size: 20px;
                          }
                          .action-bar {
                            position: fixed; left: 526px; right: 686px; bottom: 0; height: 88px;
                            background: rgba(255,255,255,0.92);
                          }
                          .draft { position: absolute; left: 260px; top: 20px; width: 154px; height: 50px; }
                          .bottom-publish {
                            position: absolute; left: 450px; top: 20px; width: 154px; height: 50px;
                            border-radius: 25px; border: 0; background: #ff2442; color: white; font-size: 20px;
                          }
                        </style>
                      </head>
                      <body>
                        <aside class="sidebar">
                          <button class="sidebar-publish">发布笔记</button>
                        </aside>
                        <main>
                          <div style="margin-left: 526px; padding-top: 120px;">已填写内容</div>
                        </main>
                        <div class="action-bar">
                          <button class="draft">暂存离开</button>
                          <button class="bottom-publish" data-test-id="bottom-publish"><span>发布</span></button>
                        </div>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                selected_test_id = await locator.evaluate(
                    """
                    node => {
                      const button = node.closest('button');
                      return button && button.getAttribute('data-test-id');
                    }
                    """
                )
                await browser.close()
                self.assertEqual(selected_test_id, "bottom-publish")

        asyncio.run(run_case())

    def test_selects_plain_bottom_div_publish_control(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 2048, "height": 1152})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; width: 2048px; height: 1152px; font-family: sans-serif; }
                          .sidebar { position: fixed; left: 0; top: 0; width: 280px; height: 100vh; }
                          .sidebar-publish {
                            position: absolute; left: 30px; top: 100px; width: 220px; height: 58px;
                            border-radius: 30px; background: #ff2442; color: white; font-size: 20px;
                          }
                          .action-bar {
                            position: fixed; left: 526px; right: 686px; bottom: 0; height: 88px;
                            background: rgba(255,255,255,0.92);
                          }
                          .draft { position: absolute; left: 260px; top: 20px; width: 154px; height: 50px; }
                          .plain-bottom-control {
                            position: absolute; left: 450px; top: 20px; width: 154px; height: 50px;
                            border-radius: 25px; background: rgb(255, 36, 66); color: white; font-size: 20px;
                            display: flex; align-items: center; justify-content: center;
                          }
                        </style>
                      </head>
                      <body>
                        <aside class="sidebar">
                          <div class="sidebar-publish">发布笔记</div>
                        </aside>
                        <div class="action-bar">
                          <div class="draft">暂存离开</div>
                          <div class="plain-bottom-control" data-test-id="bottom-publish"><span>发布</span></div>
                        </div>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                selected_test_id = await locator.evaluate(
                    """
                    node => {
                      const control = node.closest('[data-test-id]');
                      return control && control.getAttribute('data-test-id');
                    }
                    """
                )
                await browser.close()
                self.assertEqual(selected_test_id, "bottom-publish")

        asyncio.run(run_case())

    def test_trigger_promotes_inner_text_to_outer_publish_control(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 2048, "height": 1152})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; width: 2048px; height: 1152px; font-family: sans-serif; }
                          .action-bar {
                            position: fixed; left: 526px; right: 686px; bottom: 0; height: 88px;
                            background: rgba(255,255,255,0.92);
                          }
                          .plain-bottom-control {
                            position: absolute; left: 450px; top: 20px; width: 154px; height: 50px;
                            border-radius: 25px; background: rgb(255, 36, 66); color: white; font-size: 20px;
                            display: flex; align-items: center; justify-content: center;
                          }
                        </style>
                      </head>
                      <body>
                        <div class="action-bar">
                          <div class="plain-bottom-control" data-test-id="bottom-publish" onclick="window.__published = true">
                            <span>发布</span>
                          </div>
                        </div>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                locator = page.get_by_text("发布", exact=True)
                method = await uploader.trigger_publish_button(locator)
                published = await page.evaluate("window.__published === true")
                await browser.close()
                self.assertIn("dom-activation-on-promoted-target", method)
                self.assertTrue(published)

        asyncio.run(run_case())

    def test_scheduled_publish_selects_bottom_scheduled_publish_button(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1600, "height": 913})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; width: 1600px; height: 1900px; font-family: sans-serif; }
                          .settings { position: absolute; left: 410px; top: 1620px; width: 680px; height: 200px; }
                          .post-time-wrapper { width: 632px; height: 104px; }
                          .post-time-switch-container { width: 308px; height: 44px; }
                          .sidebar-publish { position: absolute; left: 24px; top: 80px; width: 176px; height: 44px; }
                          .action-bar {
                            position: fixed; left: 0; right: 0; bottom: 0; height: 96px;
                            background: rgba(255,255,255,0.92);
                          }
                          .bottom-publish {
                            position: absolute; left: 780px; top: 24px; width: 154px; height: 50px;
                            border-radius: 25px; border: 0; background: #ff2442; color: white; font-size: 20px;
                          }
                        </style>
                      </head>
                      <body>
                        <div class="sidebar-publish">发布笔记</div>
                        <div class="settings">
                          <div class="post-time-wrapper">
                            <span class="has-tips">定时发布</span>
                            <div class="post-time-switch-container">
                              <div class="custom-switch-text-content">定时发布</div>
                            </div>
                          </div>
                        </div>
                        <div class="action-bar">
                          <button class="bottom-publish" data-test-id="bottom-publish"><span>定时发布</span></button>
                        </div>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=datetime(2026, 5, 16, 10, 0),
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                selected_test_id = await locator.evaluate(
                    """
                    node => {
                      const button = node.closest('button');
                      return button && button.getAttribute('data-test-id');
                    }
                    """
                )
                await browser.close()
                self.assertEqual(selected_test_id, "bottom-publish")

        asyncio.run(run_case())

    def test_scheduled_publish_selects_xhs_custom_element_submit_text(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1600, "height": 913})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; height: 913px; font-family: sans-serif; }
                          .sidebar-publish {
                            position: fixed; left: 24px; top: 80px; width: 176px; height: 44px;
                            border-radius: 24px; background: rgb(255, 36, 66); color: white;
                          }
                          xhs-publish-btn {
                            position: fixed; left: 410px; bottom: 0; width: 680px; height: 90px;
                            display: block; z-index: 101;
                          }
                        </style>
                      </head>
                      <body>
                        <div class="sidebar-publish">发布笔记</div>
                        <xhs-publish-btn
                          data-test-id="xhs-host"
                          is-publish="true"
                          is-save-draft="true"
                          submit-text="定时发布"
                          save-text="暂存离开"
                          submit-disabled="false"
                          save-disabled="false"></xhs-publish-btn>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=datetime(2026, 5, 16, 10, 0),
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                selected_test_id = await locator.evaluate("node => node.getAttribute('data-test-id')")
                await browser.close()
                self.assertEqual(selected_test_id, "xhs-host")

        asyncio.run(run_case())

    def test_immediate_publish_ignores_schedule_setting_text(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1600, "height": 913})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; width: 1600px; height: 1900px; font-family: sans-serif; }
                          .settings { position: absolute; left: 410px; top: 1620px; width: 680px; height: 200px; }
                          .post-time-wrapper { width: 632px; height: 104px; }
                          .post-time-switch-container { width: 308px; height: 44px; }
                          .sidebar-publish { position: absolute; left: 24px; top: 80px; width: 176px; height: 44px; }
                          .action-bar {
                            position: fixed; left: 0; right: 0; bottom: 0; height: 96px;
                            background: rgba(255,255,255,0.92);
                          }
                          .bottom-publish {
                            position: absolute; left: 780px; top: 24px; width: 154px; height: 50px;
                            border-radius: 25px; border: 0; background: #ff2442; color: white; font-size: 20px;
                          }
                        </style>
                      </head>
                      <body>
                        <div class="sidebar-publish">发布笔记</div>
                        <div class="settings">
                          <div class="post-time-wrapper">
                            <span class="has-tips">定时发布</span>
                            <div class="post-time-switch-container">
                              <div class="custom-switch-text-content">定时发布</div>
                            </div>
                          </div>
                        </div>
                        <div class="action-bar">
                          <button class="bottom-publish" data-test-id="bottom-publish"><span>发布</span></button>
                        </div>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                selected_test_id = await locator.evaluate(
                    """
                    node => {
                      const button = node.closest('button');
                      return button && button.getAttribute('data-test-id');
                    }
                    """
                )
                await browser.close()
                self.assertEqual(selected_test_id, "bottom-publish")

        asyncio.run(run_case())

    def test_scrolls_offscreen_bottom_publish_button_into_view(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1600, "height": 913})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; width: 1600px; height: 1900px; font-family: sans-serif; }
                          .sidebar-publish { position: absolute; left: 24px; top: 80px; width: 176px; height: 44px; }
                          .settings { position: absolute; left: 410px; top: 1728px; width: 680px; height: 104px; }
                          .settings span { display: inline-block; width: 56px; height: 16px; }
                          .bottom-actions {
                            position: absolute; left: 620px; top: 1240px; width: 420px; height: 96px;
                          }
                          .bottom-publish {
                            width: 154px; height: 50px; border-radius: 25px; border: 0;
                            background: rgb(255, 36, 66); color: white; font-size: 20px;
                          }
                        </style>
                      </head>
                      <body>
                        <div class="sidebar-publish">发布笔记</div>
                        <div style="position:absolute; left:410px; top:617px; width:632px; height:140px;">内容编辑区</div>
                        <div class="bottom-actions">
                          <button>暂存离开</button>
                          <button class="bottom-publish" data-test-id="bottom-publish"><span>发布</span></button>
                        </div>
                        <div class="settings">
                          <span>定时发布</span>
                        </div>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                selected_test_id = await locator.evaluate(
                    """
                    node => {
                      const button = node.closest('button');
                      return button && button.getAttribute('data-test-id');
                    }
                    """
                )
                scroll_y = await page.evaluate("window.scrollY")
                await browser.close()
                self.assertEqual(selected_test_id, "bottom-publish")
                self.assertGreater(scroll_y, 300)

        asyncio.run(run_case())

    def test_upload_ready_waits_until_progress_text_disappears(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1600, "height": 913})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <body>
                        <div id="status">上传中85% 当前速度：77KB/s 剩余时间：2s</div>
                        <input class="d-text" placeholder="标题" />
                        <button>发布</button>
                        <script>
                          setTimeout(() => {
                            document.querySelector('#status').textContent = '上传成功';
                          }, 350);
                        </script>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                await uploader.wait_upload_ready(page)
                status_text = await page.locator("#status").inner_text()
                await browser.close()
                self.assertEqual(status_text, "上传成功")

        asyncio.run(run_case())

    def test_topic_accepts_platform_generated_valid_topic_node(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1280, "height": 720})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <body>
                        <div class="tiptap ProseMirror" contenteditable="true">标题内容</div>
                        <script>
                          const editor = document.querySelector('.tiptap.ProseMirror');
                          editor.addEventListener('input', () => {
                            if (editor.innerText.includes('#1') && !editor.querySelector('a.tiptap-topic')) {
                              editor.innerHTML = '标题内容 <a class="tiptap-topic">#每一帧都是电影画质[话题]#</a>';
                            }
                          });
                        </script>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=["#1"],
                    publish_date=0,
                    account_file="dummy.json",
                )
                await uploader.fill_topics(page)
                editor_text = await page.locator(".tiptap.ProseMirror").inner_text()
                topic_nodes = await page.locator(".tiptap.ProseMirror a.tiptap-topic").count()
                topic_text = await page.locator(".tiptap.ProseMirror a.tiptap-topic").first.inner_text()
                await browser.close()
                self.assertIn("[话题]", editor_text)
                self.assertEqual(topic_nodes, 1)
                self.assertEqual(topic_text, "#每一帧都是电影画质[话题]#")

        asyncio.run(run_case())

    def test_selects_red_bottom_publish_control_when_text_is_not_inner_text(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1600, "height": 913})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; width: 1600px; height: 1500px; font-family: sans-serif; }
                          .sidebar-publish { position: absolute; left: 30px; top: 100px; width: 220px; height: 58px; background: #ff2442; }
                          .bottom-publish {
                            position: absolute; left: 780px; top: 1240px; width: 154px; height: 50px;
                            border-radius: 25px; background: rgb(255, 36, 66); color: white;
                          }
                          .bottom-publish::before { content: "发布"; }
                        </style>
                      </head>
                      <body>
                        <div class="sidebar-publish">发布笔记</div>
                        <div class="bottom-publish" data-test-id="bottom-publish"></div>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                selected_test_id = await locator.evaluate(
                    "node => node.closest('[data-test-id]')?.getAttribute('data-test-id')"
                )
                await browser.close()
                self.assertEqual(selected_test_id, "bottom-publish")

        asyncio.run(run_case())

    def test_selects_xhs_publish_custom_element_and_activates_submit_side(self):
        async def run_case():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1600, "height": 913})
                await page.set_content(
                    """
                    <!doctype html>
                    <html>
                      <head>
                        <style>
                          body { margin: 0; height: 913px; font-family: sans-serif; }
                          .sidebar-publish {
                            position: fixed; left: 24px; top: 80px; width: 176px; height: 44px;
                            border-radius: 24px; background: rgb(255, 36, 66); color: white;
                          }
                          xhs-publish-btn {
                            position: fixed; left: 410px; bottom: 0; width: 680px; height: 90px;
                            display: block; z-index: 101;
                          }
                        </style>
                      </head>
                      <body>
                        <div class="sidebar-publish">发布笔记</div>
                        <xhs-publish-btn
                          data-test-id="xhs-host"
                          is-publish="true"
                          is-save-draft="true"
                          submit-text="发布"
                          save-text="暂存离开"
                          submit-disabled="false"
                          save-disabled="false"></xhs-publish-btn>
                        <script>
                          const host = document.querySelector('xhs-publish-btn');
                          host.addEventListener('click', event => {
                            host.setAttribute('data-click-x', String(event.clientX));
                            host.setAttribute('data-clicked', '1');
                          });
                        </script>
                      </body>
                    </html>
                    """
                )

                uploader = XiaoHongShuVideo(
                    title="测试",
                    file_path="dummy.mp4",
                    tags=[],
                    publish_date=0,
                    account_file="dummy.json",
                )
                locator = await uploader.wait_publish_button_ready(page)
                tag_name = await locator.evaluate("node => node.tagName")
                trigger_method = await uploader.trigger_publish_button(locator)
                clicked = await locator.evaluate("node => node.getAttribute('data-clicked')")
                click_x = int(await locator.evaluate("node => node.getAttribute('data-click-x')"))
                await browser.close()
                self.assertEqual(tag_name, "XHS-PUBLISH-BTN")
                self.assertEqual(clicked, "1")
                self.assertGreater(click_x, 820)
                self.assertIn("trusted-click-on-xhs-publish-host", trigger_method)

        asyncio.run(run_case())


if __name__ == "__main__":
    unittest.main()
