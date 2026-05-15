from pathlib import Path

from conf import BASE_DIR

PLATFORM_IDENTITY_SELECTORS = {
    1: {
        "avatar": [".user_avatar", ".user-info img"],
        "name": [".user-info .name-box", ".user-info .name"],
    },
    2: {
        "avatar": [".finder-info img.avatar", ".account-info img.avatar", "img[alt*='视频号头像']"],
        "name": [".finder-nickname", ".account-info .name"],
    },
    3: {
        "avatar": ["#header-avatar [class*='avatar']", "#header-avatar"],
        "name": ["#header-avatar"],
    },
    4: {
        "avatar": [".user-info-dpd img", ".user-info img"],
        "name": [".user-info-name", ".user-info-dpd .user-info-name"],
    },
    5: {
        "avatar": [".cc-header .custom-lazy-img", ".header .custom-lazy-img"],
        "name": [".cc-header .user-name", ".cc-header [class*='name']"],
    },
}


def _looks_like_display_name(value: str | None) -> bool:
    if not value:
        return False
    text = " ".join(str(value).split())
    if len(text) < 2 or len(text) > 32:
        return False
    blocked = (
        "首页", "发布", "内容管理", "数据中心", "账号管理", "素材管理", "创作中心",
        "创作者中心", "创作服务平台", "视频号 · 助手", "通知", "设置", "退出",
        "登录", "上传", "平台", "服务平台", "个人中心", "粉丝管理", "稿件管理",
        "身份认证", "账号正常", "遇到问题", "主站"
    )
    if any(word in text for word in blocked):
        return False
    return not text.lower().endswith((".json", ".png", ".jpg", ".jpeg", ".webp"))


async def _first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0 and await locator.is_visible(timeout=1200):
                return locator
        except Exception:
            continue
    return None


async def _capture_element(locator, path: Path) -> bool:
    try:
        await locator.scroll_into_view_if_needed(timeout=1500)
        await locator.screenshot(path=str(path))
        return True
    except Exception as e:
        print(f"[avatar] element screenshot failed: {e}")
        return False


async def fetch_display_name_from_platform_api(page, platform_type: int | None = None) -> str | None:
    if platform_type == 3:
        endpoints = [
            "https://creator.douyin.com/aweme/v1/creator/user/info/",
            "https://creator.douyin.com/web/api/media/user/info/",
        ]
        for endpoint in endpoints:
            try:
                data = await page.evaluate(
                    """
                    async (url) => {
                      const res = await fetch(url, { credentials: 'include' });
                      if (!res.ok) return null;
                      return await res.json();
                    }
                    """,
                    endpoint,
                )
                if not isinstance(data, dict):
                    continue
                candidates = [
                    data.get("user_profile", {}).get("nick_name"),
                    data.get("douyin_user_verify_info", {}).get("nick_name"),
                    data.get("user", {}).get("nickname"),
                ]
                for candidate in candidates:
                    if _looks_like_display_name(candidate):
                        return " ".join(str(candidate).split())
            except Exception as e:
                print(f"[avatar] douyin api identity failed: {e}")

    if platform_type == 5:
        try:
            data = await page.evaluate(
                """
                async () => {
                  const res = await fetch('https://api.bilibili.com/x/web-interface/nav', {
                    credentials: 'include'
                  });
                  if (!res.ok) return null;
                  return await res.json();
                }
                """
            )
            candidate = data.get("data", {}).get("uname") if isinstance(data, dict) else None
            if _looks_like_display_name(candidate):
                return " ".join(str(candidate).split())
        except Exception as e:
            print(f"[avatar] bilibili api identity failed: {e}")

    return None


async def capture_avatar_from_page(page, avatar_name: str, platform_type: int | None = None) -> str | None:
    """Capture the account avatar, including img and CSS background avatars."""
    avatars_dir = Path(BASE_DIR / "avatars")
    avatars_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(avatar_name).name
    if not safe_name.lower().endswith(".png"):
        safe_name = f"{Path(safe_name).stem}.png"
    avatar_file = avatars_dir / safe_name

    try:
        await page.wait_for_timeout(1800)
        selectors = PLATFORM_IDENTITY_SELECTORS.get(platform_type or 0, {}).get("avatar", [])
        locator = await _first_visible_locator(page, selectors)
        if locator and await _capture_element(locator, avatar_file):
            return safe_name

        found = await page.evaluate(
            """
            () => {
              const nodes = Array.from(document.querySelectorAll('img, [style*="background-image"]'));
              const scored = nodes.map((node, index) => {
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                const background = style.backgroundImage || '';
                const text = [
                  node.alt || '',
                  node.className || '',
                  node.id || '',
                  node.src || '',
                  background,
                  node.parentElement ? node.parentElement.className || '' : ''
                ].join(' ').toLowerCase();
                const visible = rect.width >= 24 && rect.height >= 24 &&
                  rect.width <= 180 && rect.height <= 180 &&
                  style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.bottom > 0 && rect.right > 0;
                if (!visible) return null;
                let score = 0;
                if (/avatar|head|user|profile|face|account|portrait|uhead|qlogo|bfs\\/face|aweme-avatar/.test(text)) score += 90;
                if (Math.abs(rect.width - rect.height) <= 12) score += 30;
                if (rect.top < 170 || rect.left > window.innerWidth * 0.55) score += 22;
                if (/qrcode|qr|logo|icon|banner|cover|video-card/.test(text)) score -= 80;
                return { index, score };
              }).filter(Boolean).sort((a, b) => b.score - a.score);
              if (!scored.length || scored[0].score < 35) return false;
              nodes.forEach(node => node.removeAttribute('data-sau-avatar-candidate'));
              nodes[scored[0].index].setAttribute('data-sau-avatar-candidate', '1');
              return true;
            }
            """
        )
        if not found:
            return None
        target = page.locator('[data-sau-avatar-candidate="1"]').first
        if await _capture_element(target, avatar_file):
            return safe_name
        return None
    except Exception as e:
        print(f"[avatar] capture failed: {e}")
        return None


async def detect_display_name_from_page(page, platform_type: int | None = None) -> str | None:
    """Best-effort account nickname detection from a logged-in creator page."""
    try:
        await page.wait_for_timeout(800)
        api_name = await fetch_display_name_from_platform_api(page, platform_type)
        if api_name:
            return api_name

        if platform_type == 3:
            try:
                await page.locator("#header-avatar").hover(timeout=1800)
                await page.wait_for_timeout(500)
            except Exception:
                pass

        selectors = PLATFORM_IDENTITY_SELECTORS.get(platform_type or 0, {}).get("name", [])
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() == 0 or not await locator.is_visible(timeout=1000):
                    continue
                if platform_type == 3 and selector == "#header-avatar":
                    name = await page.evaluate(
                        """
                        () => {
                          const blocked = ['通知', '网址', '身份认证', '退出账号'];
                          const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                          const nodes = Array.from(document.querySelectorAll('span, div, a'));
                          const candidates = nodes.map(node => {
                            const rect = node.getBoundingClientRect();
                            const style = getComputedStyle(node);
                            const text = normalize(node.innerText || node.textContent);
                            const visible = rect.width > 4 && rect.height > 4 &&
                              style.display !== 'none' && style.visibility !== 'hidden' &&
                              rect.top >= 0 && rect.top < 64 && rect.left > window.innerWidth - 180;
                            return { text, left: rect.left, visible };
                          }).filter(item => item.visible && item.text && !blocked.some(word => item.text.includes(word)));
                          candidates.sort((a, b) => b.left - a.left);
                          return candidates.length ? candidates[0].text : null;
                        }
                        """
                    )
                else:
                    name = await locator.inner_text(timeout=1000)
                name = " ".join(str(name or "").split())
                if _looks_like_display_name(name):
                    return name
            except Exception:
                continue

        if platform_type == 5:
            name = await page.evaluate(
                """
                () => {
                  const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                  const header = document.querySelector('.cc-header, .header');
                  if (!header) return null;
                  const nodes = Array.from(header.querySelectorAll('span, div, a'));
                  const blocked = ['主站', '直播姬', '必剪', 'bilibili开课', '在bilibili星球', '投稿', '退出登录', '个人中心'];
                  const candidates = nodes.map(node => {
                    const rect = node.getBoundingClientRect();
                    const style = getComputedStyle(node);
                    const text = normalize(node.innerText || node.textContent);
                    const visible = rect.width > 8 && rect.height > 8 &&
                      style.display !== 'none' && style.visibility !== 'hidden' &&
                      rect.top >= 0 && rect.top < 64;
                    return { text, left: rect.left, visible };
                  }).filter(item => item.visible && item.text && !blocked.some(word => item.text.includes(word)));
                  candidates.sort((a, b) => a.left - b.left);
                  return candidates.length ? candidates[0].text : null;
                }
                """
            )
            name = " ".join(str(name or "").split())
            if _looks_like_display_name(name):
                return name

        name = await page.evaluate(
            """
            () => {
              const blacklist = [
                '首页', '发布', '发布视频', '内容管理', '数据中心', '账号管理', '素材管理',
                '创作中心', '创作者中心', '消息', '设置', '登录', '退出登录', '立即登录',
                '上传', '管理', '平台', '服务平台', '个人中心', '创作服务平台'
              ];
              const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
              const isBadText = (text) => {
                if (!text || text.length < 2 || text.length > 32) return true;
                if (/^[\\d\\W_]+$/.test(text)) return true;
                if (/\\.json|http|https|cookie|登录态|二维码|扫码/i.test(text)) return true;
                return blacklist.some(word => text === word || text.includes(word));
              };

              const nodes = Array.from(document.querySelectorAll('span, div, p, a, strong, b'));
              const candidates = [];
              nodes.forEach((node) => {
                const text = normalize(node.innerText || node.textContent);
                if (isBadText(text)) return;
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                if (
                  rect.width < 8 || rect.height < 8 || rect.width > 420 || rect.height > 82 ||
                  rect.bottom <= 0 || rect.right <= 0 ||
                  style.display === 'none' || style.visibility === 'hidden'
                ) return;
                const meta = [
                  node.className || '',
                  node.id || '',
                  node.getAttribute('aria-label') || '',
                  node.getAttribute('title') || '',
                  node.parentElement ? node.parentElement.className || '' : ''
                ].join(' ').toLowerCase();
                let score = 0;
                if (/nick|nickname|user-name|username|display-name|account-name|profile-name/.test(meta)) score += 90;
                if (/user|account|profile|author|creator|avatar|name/.test(meta)) score += 42;
                if (rect.top < 220) score += 24;
                if (rect.left > window.innerWidth * 0.45) score += 16;
                if (/^[\\u4e00-\\u9fa5A-Za-z0-9_\\-.·]{2,20}$/.test(text)) score += 16;
                if (node.children.length > 2) score -= 24;
                candidates.push({ text, score, top: rect.top, left: rect.left });
              });
              candidates.sort((a, b) => b.score - a.score || a.top - b.top || b.left - a.left);
              return candidates.length && candidates[0].score >= 54 ? candidates[0].text : null;
            }
            """
        )
        return name if _looks_like_display_name(name) else None
    except Exception as e:
        print(f"[avatar] display name detection failed: {e}")
        return None


async def capture_identity_from_page(page, avatar_name: str, platform_type: int | None = None) -> tuple[str | None, str | None]:
    avatar_path = await capture_avatar_from_page(page, avatar_name, platform_type)
    display_name = await detect_display_name_from_page(page, platform_type)
    return avatar_path, display_name
