import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from conf import DEBUG_SKIP_FINAL_PUBLISH
from queue import Empty, Queue
from urllib.parse import urlparse
from flask_cors import CORS
from myUtils.auth import check_cookie
from flask import Flask, cli as flask_cli, request, jsonify, Response, send_from_directory
from conf import BASE_DIR
from myUtils.login import get_tencent_cookie, douyin_cookie_gen, get_ks_cookie, xiaohongshu_cookie_gen, bilibili_cookie_gen
from myUtils.postVideo import post_video_tencent, post_video_DouYin, post_video_ks, post_video_xhs
from myUtils.postVideo import post_video_bilibili
from myUtils.postVideo import post_video_batch_dry_run_tabs, post_video_batch_tabs
from utils.base_social_media import (
    launch_chromium_with_codecs,
    new_publish_context,
    reveal_page_window,
    set_init_script,
)
from playwright.async_api import async_playwright
from myUtils.avatar import capture_identity_from_page
from utils.publish_limits import get_publish_tag_limit, normalize_publish_tags


active_queues = {}
active_login_sessions = {}
cancelled_login_request_ids = set()
_open_browsers = []  # keep references to prevent GC/auto-close
PUBLISH_PLATFORM_ORDER = [3, 2, 5, 1, 4]  # 抖音、视频号、B站、小红书、快手
PUBLISH_PLATFORM_ORDER_INDEX = {platform_type: index for index, platform_type in enumerate(PUBLISH_PLATFORM_ORDER)}
PLATFORM_NAME_MAP = {
    1: "小红书",
    2: "视频号",
    3: "抖音",
    4: "快手",
    5: "B站",
}


class _WerkzeugStartupWarningFilter(logging.Filter):
    _hidden_fragments = (
        "This is a development server",
        "Do not use it in a production deployment",
        "Use a production WSGI server instead",
    )

    def filter(self, record):
        message = record.getMessage()
        return not any(fragment in message for fragment in self._hidden_fragments)


def _quiet_local_server_startup_noise():
    flask_cli.show_server_banner = lambda *args, **kwargs: None
    logging.getLogger("werkzeug").addFilter(_WerkzeugStartupWarningFilter())


def _publish_platform_sort_key(item):
    if not isinstance(item, dict):
        return 999
    try:
        platform_type = int(item.get('type'))
    except (TypeError, ValueError):
        return 999
    return PUBLISH_PLATFORM_ORDER_INDEX.get(platform_type, 999)

def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# 全局账号验证缓存时间（秒），默认 3600 秒（1 小时）
ACCOUNT_STATUS_TTL_SECONDS = int(os.getenv('ACCOUNT_STATUS_TTL_SECONDS', '3600'))
# 账号有效性校验并发数。浏览器校验很重，默认 3 个并发比串行快，也避免一次性压满机器。
ACCOUNT_VALIDATION_CONCURRENCY = max(1, int(os.getenv('ACCOUNT_VALIDATION_CONCURRENCY', '3')))
# 上次完整验证时间戳
_last_accounts_validation_ts: float = 0.0

# Detect frontend dist directory for portable serving
ROOT_DIR = Path(__file__).resolve().parent

def _find_frontend_dist():
    candidates = [
        ROOT_DIR / "frontend" / "dist",
        ROOT_DIR.parent / "frontend" / "dist",
    ]
    for p in candidates:
        if (p / "index.html").exists():
            return p
    return ROOT_DIR / "frontend"

FRONTEND_DIST = _find_frontend_dist()
print(f"FRONTEND_DIST: {FRONTEND_DIST}")

def initialize_database() -> None:
    db_dir = Path(BASE_DIR / "db")
    db_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_dir / "database.db"
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
CREATE TABLE IF NOT EXISTS user_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type INTEGER NOT NULL,
    filePath TEXT NOT NULL,
    userName TEXT NOT NULL,
    status INTEGER DEFAULT 0
)
''')
        cursor.execute("PRAGMA table_info(user_info)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        migrations = {
            "profileName": "ALTER TABLE user_info ADD COLUMN profileName TEXT",
            "avatarPath": "ALTER TABLE user_info ADD COLUMN avatarPath TEXT",
            "avatarUpdatedAt": "ALTER TABLE user_info ADD COLUMN avatarUpdatedAt TEXT",
        }
        for column, sql in migrations.items():
            if column not in existing_columns:
                cursor.execute(sql)
        cursor.execute("UPDATE user_info SET profileName = userName WHERE profileName IS NULL OR profileName = ''")
        cursor.execute('''
CREATE TABLE IF NOT EXISTS file_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filesize REAL,
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT
)
''')
        conn.commit()
    Path(BASE_DIR / "avatars").mkdir(parents=True, exist_ok=True)
    print("[OK] 数据库已初始化")

app = Flask(__name__, static_folder=str(FRONTEND_DIST))

#允许所有来源跨域访问
CORS(app)

# 限制上传文件大小为160MB
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

def _serve_frontend_index():
    response = app.send_static_file('index.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def _safe_storage_path(base_dir, stored_name):
    if not stored_name:
        return None
    stored_name = str(stored_name).replace("\\", "/")
    if stored_name.startswith("/") or ".." in stored_name.split("/"):
        return None
    return Path(base_dir / stored_name).resolve()

def _remove_if_exists(path):
    if path and path.exists() and path.is_file():
        path.unlink()

def _account_row_to_dict(row):
    keys = [
        "id", "type", "filePath", "userName", "status",
        "profileName", "avatarPath", "avatarUpdatedAt"
    ]
    data = dict(zip(keys, row))
    data["avatarUrl"] = f"/avatars/{data['avatarPath']}" if data.get("avatarPath") else None
    return data

def _update_account_identity(account_id: int, avatar_path=None, display_name=None):
    if not avatar_path and not display_name:
        return
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        if avatar_path and display_name:
            cursor.execute(
                """
                UPDATE user_info
                SET avatarPath = ?, userName = ?, avatarUpdatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (avatar_path, display_name, account_id)
            )
        elif avatar_path:
            cursor.execute(
                "UPDATE user_info SET avatarPath = ?, avatarUpdatedAt = CURRENT_TIMESTAMP WHERE id = ?",
                (avatar_path, account_id)
            )
        else:
            cursor.execute(
                "UPDATE user_info SET userName = ?, avatarUpdatedAt = CURRENT_TIMESTAMP WHERE id = ?",
                (display_name, account_id)
            )
        conn.commit()

async def _capture_identity_from_logged_in_page(page, account_id: int, account_type: int):
    try:
        avatar_name = f"account_{account_id}.png"
        avatar_path, display_name = await capture_identity_from_page(page, avatar_name, account_type)
        _update_account_identity(account_id, avatar_path, display_name)
        return avatar_path, display_name
    except Exception as e:
        print(f"capture account identity failed id={account_id} type={account_type} err={e}")
        return None, None

async def _capture_account_avatar(account_id: int):
    url_map = {
        1: "https://creator.xiaohongshu.com/new/note-manager",
        2: "https://channels.weixin.qq.com/platform",
        3: "https://creator.douyin.com/creator-micro/content/manage",
        4: "https://cp.kuaishou.com/article/publish/video",
        5: "https://member.bilibili.com/platform/upload-manager/article",
    }
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, type, filePath FROM user_info WHERE id = ?",
            (account_id,)
        )
        row = cursor.fetchone()

    if not row:
        return None, "account not found"

    cookie_file = Path(BASE_DIR / "cookiesFile" / row["filePath"])
    if not cookie_file.exists():
        return None, "account cookie file not found"

    p = await async_playwright().start()
    browser = None
    try:
        browser = await launch_chromium_with_codecs(p, headless=True, executable_path=None)
        context = await browser.new_context(
            storage_state=str(cookie_file),
            viewport={"width": 1600, "height": 1000},
        )
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto(url_map.get(row["type"], "https://www.baidu.com"), wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(1200)
        avatar_path, display_name = await _capture_identity_from_logged_in_page(page, account_id, row["type"])
        await context.close()
        if not avatar_path and not display_name:
            return None, "未在平台后台页面识别到头像或昵称"
        return avatar_path, None
    except Exception as e:
        return None, str(e)
    finally:
        if browser:
            await browser.close()
        await p.stop()

def _validate_publish_payload(data):
    errors = []
    if not isinstance(data, dict):
        return ["发布参数格式错误"]

    platform_type = data.get('type')
    if platform_type not in (1, 2, 3, 4, 5):
        errors.append("请选择有效的发布平台")

    if data.get('enableTimer') in (1, "1", True, "true", "True"):
        try:
            jitter_minutes = int(data.get('timeJitterMinutes', 0) or 0)
            if jitter_minutes < 0 or jitter_minutes > 120:
                errors.append("随机浮动需在0-120分钟之间")
        except (TypeError, ValueError):
            errors.append("随机浮动需在0-120分钟之间")

    title = (data.get('title') or data.get('biliTitle') or '').strip()
    if platform_type == 5 and not title:
        errors.append("请填写B站稿件标题")

    file_list = data.get('fileList', [])
    if not isinstance(file_list, list) or not file_list:
        errors.append("请至少选择一个视频文件")
    else:
        for file_name in file_list:
            path = _safe_storage_path(Path(BASE_DIR / "videoFile"), file_name)
            if not path or not path.exists():
                errors.append(f"视频文件不存在：{file_name}")

    account_list = data.get('accountList', [])
    if not isinstance(account_list, list) or not account_list:
        errors.append("请至少选择一个发布账号")
    else:
        for account_file in account_list:
            path = _safe_storage_path(Path(BASE_DIR / "cookiesFile"), account_file)
            if not path or not path.exists():
                errors.append(f"账号登录文件不存在：{account_file}")

    cover_path = data.get('coverPath')
    if cover_path:
        path = _safe_storage_path(Path(BASE_DIR / "videoFile"), cover_path)
        if not path or not path.exists():
            errors.append(f"封面文件不存在：{cover_path}")

    cover_paths = data.get('coverPaths')
    if cover_paths is not None:
        if not isinstance(cover_paths, dict):
            errors.append("封面规格数据格式不正确")
        else:
            for ratio, file_name in cover_paths.items():
                if not file_name:
                    continue
                path = _safe_storage_path(Path(BASE_DIR / "videoFile"), file_name)
                if not path or not path.exists():
                    errors.append(f"{ratio} 封面文件不存在：{file_name}")

    return errors

async def _check_publish_account_states(data_list):
    account_items = []
    seen_keys = set()

    for data in data_list:
        if not isinstance(data, dict):
            continue
        if data.get("skipAccountCheck") in (1, "1", True, "true", "True", "yes"):
            continue
        try:
            platform_type = int(data.get("type"))
        except (TypeError, ValueError):
            continue
        for account_file in data.get("accountList") or []:
            key = (platform_type, account_file)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            account_items.append({
                "type": platform_type,
                "filePath": account_file,
            })

    if not account_items:
        return []

    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(account_items))
        file_paths = [item["filePath"] for item in account_items]
        cursor.execute(
            f"""
            SELECT id, type, filePath, userName, status, profileName, avatarPath, avatarUpdatedAt
            FROM user_info
            WHERE filePath IN ({placeholders})
            """,
            file_paths,
        )
        rows_by_file = {row["filePath"]: row for row in cursor.fetchall()}

    failures = []
    status_updates = []

    for item in account_items:
        platform_type = item["type"]
        file_path = item["filePath"]
        row = rows_by_file.get(file_path)
        display_name = row["userName"] if row else file_path
        profile_name = row["profileName"] if row else None
        label_name = display_name or profile_name or file_path
        platform_name = PLATFORM_NAME_MAP.get(platform_type, "未知平台")

        cookie_path = Path(BASE_DIR / "cookiesFile" / file_path)
        if not cookie_path.exists():
            failures.append(f"{platform_name}「{label_name}」登录文件不存在，请重新登录")
            if row:
                status_updates.append((0, row["id"]))
            continue

        try:
            is_valid = await check_cookie(platform_type, file_path)
        except Exception as e:
            print(f"publish account preflight failed type={platform_type} file={file_path} err={e}")
            is_valid = False

        if row:
            status_updates.append((1 if is_valid else 0, row["id"]))

        if not is_valid:
            failures.append(f"{platform_name}「{label_name}」登录已失效，请先重登后再发布")

    if status_updates:
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE user_info SET status = ? WHERE id = ?",
                status_updates,
            )
            conn.commit()

    return failures

def _validate_publish_accounts_before_run(data_list):
    failures = _run_async(_check_publish_account_states(data_list))
    if not failures:
        return []
    return ["发布前账号检查未通过"] + failures

@app.route('/')
def hello_world():
    return _serve_frontend_index()

# SPA fallback: serve files if exist, else index.html
@app.route('/<path:path>')
def spa_fallback(path):
    target = FRONTEND_DIST / path
    if target.exists() and target.is_file():
        return send_from_directory(str(FRONTEND_DIST), path)
    return _serve_frontend_index()

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({
            "code": 200,
            "data": None,
            "msg": "No file part in the request"
        }), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 200,
            "data": None,
            "msg": "No selected file"
        }), 400
    try:
        # 保存文件到指定位置
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{Path(file.filename).name}")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        file.save(filepath)
        return jsonify({"code":200,"msg": "File uploaded successfully", "data": f"{uuid_v1}_{file.filename}"}), 200
    except Exception as e:
        print(f"Upload failed: {e}")
        return jsonify({"code":500,"msg": str(e),"data":None}), 500

@app.route('/getFile', methods=['GET'])
def get_file():
    # 获取 filename 参数
    filename = request.args.get('filename')

    if not filename:
        return {"error": "filename is required"}, 400

    # 防止路径穿越攻击
    if '..' in filename or filename.startswith('/'):
        return {"error": "Invalid filename"}, 400

    # 拼接完整路径
    file_path = str(Path(BASE_DIR / "videoFile"))

    # 返回文件
    return send_from_directory(file_path,filename)

@app.route('/avatars/<path:filename>', methods=['GET'])
def get_avatar(filename):
    if '..' in filename or filename.startswith('/'):
        return {"error": "Invalid filename"}, 400
    return send_from_directory(str(Path(BASE_DIR / "avatars")), filename)


@app.route('/uploadSave', methods=['POST'])
def upload_save():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400

    # 获取表单中的自定义文件名（可选）
    custom_filename = request.form.get('filename', None)
    if custom_filename:
        suffix = Path(file.filename).suffix
        filename = Path(custom_filename).name + suffix
    else:
        filename = Path(file.filename).name

    try:
        # 生成 UUID v1
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")

        # 构造文件名和路径
        final_filename = f"{uuid_v1}_{filename}"
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{filename}")
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # 保存文件
        file.save(filepath)

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO file_records (filename, filesize, file_path)
            VALUES (?, ?, ?)
                                ''', (filename, round(float(os.path.getsize(filepath)) / (1024 * 1024),2), final_filename))
            conn.commit()
            print("[OK] 上传文件已记录")

        return jsonify({
            "code": 200,
            "msg": "File uploaded and saved successfully",
            "data": {
                "filename": filename,
                "filepath": final_filename
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": f"upload failed: {e}",
            "data": None
        }), 500

@app.route('/getFiles', methods=['GET'])
def get_all_files():
    try:
        # 使用 with 自动管理数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row  # 允许通过列名访问结果
            cursor = conn.cursor()

            # 查询所有记录
            cursor.execute("SELECT * FROM file_records")
            rows = cursor.fetchall()

            # 将结果转为字典列表
            data = [dict(row) for row in rows]

        return jsonify({
            "code": 200,
            "msg": "success",
            "data": data
        }), 200
    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("get file failed!"),
            "data": None
        }), 500


@app.route("/getValidAccounts",methods=['GET'])
async def getValidAccounts():
    """
    获取账号列表。
    可选参数：
      - validate: 1/true 表示触发校验；0/false 表示仅返回数据库缓存状态（更快）。默认 0。
      - force: 1/true 表示忽略 TTL 强制校验。
      - ids: 可选，逗号分隔的账号 id 列表。提供时，仅对这些账号执行校验，其余账号保留缓存状态。
    说明：
      - 为避免频繁打开浏览器验证，增加了 TTL，默认 1 小时内重复请求不会再次校验。
    """
    global _last_accounts_validation_ts

    validate = request.args.get('validate', '0').lower() in ('1', 'true', 'yes')
    force = request.args.get('force', '0').lower() in ('1', 'true', 'yes')
    ids_param = request.args.get('ids', '').strip()
    selected_ids = set()
    if ids_param:
        try:
            selected_ids = {int(x) for x in ids_param.split(',') if x.strip().isdigit()}
        except Exception:
            selected_ids = set()

    now_ts = time.time()
    should_validate = validate and (force or (now_ts - _last_accounts_validation_ts >= ACCOUNT_STATUS_TTL_SECONDS))

    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT id, type, filePath, userName, status, profileName, avatarPath, avatarUpdatedAt FROM user_info''')
        rows = cursor.fetchall()
        rows_list = [_account_row_to_dict(row) for row in rows]

        # 快速返回：不需要校验时，直接返回数据库中的缓存状态
        if not should_validate:
            return jsonify({
                "code": 200,
                "msg": None,
                "data": rows_list
            }), 200

        rows_to_validate = [
            row for row in rows_list
            if not selected_ids or row["id"] in selected_ids
        ]
        preview = request.args.get('preview', '0').lower() in ('1', 'true', 'yes')
        concurrency = 1 if preview else min(ACCOUNT_VALIDATION_CONCURRENCY, max(1, len(rows_to_validate)))
        semaphore = asyncio.Semaphore(concurrency)

        async def validate_account_row(row):
            platform = {1: 'xhs', 2: 'tencent', 3: 'douyin', 4: 'kuaishou', 5: 'bilibili'}.get(row["type"], 'unknown')
            started_at = time.perf_counter()
            try:
                cookie_path = Path(BASE_DIR / "cookiesFile" / row["filePath"])
                if not cookie_path.exists():
                    print(f"   - [{platform}] 跳过: cookie 文件不存在 id={row['id']} file={row['filePath']}")
                    return row, False

                async with semaphore:
                    print(f"   - 正在校验 [{platform}] 账号: id={row['id']} user={row['userName']}")
                    flag = await check_cookie(row["type"], row["filePath"], preview=preview)
                    elapsed = time.perf_counter() - started_at
                    print(f"     -> [{platform}] 结果: {'cookie 有效' if flag else 'cookie 失效'} ({elapsed:.1f}s)")
                    return row, flag
            except Exception as e:
                print(f"check_cookie 出错: platform={row['type']} id={row['id']} user={row['userName']} err={e}")
                return row, False

        print(f"\n[INFO] 开始账号有效性校验：{len(rows_to_validate)} 个账号，并发 {concurrency} ...")
        results = await asyncio.gather(*(validate_account_row(row) for row in rows_to_validate))

        any_updated = False
        for row, flag in results:
            new_status = 1 if flag else 0
            if row["status"] != new_status:
                row["status"] = new_status
                cursor.execute('''
                UPDATE user_info 
                SET status = ? 
                WHERE id = ?
                ''', (new_status, row["id"]))
                any_updated = True

        if any_updated:
            conn.commit()
            print("[OK] 用户状态已更新并写入数据库")
        else:
            print("[INFO] 用户状态无变更，保持现状")

        _last_accounts_validation_ts = time.time()

        return jsonify({
            "code": 200,
            "msg": None,
            "data": rows_list
        }), 200

@app.route('/deleteFile', methods=['GET'])
def delete_file():
    file_id = request.args.get('id')

    if not file_id or not file_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing file ID",
            "data": None
        }), 400

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM file_records WHERE id = ?", (file_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "File not found",
                    "data": None
                }), 404

            record = dict(record)

            # 删除数据库记录
            cursor.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
            conn.commit()

        _remove_if_exists(_safe_storage_path(Path(BASE_DIR / "videoFile"), record.get('file_path')))

        return jsonify({
            "code": 200,
            "msg": "File deleted successfully",
            "data": {
                "id": record['id'],
                "filename": record['filename']
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("delete failed!"),
            "data": None
        }), 500

@app.route('/batchDeleteFiles', methods=['POST'])
def batch_delete_files():
    data = request.get_json()
    
    if not data or 'ids' not in data:
        return jsonify({
            "code": 400,
            "msg": "Missing or invalid request data",
            "data": None
        }), 400
    
    ids = data['ids']
    
    if not isinstance(ids, list) or len(ids) == 0:
        return jsonify({
            "code": 400,
            "msg": "Invalid IDs list",
            "data": None
        }), 400
    
    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 查询要删除的记录
            placeholders = ','.join(['?' for _ in ids])
            cursor.execute(f"SELECT * FROM file_records WHERE id IN ({placeholders})", ids)
            records = cursor.fetchall()
            
            if not records:
                return jsonify({
                    "code": 404,
                    "msg": "No files found",
                    "data": None
                }), 404
            
            records = [dict(record) for record in records]

            # 删除数据库记录
            cursor.execute(f"DELETE FROM file_records WHERE id IN ({placeholders})", ids)
            conn.commit()
            
            deleted_count = cursor.rowcount

        for record in records:
            _remove_if_exists(_safe_storage_path(Path(BASE_DIR / "videoFile"), record.get('file_path')))
            
        return jsonify({
            "code": 200,
            "msg": f"Successfully deleted {deleted_count} files",
            "data": {
                "deleted_count": deleted_count,
                "deleted_ids": ids
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("Batch delete failed!"),
            "data": None
        }), 500

@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    account_id = request.args.get('id')
    if not account_id or not str(account_id).isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing account ID",
            "data": None
        }), 400
    account_id = int(account_id)

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "account not found",
                    "data": None
                }), 404

            record = dict(record)

            # 删除数据库记录
            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        _remove_if_exists(_safe_storage_path(Path(BASE_DIR / "cookiesFile"), record.get('filePath')))
        _remove_if_exists(_safe_storage_path(Path(BASE_DIR / "avatars"), record.get('avatarPath')))

        return jsonify({
            "code": 200,
            "msg": "account deleted successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("delete failed!"),
            "data": None
        }), 500

@app.route('/refreshAccountAvatar', methods=['POST'])
def refresh_account_avatar():
    data = request.get_json() or {}
    account_id = data.get('id')
    if not account_id or not str(account_id).isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing account ID",
            "data": None
        }), 200

    try:
        avatar_path, error = _run_async(_capture_account_avatar(int(account_id)))
    except Exception as e:
        avatar_path, error = None, str(e)

    if error:
        return jsonify({
            "code": 500,
            "msg": error,
            "data": None
        }), 200

    return jsonify({
        "code": 200,
        "msg": "account identity refreshed",
        "data": {
            "avatarPath": avatar_path,
            "avatarUrl": f"/avatars/{avatar_path}" if avatar_path else None
        }
    }), 200


# SSE 登录接口
@app.route('/login')
def login():
    # 1 小红书 2 视频号 3 抖音 4 快手
    type = request.args.get('type')
    # 账号名
    id = request.args.get('id')
    request_id = request.args.get('request_id') or str(uuid.uuid4())
    if request_id in cancelled_login_request_ids:
        cancelled_login_request_ids.discard(request_id)
        status_queue = Queue()
        status_queue.put("CANCELLED")
        response = Response(sse_stream(status_queue), mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'
        response.headers['Content-Type'] = 'text/event-stream'
        response.headers['Connection'] = 'keep-alive'
        return response
    # 是否更新已有记录
    update_mode = request.args.get('update', '0') in ('1', 'true', 'True')
    record_id = request.args.get('record_id')

    # 模拟一个用于异步通信的队列
    status_queue = Queue()
    cancel_event = threading.Event()
    active_queues[id] = status_queue
    active_login_sessions[request_id] = {
        "queue": status_queue,
        "cancel_event": cancel_event,
        "account_name": id,
    }
    # 启动异步任务线程
    thread = threading.Thread(
        target=run_async_function,
        args=(type, id, status_queue, update_mode, record_id, cancel_event),
        daemon=True
    )
    thread.start()
    response = Response(sse_stream(status_queue, session_key=request_id), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # 关键：禁用 Nginx 缓冲
    response.headers['Content-Type'] = 'text/event-stream'
    response.headers['Connection'] = 'keep-alive'
    return response


@app.route('/cancelLogin', methods=['POST'])
def cancel_login():
    data = request.get_json() or {}
    request_id = data.get('requestId') or data.get('request_id')
    if not request_id:
        return jsonify({
            "code": 400,
            "msg": "requestId required",
            "data": None
        }), 200

    session = active_login_sessions.get(request_id)
    if not session:
        cancelled_login_request_ids.add(request_id)
        return jsonify({
            "code": 200,
            "msg": None,
            "data": {"cancelled": True}
        }), 200

    session["cancel_event"].set()
    session["queue"].put("CANCELLED")
    return jsonify({
        "code": 200,
        "msg": None,
        "data": {"cancelled": True}
    }), 200

@app.route('/postVideo', methods=['POST'])
def postVideo():
    # 获取JSON数据
    data = request.get_json() or {}

    validation_errors = _validate_publish_payload(data)
    if validation_errors:
        return jsonify({
            "code": 400,
            "msg": "；".join(validation_errors),
            "data": None
        }), 200

    account_errors = _validate_publish_accounts_before_run([data])
    if account_errors:
        return jsonify({
            "code": 409,
            "msg": "；".join(account_errors),
            "data": {
                "reason": "account_preflight_failed"
            }
        }), 200

    # 从JSON数据中提取fileList和accountList
    file_list = data.get('fileList', [])
    account_list = data.get('accountList', [])
    type = data.get('type')
    title = data.get('title') or data.get('biliTitle') or ''
    tags = normalize_publish_tags(data.get('tags'), max_count=get_publish_tag_limit(type))
    category = data.get('category')
    enableTimer = data.get('enableTimer')
    cover_path = data.get('coverPath')  # 可选封面路径（相对 videoFile 下的存储名）
    cover_paths = data.get('coverPaths') if isinstance(data.get('coverPaths'), dict) else {}
    debug_dry_run = DEBUG_SKIP_FINAL_PUBLISH if 'debugDryRun' not in data else bool(data.get('debugDryRun'))
    debug_dry_run_hold_browser = bool(data.get('debugDryRunHoldBrowser', True))
    # B站专用字段
    bili_desc = data.get('biliDesc')
    bili_type = data.get('biliType')  # 自制/转载
    bili_partition = data.get('biliPartition')
    schedule_time = data.get('scheduleTime')
    if category == 0:
        category = None

    videos_per_day = data.get('videosPerDay')
    daily_times = data.get('dailyTimes')
    start_days = data.get('startDays')
    jitter_minutes = data.get('timeJitterMinutes', 0)
    # 打印获取到的数据（仅作为示例）
    print("File List:", file_list)
    print("Account List:", account_list)
    try:
        match type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, cover_path=cover_path, cover_paths=cover_paths,
                                   jitter_minutes=jitter_minutes, dry_run=debug_dry_run,
                                   dry_run_hold_browser=debug_dry_run_hold_browser)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, cover_path=cover_path, cover_paths=cover_paths,
                                   jitter_minutes=jitter_minutes, dry_run=debug_dry_run,
                                   dry_run_hold_browser=debug_dry_run_hold_browser)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, cover_path=cover_path, cover_paths=cover_paths,
                          jitter_minutes=jitter_minutes, dry_run=debug_dry_run,
                          dry_run_hold_browser=debug_dry_run_hold_browser)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, cover_path=cover_path, cover_paths=cover_paths,
                          jitter_minutes=jitter_minutes, dry_run=debug_dry_run,
                          dry_run_hold_browser=debug_dry_run_hold_browser)
            case 5:
                post_video_bilibili(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, desc=bili_desc, bili_type=bili_type, bili_partition=bili_partition,
                          cover_path=cover_path, cover_paths=cover_paths,
                          schedule_time=schedule_time, jitter_minutes=jitter_minutes, dry_run=debug_dry_run,
                          dry_run_hold_browser=debug_dry_run_hold_browser)
            case _:
                return jsonify({"code": 400, "msg": "unsupported platform", "data": None}), 200
    except Exception as e:
        print(f"postVideo failed: {e}")
        return jsonify({
            "code": 500,
            "msg": f"发布失败：{e}",
            "data": None
        }), 200
    # 返回响应给客户端
    return jsonify(
        {
            "code": 200,
            "msg": None,
            "data": None
        }), 200


@app.route('/openAccounts', methods=['POST'])
def open_accounts():
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return jsonify({
            "code": 400,
            "msg": "ids required",
            "data": None
        }), 200

    # 查询账号信息
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        # rows: [id, type, filePath, userName, status]
        placeholders = ",".join(["?"] * len(ids))
        cursor.execute(f"SELECT id, type, filePath, userName, status FROM user_info WHERE id IN ({placeholders})", tuple(ids))
        rows = cursor.fetchall()

    if not rows:
        return jsonify({
            "code": 404,
            "msg": "accounts not found",
            "data": None
        }), 200

    def run_open_tabs(rows_):
        async def open_tabs_async():
            p = await async_playwright().start()
            browser = await launch_chromium_with_codecs(p, headless=False, executable_path=None, hide_until_ready=True)
            _open_browsers.append(browser)

            platform_domains = {
                1: ("xiaohongshu.com",),
                2: ("channels.weixin.qq.com", "weixin.qq.com", "qq.com",),
                3: ("douyin.com", "bytedance.com", "iesdouyin.com",),
                4: ("kuaishou.com",),
                5: ("bilibili.com",),
            }

            def domain_matches(value, domains):
                if not value:
                    return False
                normalized = str(value).lower().lstrip(".")
                return any(normalized == domain or normalized.endswith(f".{domain}") for domain in domains)

            def origin_matches(origin, domains):
                try:
                    host = urlparse(origin).hostname or origin
                except Exception:
                    host = origin
                return domain_matches(host, domains)

            def merge_storage_states(account_rows):
                merged_cookies = {}
                merged_origins = {}
                for (_acc_id, _acc_type, file_path, _user_name, _status) in account_rows:
                    storage_path = Path(BASE_DIR / "cookiesFile" / file_path)
                    if not storage_path.exists():
                        continue
                    try:
                        state = json.loads(storage_path.read_text(encoding="utf-8"))
                    except Exception as e:
                        print(f"read account state failed file={file_path} err={e}")
                        continue
                    for cookie in state.get("cookies", []):
                        cookie_key = (cookie.get("name"), cookie.get("domain"), cookie.get("path"))
                        merged_cookies[cookie_key] = cookie
                    for origin_state in state.get("origins", []):
                        origin = origin_state.get("origin")
                        if origin:
                            merged_origins[origin] = origin_state
                return {
                    "cookies": list(merged_cookies.values()),
                    "origins": list(merged_origins.values()),
                }

            def filter_storage_state_for_account(state, account_type):
                domains = platform_domains.get(account_type, ())
                if not domains:
                    return state
                return {
                    "cookies": [
                        cookie for cookie in state.get("cookies", [])
                        if domain_matches(cookie.get("domain"), domains)
                    ],
                    "origins": [
                        origin_state for origin_state in state.get("origins", [])
                        if origin_matches(origin_state.get("origin"), domains)
                    ],
                }

            def looks_logged_in(account_type, page_url):
                if not page_url:
                    return False
                if account_type == 2:
                    return "channels.weixin.qq.com/platform" in page_url and "login" not in page_url
                if account_type == 4:
                    return "cp.kuaishou.com" in page_url and "login" not in page_url
                return "login" not in page_url

            def mark_account_normal(account_id):
                try:
                    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE user_info SET status = 1 WHERE id = ?", (account_id,))
                        conn.commit()
                except Exception as e:
                    print(f"mark account normal failed id={account_id} err={e}")

            async def write_context_state(context, storage_path, account_type):
                try:
                    state = await context.storage_state(indexed_db=True)
                except TypeError:
                    state = await context.storage_state()
                filtered_state = filter_storage_state_for_account(state, account_type)
                storage_path.write_text(
                    json.dumps(filtered_state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            async def save_account_state(
                context,
                page,
                storage_path,
                account_id,
                account_type,
                close_after_login=False,
                closed_state=None,
            ):
                if closed_state is not None and closed_state["closed"]:
                    return True
                try:
                    if not looks_logged_in(account_type, page.url):
                        return False
                    await write_context_state(context, storage_path, account_type)
                    mark_account_normal(account_id)
                    await _capture_identity_from_logged_in_page(page, account_id, account_type)
                    if close_after_login and closed_state is not None and not closed_state["closed"]:
                        closed_state["closed"] = True
                        await page.close()
                        print(f"[openAccounts] Login completed, closed account tab id={account_id}")
                        return True
                except Exception as e:
                    print(f"persist account state failed id={account_id} err={e}")
                return False

            async def monitor_login_state(
                context,
                page,
                storage_path,
                account_id,
                account_type,
                close_after_login=False,
                closed_state=None,
            ):
                for _ in range(90):
                    await asyncio.sleep(1)
                    if page.is_closed():
                        return
                    if not looks_logged_in(account_type, page.url):
                        continue
                    await page.wait_for_timeout(1800)
                    if page.is_closed() or not looks_logged_in(account_type, page.url):
                        continue
                    closed = await save_account_state(
                        context,
                        page,
                        storage_path,
                        account_id,
                        account_type,
                        close_after_login,
                        closed_state,
                    )
                    if closed:
                        return

            async def save_after_navigation(
                frame,
                context,
                page,
                storage_path,
                account_id,
                account_type,
                close_after_login=False,
                closed_state=None,
            ):
                if not close_after_login:
                    return
                if frame != page.main_frame:
                    return
                await page.wait_for_timeout(2500)
                await save_account_state(
                    context,
                    page,
                    storage_path,
                    account_id,
                    account_type,
                    close_after_login,
                    closed_state,
                )

            # 平台登录后页面地址
            url_map = {
                1: "https://creator.xiaohongshu.com/new/note-manager",
                2: "https://channels.weixin.qq.com/platform/post/list",
                3: "https://creator.douyin.com/creator-micro/content/manage",
                4: "https://cp.kuaishou.com/article/publish/video",
                5: "https://member.bilibili.com/platform/upload-manager/article",
            }
            context = await new_publish_context(
                browser,
                storage_state=merge_storage_states(rows_),
            )
            context = await set_init_script(context)
            page_entries = []
            for (acc_id, acc_type, file_path, user_name, _status) in rows_:
                try:
                    storage_path = Path(BASE_DIR / "cookiesFile" / file_path)
                    close_after_login = _status != 1
                    closed_state = {"closed": False}
                    page = await context.new_page()
                    if close_after_login:
                        page.on(
                            "framenavigated",
                            lambda frame, ctx=context, pg=page, path=storage_path, account_id=acc_id, account_type=acc_type, should_close=close_after_login, state=closed_state:
                                asyncio.create_task(save_after_navigation(
                                    frame,
                                    ctx,
                                    pg,
                                    path,
                                    account_id,
                                    account_type,
                                    should_close,
                                    state,
                                ))
                        )
                    url = url_map.get(acc_type) or "https://www.baidu.com"
                    page_entries.append({
                        "page": page,
                        "url": url,
                        "context": context,
                        "storage_path": storage_path,
                        "account_id": acc_id,
                        "account_type": acc_type,
                        "close_after_login": close_after_login,
                        "closed_state": closed_state,
                    })
                    # 命名标签便于识别
                    try:
                        await page.evaluate("document.title = document.title + ' - ' + arguments[0]", user_name)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"open tab failed id={acc_id} err={e}")

            async def navigate_entry(entry):
                try:
                    await entry["page"].goto(entry["url"], wait_until="commit", timeout=15000)
                except Exception as e:
                    print(f"open tab navigation failed id={entry['account_id']} err={e}")
                if entry["close_after_login"] and not entry["closed_state"]["closed"]:
                    asyncio.create_task(monitor_login_state(
                        entry["context"],
                        entry["page"],
                        entry["storage_path"],
                        entry["account_id"],
                        entry["account_type"],
                        entry["close_after_login"],
                        entry["closed_state"],
                    ))

            if page_entries:
                navigation_tasks = [asyncio.create_task(navigate_entry(entry)) for entry in page_entries]
                try:
                    await reveal_page_window(page_entries[0]["page"])
                except Exception as e:
                    print(f"reveal browser failed err={e}")
                await asyncio.gather(*navigation_tasks)
            # 保持浏览器打开，直到进程退出（避免意外自动关闭）
            print("[openAccounts] Tabs opened, holding browser open...")
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                # do not stop playwright/browsers here to allow persistence if loop ends unexpectedly
                pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(open_tabs_async())
        finally:
            loop.close()

    t = threading.Thread(target=run_open_tabs, args=(rows,), daemon=True)
    t.start()

    return jsonify({
        "code": 200,
        "msg": None,
        "data": {"opened": len(rows)}
    }), 200


@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    # 获取JSON数据
    data = request.get_json()

    # 从JSON数据中提取 type 和 userName
    user_id = data.get('id')
    type = data.get('type')
    userName = data.get('userName')
    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 更新数据库记录
            cursor.execute('''
                           UPDATE user_info
                           SET type     = ?,
                               userName = ?
                           WHERE id = ?;
                           ''', (type, userName, user_id))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account update successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("update failed!"),
            "data": None
        }), 500

@app.route('/postVideoBatch', methods=['POST'])
def postVideoBatch():
    data_list = request.get_json()

    if not isinstance(data_list, list):
        return jsonify({"code": 400, "msg": "Expected a JSON array", "data": None}), 400
    data_list = sorted(
        data_list,
        key=_publish_platform_sort_key,
    )
    for data in data_list:
        validation_errors = _validate_publish_payload(data)
        if validation_errors:
            return jsonify({
                "code": 400,
                "msg": "；".join(validation_errors),
                "data": None
            }), 200

    account_errors = _validate_publish_accounts_before_run(data_list)
    if account_errors:
        return jsonify({
            "code": 409,
            "msg": "；".join(account_errors),
            "data": {
                "reason": "account_preflight_failed"
            }
        }), 200

    all_debug_dry_run = all(
        DEBUG_SKIP_FINAL_PUBLISH if 'debugDryRun' not in data else bool(data.get('debugDryRun'))
        for data in data_list
    )
    if all_debug_dry_run:
        try:
            batch_results = post_video_batch_dry_run_tabs(data_list)
        except Exception as e:
            print(f"postVideoBatch dry-run tabs failed: {e}")
            return jsonify({
                "code": 500,
                "msg": f"预发布检查失败：{e}",
                "data": None
            }), 200
        return jsonify({
            "code": 200,
            "msg": None,
            "data": {
                "results": batch_results
            }
        }), 200

    try:
        batch_results = post_video_batch_tabs(data_list, dry_run=False)
    except Exception as e:
        print(f"postVideoBatch shared-browser publish failed: {e}")
        return jsonify({
            "code": 500,
            "msg": f"发布失败：{e}",
            "data": None
        }), 200

    return jsonify({
        "code": 200,
        "msg": None,
        "data": {
            "results": batch_results
        }
    }), 200

# 包装函数：在线程中运行异步函数
def run_async_function(type,id,status_queue, update_mode=False, record_id=None, cancel_event=None):
    cookiesFile_dir = Path(BASE_DIR / "cookiesFile")
    cookiesFile_dir.mkdir(parents=False, exist_ok=True)
    login_task_map = {
        '1': xiaohongshu_cookie_gen,
        '2': get_tencent_cookie,
        '3': douyin_cookie_gen,
        '4': get_ks_cookie,
        '5': bilibili_cookie_gen,
    }
    login_task = login_task_map.get(str(type))
    if not login_task:
        status_queue.put(f"ERROR: 不支持的平台类型：{type}")
        status_queue.put("500")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(login_task(id, status_queue, update_mode, record_id, cancel_event))
    except Exception as e:
        print(f"login task failed: type={type} id={id} err={e}")
        status_queue.put(f"ERROR: 登录页面初始化失败：{e}")
        status_queue.put("500")
    finally:
        loop.close()

# SSE 流生成器函数
def sse_stream(status_queue, first_event_timeout=60, session_key=None):
    started_at = time.time()
    has_sent_first_event = False
    try:
        while True:
            try:
                msg = status_queue.get(timeout=0.5)
            except Empty:
                if not has_sent_first_event and time.time() - started_at > first_event_timeout:
                    yield "data: ERROR: 登录页面加载超时，未获取到二维码。请关闭弹窗后重试，或检查平台登录页是否改版、浏览器是否被拦截。\n\n"
                    yield "data: 500\n\n"
                    break
                yield ": ping\n\n"
                continue

            has_sent_first_event = True
            yield f"data: {msg}\n\n"
            if str(msg) in ("200", "500", "CANCELLED"):
                break
    finally:
        if session_key:
            active_login_sessions.pop(session_key, None)

if __name__ == '__main__':
    initialize_database()
    _quiet_local_server_startup_noise()
    app.run(host='0.0.0.0' ,port=5409)
