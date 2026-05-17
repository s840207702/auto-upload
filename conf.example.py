from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

# Optional local helper service. Leave empty unless you know what you are doing.
XHS_SERVER = ""

# Optional Chrome path. Empty means the launcher will try system Chrome/Edge or bundled Chromium.
LOCAL_CHROME_PATH = ""

# Set False to force bundled Playwright Chromium from third_party when available.
USE_SYSTEM_BROWSER = False

# Safety guard for development and public examples:
# False means the automation clicks the final publish/schedule button.
DEBUG_SKIP_FINAL_PUBLISH = False
DEBUG_DRY_RUN_HOLD_SECONDS = 15
