from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
XHS_SERVER = "" # "http://127.0.0.1:11901"
LOCAL_CHROME_PATH = ""   # change me necessary！ for example C:/Program Files/Google/Chrome/Application/chrome.exe
USE_SYSTEM_BROWSER = False  # set False to force bundled Playwright Chromium from third_party

# 调试阶段保护：只跑到最终发布前，不点击各平台的发布/发表按钮。
DEBUG_SKIP_FINAL_PUBLISH = True
DEBUG_DRY_RUN_HOLD_SECONDS = 15
