<template>
  <div class="account-management" v-loading="appStore.isAccountRefreshing" element-loading-text="正在验证账号...">
    <div class="page-header">
      <div>
        <h1>账号管理</h1>
        <p>以账号主体为入口管理多平台登录态。</p>
      </div>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索账号主体或平台账号"
          prefix-icon="Search"
          clearable
        />
        <el-button type="primary" @click="handleAddAccount()">
          <el-icon><Plus /></el-icon>
          <span>绑定平台</span>
        </el-button>
        <el-button type="info" @click="fetchAccounts(true)">
          <el-icon :class="{ 'is-loading': appStore.isAccountRefreshing, 'refresh-icon': true }"><Refresh /></el-icon>
          <span>{{ appStore.isAccountRefreshing ? '验证中...' : '重新验证' }}</span>
        </el-button>
      </div>
    </div>

    <div v-if="accountGroups.length" class="account-groups">
      <section v-for="group in accountGroups" :key="group.name" class="account-card">
        <div class="account-card-header">
          <div class="profile-main">
            <el-avatar
              v-if="getAvatarSrc(group)"
              :src="getAvatarSrc(group)"
              :size="42"
            />
            <el-avatar
              v-else
              :size="42"
              :style="{ backgroundColor: group.avatarColor }"
            >
              {{ group.avatarText }}
            </el-avatar>
            <div>
              <div class="profile-name" :title="group.name">{{ group.name }}</div>
              <div class="profile-meta">
                <span>{{ group.accounts.length }} 个平台已绑定</span>
                <span class="meta-dot"></span>
                <span>{{ group.normalCount }} 个可用</span>
              </div>
            </div>
          </div>
          <div class="account-card-actions">
            <div class="bound-platform-icons" aria-label="已绑定平台">
              <el-tooltip
                v-for="account in group.accounts"
                :key="`${group.name}-${account.id}-icon`"
                :content="`${account.platform} · ${displayAccountName(account)}`"
                placement="top"
              >
                <span :class="getPlatformLogoClasses(account.platform)">
                  <img :src="getPlatformMeta(account.platform).iconSrc" :alt="`${account.platform} 图标`" />
                </span>
              </el-tooltip>
            </div>
            <el-button size="small" @click="openGroup(group)">打开后台</el-button>
            <el-button size="small" type="primary" @click="handleAddAccount(group.name)">
              <el-icon><Plus /></el-icon>
              <span>绑定</span>
            </el-button>
          </div>
        </div>

        <div v-if="getMissingPlatforms(group).length" class="platform-strip" aria-label="可添加平台">
          <button
            v-for="platform in getMissingPlatforms(group)"
            :key="`${group.name}-${platform.type}`"
            class="platform-chip"
            type="button"
            @click="handleAddAccount(group.name, platform.name)"
          >
            <span :class="getPlatformLogoClasses(platform.name, 'small')">
              <img :src="platform.iconSrc" :alt="`${platform.name} 图标`" />
            </span>
            <span class="platform-chip-text">{{ platform.name }}</span>
            <span class="platform-chip-status">可绑定</span>
          </button>
        </div>

        <div class="platform-grid">
          <article v-for="account in group.accounts" :key="account.id" class="platform-item">
            <div class="platform-brand-cell">
              <span :class="getPlatformLogoClasses(account.platform)">
                <img :src="getPlatformMeta(account.platform).iconSrc" :alt="`${account.platform} 图标`" />
              </span>
              <div class="platform-brand-copy">
                <div class="platform-title-row">
                  <span class="platform-name">{{ account.platform }}</span>
                  <span class="status-pill" :class="{ 'is-error': account.status !== '正常' }">
                    {{ account.status }}
                  </span>
                </div>
                <span class="platform-file" :title="account.filePath">{{ shortCookieName(account.filePath) }}</span>
              </div>
            </div>

            <div class="platform-identity-cell">
              <el-avatar
                v-if="getAvatarSrc(account)"
                :src="getAvatarSrc(account)"
                :size="34"
              />
              <el-avatar
                v-else
                :size="34"
                :style="{ backgroundColor: account.avatarColor }"
              >
                {{ account.avatarText }}
              </el-avatar>
              <div class="platform-identity-copy">
                <div class="platform-account-name" :title="displayAccountName(account)">
                  {{ displayAccountName(account) }}
                </div>
                <div v-if="account.profileName && account.profileName !== account.name" class="platform-profile-name">
                  {{ account.profileName }}
                </div>
              </div>
            </div>

            <div class="platform-actions">
              <el-button size="small" @click="openAccount(account)">后台</el-button>
              <el-button size="small" @click="refreshAvatar(account)" :loading="avatarRefreshingId === account.id">
                资料
              </el-button>
              <el-button size="small" type="warning" @click="handleReAdd(account)">重登</el-button>
              <el-button size="small" type="danger" @click="handleDelete(account)">删除</el-button>
            </div>
          </article>
        </div>
      </section>
    </div>

    <div v-else class="empty-data">
      <el-empty :description="emptyDescription">
        <el-button type="primary" @click="handleAddAccount()">绑定第一个平台</el-button>
      </el-empty>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="520px"
      :close-on-click-modal="false"
      :close-on-press-escape="!sseConnecting"
      :show-close="!sseConnecting"
    >
      <el-form :model="accountForm" label-width="110px" :rules="rules" ref="accountFormRef">
        <el-form-item label="账号主体" prop="name">
          <el-input
            v-model="accountForm.name"
            placeholder="例如：飞哥技术号、小说矩阵01"
            :disabled="sseConnecting"
          />
        </el-form-item>
        <el-form-item label="绑定平台" prop="platform">
          <el-select
            v-model="accountForm.platform"
            placeholder="请选择平台"
            style="width: 100%"
            :disabled="sseConnecting"
          >
            <el-option label="抖音" value="抖音" />
            <el-option label="小红书" value="小红书" />
            <el-option label="视频号" value="视频号" />
            <el-option label="快手" value="快手" />
            <el-option label="B站" value="B站" />
          </el-select>
        </el-form-item>

        <div v-if="sseConnecting" class="qrcode-container">
          <div v-if="qrCodeData && !loginStatus" class="qrcode-wrapper">
            <p class="qrcode-tip">请使用对应平台 APP 扫码登录</p>
            <img :src="qrCodeData" alt="登录二维码" class="qrcode-image" />
          </div>
          <div v-else-if="!qrCodeData && !loginStatus" class="loading-wrapper">
            <el-icon class="is-loading"><Refresh /></el-icon>
            <span>请求中...</span>
          </div>
          <div v-else-if="loginStatus === '200'" class="success-wrapper">
            <el-icon><CircleCheckFilled /></el-icon>
            <span>绑定成功</span>
          </div>
          <div v-else-if="loginStatus === '500'" class="error-wrapper">
            <el-icon><CircleCloseFilled /></el-icon>
            <span>绑定失败，请稍后再试</span>
          </div>
        </div>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false" :disabled="sseConnecting">取消</el-button>
          <el-button
            type="primary"
            @click="submitAccountForm"
            :loading="sseConnecting"
            :disabled="sseConnecting"
          >
            {{ sseConnecting ? '请求中' : '确认' }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { Plus, Refresh, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountApi } from '@/api/account'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'

const accountStore = useAccountStore()
const appStore = useAppStore()
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

const platformCatalog = [
  { type: 3, name: '抖音', iconSrc: '/platform-icons/douyin.ico', iconClass: 'douyin', color: '#111827' },
  { type: 2, name: '视频号', iconSrc: '/platform-icons/wechat-channels-logo.png', iconClass: 'channels', color: '#ff9f2f' },
  { type: 5, name: 'B站', iconSrc: '/platform-icons/bilibili.png', iconClass: 'bilibili', color: '#00a1d6' },
  { type: 1, name: '小红书', iconSrc: '/platform-icons/xiaohongshu.png', iconClass: 'xhs', color: '#ff2442' },
  { type: 4, name: '快手', iconSrc: '/platform-icons/kuaishou.ico', iconClass: 'kuaishou', color: '#ff7a00' }
]

const platformOrder = platformCatalog.reduce((order, platform, index) => {
  order[platform.type] = index
  return order
}, {})

const searchKeyword = ref('')
const dialogVisible = ref(false)
const accountFormRef = ref(null)
const avatarRefreshingId = ref(null)

const accountForm = reactive({
  id: null,
  name: '',
  platform: ''
})

const rules = {
  name: [{ required: true, message: '请输入账号主体名称', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }]
}

const sseConnecting = ref(false)
const qrCodeData = ref('')
const loginStatus = ref('')
let eventSource = null
let accountStatusPollingTimer = null

const dialogTitle = computed(() => {
  if (accountForm.id) return '重新登录平台账号'
  if (accountForm.name) return `为「${accountForm.name}」添加平台`
  return '绑定平台登录态'
})

const emptyDescription = computed(() => {
  return searchKeyword.value.trim() ? '没有匹配的账号主体或平台账号' : '暂无账号主体'
})

const filteredAccounts = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) return accountStore.accounts
  return accountStore.accounts.filter(account => {
    return [account.profileName, account.name, account.platform]
      .filter(Boolean)
      .some(value => String(value).toLowerCase().includes(keyword))
  })
})

const accountGroups = computed(() => {
  const groupMap = new Map()
  filteredAccounts.value.forEach(account => {
    const groupName = account.profileName || account.name || '未命名账号'
    if (!groupMap.has(groupName)) {
      groupMap.set(groupName, {
        name: groupName,
        accounts: [],
        normalCount: 0,
        avatarUrl: null,
        avatarUpdatedAt: null,
        avatarText: String(groupName).slice(0, 1).toUpperCase(),
        avatarColor: getProfileColor(groupName),
        platformMap: {}
      })
    }
    const group = groupMap.get(groupName)
    group.accounts.push(account)
    group.platformMap[account.platform] = account
    if (account.status === '正常') group.normalCount += 1
    if (!group.avatarUrl && account.avatarUrl) {
      group.avatarUrl = account.avatarUrl
      group.avatarUpdatedAt = account.avatarUpdatedAt
    }
  })
  return Array.from(groupMap.values()).map(group => ({
    ...group,
    accounts: group.accounts.sort((a, b) => {
      return (platformOrder[a.type] ?? 99) - (platformOrder[b.type] ?? 99)
    })
  }))
})

const getProfileColor = (name) => {
  const colors = ['#3b82f6', '#14b8a6', '#8b5cf6', '#f97316', '#0f766e', '#64748b']
  const seed = String(name || '').split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return colors[seed % colors.length]
}

const resolveAvatarUrl = (url, updatedAt = '') => {
  if (!url) return ''
  const resolvedUrl = /^https?:\/\//i.test(url) ? url : `${apiBaseUrl}${url}`
  if (!updatedAt) return resolvedUrl
  const separator = resolvedUrl.includes('?') ? '&' : '?'
  return `${resolvedUrl}${separator}t=${encodeURIComponent(updatedAt)}`
}

const getAvatarSrc = (entity) => {
  return resolveAvatarUrl(entity?.avatarUrl, entity?.avatarUpdatedAt)
}

const displayAccountName = (account) => {
  return account?.name || account?.profileName || '未识别昵称'
}

const shortCookieName = (filePath = '') => {
  if (!filePath) return '未找到登录态文件'
  const normalized = String(filePath).replace(/\\/g, '/')
  const name = normalized.split('/').pop()
  if (!name) return normalized
  if (name.length <= 18) return name
  return `${name.slice(0, 8)}...${name.slice(-7)}`
}

const getPlatformMeta = (platformName) => {
  return platformCatalog.find(platform => platform.name === platformName) || {
    name: platformName || '未知',
    iconSrc: '',
    iconClass: 'unknown',
    color: '#8e8e93'
  }
}

const getPlatformLogoClasses = (platformName, size = '') => {
  const meta = getPlatformMeta(platformName)
  return [
    'platform-logo',
    `platform-logo--${meta.iconClass}`,
    size === 'small' ? 'platform-logo--small' : ''
  ].filter(Boolean)
}

const getMissingPlatforms = (group) => {
  return platformCatalog.filter(platform => !group.platformMap[platform.name])
}

const fetchAccounts = async (validate = false, options = {}) => {
  if (appStore.isAccountRefreshing) return
  const silent = options.silent === true
  if (!silent) appStore.setAccountRefreshing(true)
  try {
    const res = await accountApi.getValidAccounts({
      validate: validate ? 1 : 0,
      force: validate ? 1 : 0
    })
    if (res.code === 200 && Array.isArray(res.data)) {
      accountStore.setAccounts(res.data)
      if (validate) ElMessage.success('账号验证完成')
      if (appStore.isFirstTimeAccountManagement) appStore.setAccountManagementVisited()
    } else {
      ElMessage.error(res.msg || '获取账号数据失败')
    }
  } catch (error) {
    console.error('获取账号数据失败:', error)
    if (!silent) ElMessage.error('获取账号数据失败')
  } finally {
    if (!silent) appStore.setAccountRefreshing(false)
  }
}

const stopAccountStatusPolling = () => {
  if (accountStatusPollingTimer) {
    window.clearInterval(accountStatusPollingTimer)
    accountStatusPollingTimer = null
  }
}

const startAccountStatusPolling = (accountIds, successMessage = '账号状态已更新') => {
  const pendingIds = new Set(accountIds)
  if (!pendingIds.size) return
  stopAccountStatusPolling()

  let elapsed = 0
  accountStatusPollingTimer = window.setInterval(async () => {
    elapsed += 2
    await fetchAccounts(false, { silent: true })

    for (const account of accountStore.accounts) {
      if (pendingIds.has(account.id) && account.status === '正常') {
        pendingIds.delete(account.id)
      }
    }

    if (!pendingIds.size) {
      stopAccountStatusPolling()
      ElMessage.success(successMessage)
      return
    }

    if (elapsed >= 90) {
      stopAccountStatusPolling()
    }
  }, 2000)
}

const openAccount = async (account) => {
  try {
    const res = await accountApi.openAccounts([account.id])
    if (res.code === 200) {
      ElMessage.success('已打开平台后台')
      if (account.status !== '正常') {
        startAccountStatusPolling([account.id], `${account.platform} 登录状态已更新`)
      }
    } else {
      ElMessage.error(res.msg || '打开失败')
    }
  } catch (error) {
    ElMessage.error('打开失败')
  }
}

const openGroup = async (group) => {
  const ids = group.accounts.map(account => account.id)
  if (!ids.length) return
  try {
    const res = await accountApi.openAccounts(ids)
    if (res.code === 200) {
      ElMessage.success(`已打开 ${res.data?.opened ?? ids.length} 个平台后台`)
      const abnormalIds = group.accounts
        .filter(account => account.status !== '正常')
        .map(account => account.id)
      startAccountStatusPolling(abnormalIds, '账号登录状态已更新')
    } else {
      ElMessage.error(res.msg || '打开失败')
    }
  } catch (error) {
    ElMessage.error('打开失败')
  }
}

const refreshAvatar = async (account) => {
  avatarRefreshingId.value = account.id
  try {
    const res = await accountApi.refreshAvatar(account.id)
    if (res.code === 200) {
      ElMessage.success('头像已刷新')
      await fetchAccounts(false)
    } else {
      ElMessage.error(res.msg || '头像抓取失败')
    }
  } catch (error) {
    ElMessage.error('头像抓取失败')
  } finally {
    avatarRefreshingId.value = null
  }
}

const handleAddAccount = (profileName = '', platformName = '') => {
  Object.assign(accountForm, {
    id: null,
    name: profileName,
    platform: platformName
  })
  sseConnecting.value = false
  qrCodeData.value = ''
  loginStatus.value = ''
  dialogVisible.value = true
}

const handleReAdd = (account) => {
  Object.assign(accountForm, {
    id: account.id,
    name: account.profileName || account.name,
    platform: account.platform
  })
  sseConnecting.value = false
  qrCodeData.value = ''
  loginStatus.value = ''
  dialogVisible.value = true
}

const handleDelete = (account) => {
  ElMessageBox.confirm(
    `确定要删除「${account.profileName || account.name}」的 ${account.platform} 登录态吗？`,
    '删除平台登录态',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      const response = await accountApi.deleteAccount(account.id)
      if (response.code === 200) {
        accountStore.deleteAccount(account.id)
        ElMessage.success('删除成功')
      } else {
        ElMessage.error(response.msg || '删除失败')
      }
    } catch (error) {
      console.error('删除账号失败:', error)
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

const closeSSEConnection = () => {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

const connectSSE = (platform, profileName, recordId = null) => {
  closeSSEConnection()
  sseConnecting.value = true
  qrCodeData.value = ''
  loginStatus.value = ''

  const platformTypeMap = {
    '小红书': '1',
    '视频号': '2',
    '抖音': '3',
    '快手': '4',
    'B站': '5'
  }

  const type = platformTypeMap[platform] || '1'
  const params = new URLSearchParams({ type, id: profileName })
  if (recordId) {
    params.append('update', '1')
    params.append('record_id', String(recordId))
  }

  eventSource = new EventSource(`${apiBaseUrl}/login?${params.toString()}`)
  eventSource.onmessage = (event) => {
    const data = event.data
    if (!qrCodeData.value && data.length > 100) {
      qrCodeData.value = data.startsWith('data:image') ? data : `data:image/png;base64,${data}`
      return
    }

    if (data === '200' || data === '500') {
      loginStatus.value = data
      if (data === '200') {
        setTimeout(() => {
          closeSSEConnection()
          dialogVisible.value = false
          sseConnecting.value = false
          ElMessage.success(recordId ? '重新登录成功' : '绑定成功')
          fetchAccounts(false)
        }, 900)
      } else {
        closeSSEConnection()
        setTimeout(() => {
          sseConnecting.value = false
          qrCodeData.value = ''
          loginStatus.value = ''
        }, 1200)
      }
    }
  }

  eventSource.onerror = (error) => {
    console.error('SSE连接错误:', error)
    ElMessage.error('连接服务器失败')
    closeSSEConnection()
    sseConnecting.value = false
  }
}

const submitAccountForm = () => {
  accountFormRef.value.validate((valid) => {
    if (!valid) return
    connectSSE(accountForm.platform, accountForm.name, accountForm.id)
  })
}

onMounted(() => {
  fetchAccounts(false)
})

onBeforeUnmount(() => {
  closeSSEConnection()
  stopAccountStatusPolling()
})
</script>

<style lang="scss" scoped>
@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.account-management {
  max-width: 100%;
  min-width: 0;

  :deep(.el-button + .el-button) {
    margin-left: 0;
  }

  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 18px;
    margin-bottom: 22px;

    h1 {
      margin: 0;
      color: #1d1d1f;
      font-size: 28px;
      font-weight: 730;
      letter-spacing: 0;
    }

    p {
      margin: 8px 0 0;
      color: #6e6e73;
      font-size: 14px;
    }
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;

    .el-input {
      width: 300px;
      min-width: 0;
    }
  }

  .account-groups {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }

  .account-card {
    padding: 14px 16px;
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid rgba(226, 232, 240, 0.9);
    border-radius: 16px;
    box-shadow: 0 14px 34px rgba(15, 23, 42, 0.055);
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;

    &:hover {
      transform: translateY(-1px);
      border-color: rgba(203, 213, 225, 0.96);
      box-shadow: 0 18px 42px rgba(15, 23, 42, 0.075);
    }
  }

  .account-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid #eef2f7;
  }

  .profile-main {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .profile-name {
    color: #1d1d1f;
    font-size: 17px;
    font-weight: 730;
    line-height: 1.2;
    max-width: 380px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .profile-meta {
    margin-top: 3px;
    display: flex;
    align-items: center;
    gap: 7px;
    color: #6e6e73;
    font-size: 12px;
  }

  .meta-dot {
    width: 4px;
    height: 4px;
    border-radius: 999px;
    background: #cbd5e1;
  }

  .account-card-actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    justify-content: flex-end;
    flex-shrink: 0;
    gap: 7px;
  }

  .bound-platform-icons {
    display: flex;
    align-items: center;
    gap: 5px;
    padding-right: 4px;
  }

  .platform-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px 0 0;
    border-bottom: 1px solid #eef2f7;
  }

  .platform-chip {
    appearance: none;
    min-width: 0;
    height: 34px;
    display: inline-grid;
    grid-template-columns: auto auto auto;
    align-items: center;
    gap: 6px;
    padding: 0 9px 0 7px;
    background: #f8fafc;
    border: 1px solid #e8edf3;
    border-radius: 999px;
    color: #1f2937;
    cursor: pointer;
    text-align: left;
    transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;

    &:hover {
      transform: translateY(-1px);
      background: #ffffff;
      border-color: #cbd5e1;
      box-shadow: 0 10px 26px rgba(15, 23, 42, 0.07);
    }

    &:focus-visible {
      outline: 3px solid rgba(64, 158, 255, 0.18);
      outline-offset: 2px;
    }
  }

  .platform-logo {
    width: 30px;
    height: 30px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    border-radius: 9px;
    overflow: hidden;
    background: #fff;
    box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08), 0 6px 14px rgba(15, 23, 42, 0.08);

    img {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
    }
  }

  .platform-logo--channels img {
    width: 82%;
    height: 82%;
    object-fit: contain;
  }

  .platform-logo--small {
    width: 22px;
    height: 22px;
    border-radius: 7px;
    font-size: 10px;
  }

  .platform-logo--douyin {
    background: #0b1020;
  }

  .platform-logo--xhs {
    background: #ff2442;
  }

  .platform-logo--channels {
    background: #ffffff;
  }

  .platform-logo--kuaishou {
    background: #ff7a00;
  }

  .platform-logo--bilibili {
    background: #00a1d6;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
  }

  .platform-logo--unknown {
    background: #8e8e93;
  }

  .platform-chip-text {
    color: inherit;
    font-size: 12px;
    font-weight: 680;
    line-height: 1.1;
  }

  .platform-chip-status {
    color: #8a93a3;
    font-size: 11px;
    line-height: 1.1;
  }

  .platform-grid {
    display: grid;
    gap: 6px;
    margin-top: 10px;
  }

  .platform-item {
    display: grid;
    grid-template-columns: minmax(190px, 0.8fr) minmax(220px, 1.2fr) auto;
    align-items: center;
    gap: 12px;
    min-height: 54px;
    padding: 8px 10px;
    background: #fbfcfe;
    border: 1px solid transparent;
    border-radius: 12px;
    transition: border-color 0.16s ease, background 0.16s ease;

    &:hover {
      background: #ffffff;
      border-color: #e4eaf2;
    }
  }

  .platform-brand-cell,
  .platform-identity-cell {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .platform-brand-copy,
  .platform-identity-copy {
    min-width: 0;
  }

  .platform-title-row {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .platform-name {
    color: #1d1d1f;
    font-size: 13px;
    font-weight: 730;
  }

  .status-pill {
    height: 20px;
    display: inline-flex;
    align-items: center;
    padding: 0 7px;
    border-radius: 999px;
    background: #eefbe8;
    color: #55a630;
    border: 1px solid #d9f2cb;
    font-size: 11px;
    font-weight: 680;
    line-height: 1;

    &.is-error {
      background: #fff1f2;
      color: #e11d48;
      border-color: #ffe0e5;
    }
  }

  .platform-account-name {
    color: #334155;
    font-size: 13px;
    font-weight: 680;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .platform-profile-name,
  .platform-file {
    margin-top: 4px;
    color: #8a93a3;
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .platform-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 6px;
    max-width: 250px;

    :deep(.el-button) {
      padding: 5px 9px;
    }
  }

  .empty-data {
    padding: 80px 0;
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid #e8edf3;
    border-radius: 18px;
    box-shadow: 0 18px 48px rgba(15, 23, 42, 0.05);
  }

  .refresh-icon.is-loading {
    animation: rotate 1s linear infinite;
  }

  .qrcode-container {
    margin-top: 20px;
    text-align: center;
  }

  .qrcode-tip {
    color: #606266;
    margin-bottom: 12px;
  }

  .qrcode-image {
    width: 220px;
    height: 220px;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
  }

  .loading-wrapper,
  .success-wrapper,
  .error-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    min-height: 120px;
    color: #606266;
  }

  .success-wrapper {
    color: #67c23a;
  }

  .error-wrapper {
    color: #f56c6c;
  }

  @media (max-width: 1280px) {
    .page-header {
      flex-direction: column;
    }

    .header-actions {
      width: 100%;
      display: flex;
      flex-wrap: wrap;

      .el-input {
        flex: 0 0 100%;
        width: 100%;
      }

      .el-button {
        flex: 0 0 auto;
      }
    }
    .platform-item {
      grid-template-columns: minmax(160px, 0.8fr) minmax(190px, 1fr) auto;
    }
  }

  @media (max-width: 720px) {
    .account-card-header {
      align-items: stretch;
      flex-direction: column;
    }

    .account-card-actions,
    .platform-actions {
      justify-content: flex-start;
      max-width: none;
    }

    .header-actions {
      grid-template-columns: minmax(0, 1fr);
      align-items: stretch;

      .el-button {
        width: 100%;
      }
    }

    .platform-item {
      grid-template-columns: 1fr;

      .platform-actions {
        justify-content: flex-start;
      }
    }
  }
}
</style>
