# PROJECT_MAP

## 项目地图

- `frontend/src/components/publish/ScheduleSettings.vue`：非 B 站发布方式与定时发布规则设置。
- `frontend/src/views/PublishCenter.vue`：发布中心主页面，包含 B 站单独发布方式选择。
- `frontend/src/views/AccountManagement.vue`：账号管理页面，负责账号列表刷新、重新验证、绑定/重登入口。
- `frontend/src/stores/account.js`：账号列表状态归一化与平台类型映射。
- `myUtils/auth.py`：各平台 cookie / 登录态有效性校验。
- `myUtils/login.py`：各平台扫码登录与登录态写入数据库。
- `main.py`：发布接口 `/postVideo`、`/postVideoBatch`，负责校验 payload 并分发到各平台发布器。
- `myUtils/postVideo.py`：把前端相对文件名解析成实际视频/封面路径，并实例化各平台上传器。
- `uploader/tencent_uploader/main.py`：视频号上传、描述/话题、短标题、双规格封面、最终发表 dry-run。
- `uploader/douyin_uploader/main.py`：抖音上传、描述/话题、横竖双封面、最终发布 dry-run。
- `uploader/xiaohongshu_uploader/main.py`：小红书上传、封面、标题/正文话题、最终发布 dry-run。
- `uploader/ks_uploader/main.py`：快手上传、描述/话题、最终发布 dry-run。
- 后续只在明确需要时按目标文件或目录补充，不默认扫描整个目录树。
