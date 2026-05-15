<template>
  <div class="publish-center">
    <section class="account-dock">
      <div class="dock-head">
        <div>
          <h2>账号主体</h2>
        </div>
        <div class="dock-actions">
          <el-tag v-if="selectedProfileGroup" type="info" round>
            {{ selectedProfileGroup.normalCount }} 个可用平台
          </el-tag>
          <el-button @click="resetForm">清空</el-button>
        </div>
      </div>

      <div v-if="accountGroups.length" class="account-dock-body">
        <div class="account-rail">
          <button
            v-for="group in accountGroups"
            :key="group.name"
            type="button"
            :class="['account-pill', { active: publishForm.selectedProfileName === group.name }]"
            @click="selectProfile(group)"
          >
            <span class="profile-avatar">
              <img v-if="group.avatarUrl" :src="resolveAvatarUrl(group.avatarUrl)" alt="" />
              <span v-else>{{ group.name.slice(0, 1) }}</span>
            </span>
            <span class="profile-meta">
              <strong>{{ group.name }}</strong>
              <small>{{ group.accounts.length }} 个平台，{{ group.normalCount }} 个正常</small>
            </span>
          </button>
        </div>
        <div v-if="selectedProfileGroup" class="platform-picker">
          <label
            v-for="account in selectedProfileGroup.accounts"
            :key="account.id"
            :class="['platform-card', { disabled: account.status !== '正常' }]"
          >
            <el-checkbox
              v-model="publishForm.selectedPlatformTypes"
              :label="Number(account.type)"
              :disabled="account.status !== '正常'"
            >
              <span :class="['platform-badge', `platform-badge--${platformByType(account.type).iconClass}`]">
                <img :src="platformByType(account.type).iconSrc" :alt="`${platformByType(account.type).name} 图标`" />
              </span>
              <span class="platform-info">
                <strong>{{ platformByType(account.type).name }}</strong>
                <small>{{ account.name || account.filePath }}</small>
              </span>
              <el-tag :type="account.status === '正常' ? 'success' : 'danger'" size="small" round>
                {{ account.status }}
              </el-tag>
            </el-checkbox>
          </label>
        </div>
      </div>
      <el-empty v-else description="暂无可发布账号，请先到账号管理绑定平台账号" />
    </section>

    <main :class="['workspace-grid', { 'has-bili': hasBilibili }]">
      <section class="panel media-panel">
        <div class="section-head">
          <div>
            <h3>发布素材</h3>
          </div>
        </div>

        <el-upload
          class="drop-upload"
          :class="{ 'has-files': publishForm.fileList.length }"
          drag
          multiple
          accept="video/*"
          :action="`${apiBaseUrl}/upload`"
          :headers="authHeaders"
          :auto-upload="true"
          :show-file-list="false"
          :on-success="handleVideoUploadSuccess"
          :on-error="handleUploadError"
        >
          <div v-if="!publishForm.fileList.length" class="drop-empty-state">
            <el-icon class="drop-icon"><UploadFilled /></el-icon>
            <div class="drop-title">拖拽视频到这里</div>
            <div class="drop-subtitle">支持 mp4 / mov / webm 等常见视频格式</div>
            <el-button class="drop-library-button" @click.stop="openVideoLibrary">
              <el-icon><FolderOpened /></el-icon>
              从素材库选择
            </el-button>
          </div>
          <div v-else class="video-file-list">
            <div v-for="(file, index) in publishForm.fileList" :key="`${file.path}-${index}`" class="video-file-row">
              <span class="video-file-index">{{ index + 1 }}</span>
              <div class="video-file-copy">
                <strong :title="file.name">{{ file.name }}</strong>
                <small>{{ (file.size / 1024 / 1024).toFixed(2) }}MB</small>
              </div>
              <el-button size="small" type="danger" plain @click.stop="removeVideo(index)">移除</el-button>
            </div>
            <div class="video-drop-hint">
              <span>继续拖拽添加视频</span>
              <el-button size="small" @click.stop="openVideoLibrary">
                <el-icon><FolderOpened /></el-icon>
                素材库
              </el-button>
            </div>
          </div>
        </el-upload>
      </section>

      <section class="panel cover-panel">
        <div class="section-head">
          <div>
            <h3>平台封面</h3>
          </div>
        </div>

        <div class="cover-layout">
          <div
            v-for="spec in coverDisplaySpecs"
            :key="spec.ratio"
            :class="['cover-card', { 'is-inactive': !spec.active }]"
          >
            <div class="cover-spec">
              <span>{{ spec.active ? spec.platformNames.join(' / ') : '当前平台暂不需要' }}</span>
              <strong>{{ spec.ratio }}</strong>
            </div>
            <div class="cover-stage">
              <el-upload
                :class="['cover-drop', spec.ratioClass]"
                drag
                accept="image/*"
                :disabled="!spec.active"
                :action="`${apiBaseUrl}/upload`"
                :headers="authHeaders"
                :auto-upload="true"
                :show-file-list="false"
                :on-success="(response, file) => handleCoverUploaded(spec.ratio, response, file)"
                :on-error="handleCoverUploadError"
              >
                <div
                  v-if="spec.active && publishForm.coverVariants[spec.ratio]"
                  class="cover-thumb"
                >
                  <img
                    :src="publishForm.coverVariants[spec.ratio].url"
                    :alt="publishForm.coverVariants[spec.ratio].name"
                  />
                </div>
                <div v-else class="cover-empty">
                  <el-icon class="cover-empty-icon"><UploadFilled /></el-icon>
                  <span>{{ spec.active ? `${spec.ratio} 封面` : '无需上传' }}</span>
                </div>
              </el-upload>
            </div>
            <div class="cover-tools">
              <el-button size="small" :disabled="!spec.active" @click="openCoverLibrary(spec.ratio)">素材库</el-button>
              <el-button
                v-if="spec.active && publishForm.coverVariants[spec.ratio]"
                size="small"
                type="danger"
                plain
                @click="removeCoverVariant(spec.ratio)"
              >
                移除
              </el-button>
            </div>
          </div>
        </div>
      </section>

      <section class="panel content-panel">
        <div class="section-head">
          <div>
            <h3>发布内容</h3>
          </div>
          <el-tag type="info" round>{{ titleLimitHint }} · {{ topicLimitHint }}</el-tag>
        </div>

        <el-form label-position="top" @submit.prevent>
          <el-form-item label="作品文案">
            <el-input
              v-model="publishForm.title"
              class="title-textarea"
              type="textarea"
              :rows="3"
              :maxlength="selectedTitleLimit"
              show-word-limit
              clearable
              resize="none"
              placeholder="可选。抖音 / 视频号 / 小红书 / 快手会把这里作为作品描述，可只填写话题"
            />
          </el-form-item>

          <el-form-item label="话题">
            <div class="topic-editor">
              <div class="topic-tags">
                <el-tag
                  v-for="topic in publishForm.selectedTopics"
                  :key="topic"
                  closable
                  round
                  @close="removeTopic(topic)"
                >
                  #{{ topic }}
                </el-tag>
                <span v-if="!publishForm.selectedTopics.length" class="topic-placeholder">
                  暂无话题
                </span>
              </div>
              <div class="topic-input-row">
                <el-input
                  v-model="publishForm.topicDraft"
                  clearable
                  placeholder="输入话题后回车添加"
                  @keydown.enter.prevent="addTopic"
                />
                <el-button native-type="button" @click="addTopic">添加</el-button>
              </div>
            </div>
          </el-form-item>
        </el-form>
      </section>

      <section v-if="hasBilibili" class="panel bili-panel">
        <div class="section-head">
          <div>
            <h3>B站设置</h3>
          </div>
        </div>
        <el-form label-position="top">
          <el-form-item label="稿件标题" required>
            <el-input
              v-model="publishForm.biliTitle"
              maxlength="80"
              show-word-limit
              clearable
              placeholder="B站必填标题"
            />
          </el-form-item>
          <div class="form-grid">
            <el-form-item label="类型" required>
              <el-radio-group v-model="publishForm.biliType">
                <el-radio label="自制">自制</el-radio>
                <el-radio label="转载">转载</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="分区" required>
              <el-select v-model="publishForm.biliPartition" filterable clearable placeholder="请选择分区">
                <el-option
                  v-for="partition in biliPartitions"
                  :key="partition"
                  :label="partition"
                  :value="partition"
                />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="简介">
            <el-input
              v-model="publishForm.biliDesc"
              type="textarea"
              :rows="4"
              maxlength="2000"
              show-word-limit
              placeholder="填写B站简介"
            />
          </el-form-item>
        </el-form>
      </section>

      <section v-if="selectedPlatformAccounts.length" class="panel schedule-panel">
        <div class="section-head">
          <div>
            <h3>发布方式</h3>
          </div>
        </div>
        <ScheduleSettings
          v-model:schedule-enabled="publishForm.scheduleEnabled"
          v-model:videos-per-day="publishForm.videosPerDay"
          v-model:daily-times="publishForm.dailyTimes"
          v-model:start-days="publishForm.startDays"
          v-model:time-jitter-minutes="publishForm.timeJitterMinutes"
        />
      </section>
    </main>

    <section class="publish-action-bar">
      <div class="publish-action-copy">
        <strong>{{ debugDryRunEnabled ? '预发布检查' : '准备发布' }}</strong>
        <span>
          已选择 {{ selectedPlatformAccounts.length || 0 }} 个平台 ·
          {{ publishForm.fileList.length || 0 }} 个视频 ·
          {{ debugDryRunEnabled ? '停在最终发布前' : (publishForm.scheduleEnabled ? '定时发布' : '立即发布') }}
        </span>
      </div>
      <el-button type="primary" size="large" :loading="publishing" @click="confirmPublish">
        {{ debugDryRunEnabled ? '预发布检查' : '发布到' }} {{ selectedPlatformAccounts.length || 0 }} 个平台
      </el-button>
    </section>

    <el-alert
      v-if="publishStatus"
      class="floating-status"
      :title="publishStatus.message"
      :type="publishStatus.type"
      show-icon
      :closable="true"
      @close="publishStatus = null"
    />

    <el-dialog v-model="videoLibraryVisible" title="选择视频素材" width="820px">
      <div class="library-content">
        <el-empty v-if="videoMaterials.length === 0" description="暂无视频文件" />
        <el-checkbox-group v-else v-model="selectedVideoMaterialIds">
          <div class="material-list">
            <div v-for="material in videoMaterials" :key="material.id" class="material-item">
              <el-checkbox :label="material.id">
                <div class="material-info">
                  <strong>{{ material.filename }}</strong>
                  <small>{{ material.filesize }}MB · {{ material.upload_time }}</small>
                </div>
              </el-checkbox>
            </div>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="videoLibraryVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmVideoSelection">添加</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="coverLibraryVisible" title="选择封面素材" width="820px">
      <div class="library-content">
        <el-empty v-if="imageMaterials.length === 0" description="暂无图片文件" />
        <el-radio-group v-else v-model="selectedCoverMaterialId">
          <div class="material-list">
            <div v-for="material in imageMaterials" :key="material.id" class="material-item">
              <el-radio :label="material.id">
                <div class="material-info">
                  <strong>{{ material.filename }}</strong>
                  <small>{{ material.filesize }}MB · {{ material.upload_time }}</small>
                </div>
              </el-radio>
            </div>
          </div>
        </el-radio-group>
      </div>
      <template #footer>
        <el-button @click="coverLibraryVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmCoverSelection">使用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, UploadFilled } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi } from '@/api/account'
import { materialApi } from '@/api/material'
import { getPlatformConfig } from '@/utils/platformConfig'
import { validatePublishForm } from '@/utils/formValidation'
import ScheduleSettings from '@/components/publish/ScheduleSettings.vue'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
const debugDryRunEnabled = true
const GLOBAL_TOPIC_LIMIT = 5
const authHeaders = computed(() => ({
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`
}))

const accountStore = useAccountStore()
const appStore = useAppStore()
const materials = computed(() => appStore.materials)

const platformCatalog = [
  { type: 3, name: '抖音', iconSrc: '/platform-icons/douyin.ico', iconClass: 'douyin', color: '#111827' },
  { type: 2, name: '视频号', iconSrc: '/platform-icons/wechat-channels-logo.png', iconClass: 'channels', color: '#ff9f2f' },
  { type: 5, name: 'B站', iconSrc: '/platform-icons/bilibili.png', iconClass: 'bilibili', color: '#00a1d6' },
  { type: 1, name: '小红书', iconSrc: '/platform-icons/xiaohongshu.png', iconClass: 'xhs', color: '#ff2442' },
  { type: 4, name: '快手', iconSrc: '/platform-icons/kuaishou.ico', iconClass: 'kuaishou', color: '#ff8a00' }
]

const platformOrder = platformCatalog.reduce((order, platform, index) => {
  order[platform.type] = index
  return order
}, {})

const coverSpecs = {
  '3:4': { ratio: '3:4', cssRatio: '3 / 4' },
  '4:3': { ratio: '4:3', cssRatio: '4 / 3' },
  '16:9': { ratio: '16:9', cssRatio: '16 / 9' }
}

const platformCoverRatios = {
  1: ['3:4', '4:3'],
  2: ['3:4', '4:3'],
  3: ['3:4', '4:3'],
  4: ['3:4', '4:3'],
  5: ['4:3', '16:9']
}

const biliPartitions = [
  '影视', '娱乐', '音乐', '舞蹈', '动画', '绘画', '鬼畜', '游戏', '资讯', '知识',
  '人工智能', '科技数码', '汽车', '时尚美妆', '家装房产', '户外潮流', '健身',
  '体育运动', '手工', '美食', '小剧场', '旅游出行', '三农', '动物', '亲子',
  '健康', '情感', 'vlog', '生活兴趣', '生活经验'
]

const publishFormDefaults = {
  selectedProfileName: '',
  selectedPlatformTypes: [],
  fileList: [],
  title: '',
  selectedTopics: [],
  topicDraft: '',
  coverVariants: {},
  biliTitle: '',
  biliType: '自制',
  biliPartition: '',
  biliDesc: '',
  scheduleEnabled: false,
  timeJitterMinutes: 15,
  videosPerDay: 1,
  dailyTimes: ['10:00'],
  startDays: 0
}

const PUBLISH_DRAFT_STORAGE_KEY = 'auto-upload:publish-center:draft'

const createPublishFormDefaults = () => ({
  ...publishFormDefaults,
  selectedPlatformTypes: [],
  fileList: [],
  selectedTopics: [],
  coverVariants: {},
  dailyTimes: ['10:00']
})

const publishForm = reactive(createPublishFormDefaults())

const normalizeTopics = (topics, limit = GLOBAL_TOPIC_LIMIT) => {
  if (!Array.isArray(topics)) return []
  const seen = new Set()
  const normalized = []
  const maxCount = Math.max(0, Number(limit) || GLOBAL_TOPIC_LIMIT)
  topics.forEach(topic => {
    const text = String(topic || '').trim().replace(/^#+/, '')
    if (!text || seen.has(text) || normalized.length >= maxCount) return
    seen.add(text)
    normalized.push(text)
  })
  return normalized
}

const normalizePublishDraft = (draft) => ({
  ...createPublishFormDefaults(),
  ...(draft && typeof draft === 'object' ? draft : {}),
  selectedPlatformTypes: Array.isArray(draft?.selectedPlatformTypes) ? draft.selectedPlatformTypes.map(Number) : [],
  fileList: Array.isArray(draft?.fileList) ? draft.fileList : [],
  selectedTopics: normalizeTopics(draft?.selectedTopics),
  coverVariants: draft?.coverVariants && typeof draft.coverVariants === 'object' ? draft.coverVariants : {},
  dailyTimes: Array.isArray(draft?.dailyTimes) && draft.dailyTimes.length ? draft.dailyTimes : ['10:00'],
  videosPerDay: Number(draft?.videosPerDay) || 1,
  startDays: Number(draft?.startDays) || 0,
  timeJitterMinutes: Number(draft?.timeJitterMinutes ?? 15),
  scheduleEnabled: Boolean(draft?.scheduleEnabled)
})

const restorePublishDraft = () => {
  try {
    const raw = sessionStorage.getItem(PUBLISH_DRAFT_STORAGE_KEY)
    if (!raw) return
    Object.assign(publishForm, normalizePublishDraft(JSON.parse(raw)))
  } catch (error) {
    console.warn('恢复发布草稿失败', error)
    sessionStorage.removeItem(PUBLISH_DRAFT_STORAGE_KEY)
  }
}

const persistPublishDraft = () => {
  try {
    sessionStorage.setItem(PUBLISH_DRAFT_STORAGE_KEY, JSON.stringify(publishForm))
  } catch (error) {
    console.warn('保存发布草稿失败', error)
  }
}

restorePublishDraft()

const publishing = ref(false)
const publishStatus = ref(null)
const videoLibraryVisible = ref(false)
const coverLibraryVisible = ref(false)
const selectedVideoMaterialIds = ref([])
const selectedCoverMaterialId = ref(null)
const coverSelectingType = ref(null)

const platformByType = (type) => {
  return platformCatalog.find(item => item.type === Number(type)) || {
    type: Number(type),
    name: '未知平台',
    iconSrc: '',
    iconClass: 'unknown',
    color: '#8e8e93'
  }
}

const resolveAvatarUrl = (url) => {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  return `${apiBaseUrl}${url}`
}

const accountGroups = computed(() => {
  const map = new Map()
  accountStore.accounts.forEach(account => {
    const name = account.profileName || account.name || '未命名主体'
    if (!map.has(name)) {
      map.set(name, { name, avatarUrl: account.avatarUrl, accounts: [], normalCount: 0 })
    }
    const group = map.get(name)
    if (!group.avatarUrl && account.avatarUrl) group.avatarUrl = account.avatarUrl
    group.accounts.push({ ...account, type: Number(account.type) })
  })

  return Array.from(map.values()).map(group => {
    group.accounts.sort((a, b) => {
      return (platformOrder[a.type] ?? 99) - (platformOrder[b.type] ?? 99)
    })
    group.normalCount = group.accounts.filter(account => account.status === '正常').length
    return group
  })
})

const selectedProfileGroup = computed(() => {
  return accountGroups.value.find(group => group.name === publishForm.selectedProfileName)
})

const selectedPlatformAccounts = computed(() => {
  if (!selectedProfileGroup.value) return []
  return publishForm.selectedPlatformTypes
    .map(type => selectedProfileGroup.value.accounts.find(account => Number(account.type) === Number(type)))
    .filter(Boolean)
    .sort((a, b) => {
      return (platformOrder[Number(a.type)] ?? 99) - (platformOrder[Number(b.type)] ?? 99)
    })
})

const hasBilibili = computed(() => publishForm.selectedPlatformTypes.includes(5))

const requiredCoverSpecs = computed(() => {
  const orderedRatios = ['3:4', '4:3', '16:9']
  return orderedRatios
    .filter(ratio => publishForm.selectedPlatformTypes.some(type => {
      return (platformCoverRatios[Number(type)] || []).includes(ratio)
    }))
    .map(ratio => {
      const platformNames = publishForm.selectedPlatformTypes
        .filter(type => (platformCoverRatios[Number(type)] || []).includes(ratio))
        .map(type => platformByType(type).name)
      return {
        ...coverSpecs[ratio],
        platformNames
      }
    })
})

const coverDisplaySpecs = computed(() => {
  const requiredMap = new Map(requiredCoverSpecs.value.map(spec => [spec.ratio, spec]))
  return ['3:4', '4:3', '16:9'].map(ratio => {
    const requiredSpec = requiredMap.get(ratio)
    return {
      ...coverSpecs[ratio],
      ratioClass: `cover-drop--${ratio.replace(':', '-')}`,
      platformNames: requiredSpec?.platformNames || [],
      active: Boolean(requiredSpec)
    }
  })
})

const selectedPlatformConfigs = computed(() => {
  return publishForm.selectedPlatformTypes.map(type => getPlatformConfig(type))
})

const selectedTitleLimit = computed(() => {
  if (!selectedPlatformConfigs.value.length) return 80
  return Math.min(...selectedPlatformConfigs.value.map(config => config.titleLimit || 80))
})

const selectedTopicLimit = computed(() => {
  if (!selectedPlatformConfigs.value.length) return GLOBAL_TOPIC_LIMIT
  return Math.min(GLOBAL_TOPIC_LIMIT, ...selectedPlatformConfigs.value.map(config => config.topicLimit || GLOBAL_TOPIC_LIMIT))
})

const titleLimitHint = computed(() => `作品文案最多 ${selectedTitleLimit.value} 字，B站标题单独填写`)
const topicLimitHint = computed(() => `话题最多 ${selectedTopicLimit.value} 个`)

watch(selectedTopicLimit, (limit) => {
  if (publishForm.selectedTopics.length <= limit) return
  publishForm.selectedTopics = normalizeTopics(publishForm.selectedTopics, limit)
  ElMessage.warning(`已按当前平台限制保留前 ${limit} 个话题`)
})

const videoMaterials = computed(() => {
  const videoExtensions = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.m4v']
  return materials.value.filter(material => {
    const filename = (material.filename || '').toLowerCase()
    return videoExtensions.some(ext => filename.endsWith(ext))
  })
})

const imageMaterials = computed(() => {
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
  return materials.value.filter(material => {
    const filename = (material.filename || '').toLowerCase()
    return imageExtensions.some(ext => filename.endsWith(ext))
  })
})

onMounted(async () => {
  try {
    const res = await accountApi.getValidAccounts({ validate: 0 })
    if (res && res.code === 200 && Array.isArray(res.data)) {
      accountStore.setAccounts(res.data)
    }
  } catch (e) {
    console.warn('初始化获取账号失败', e)
  }
})

const selectProfile = (group) => {
  publishForm.selectedProfileName = group.name
  const normalTypes = group.accounts
    .filter(account => account.status === '正常')
    .map(account => Number(account.type))
  publishForm.selectedPlatformTypes = normalTypes.length
    ? normalTypes
    : group.accounts.map(account => Number(account.type))
}

watch(accountGroups, (groups) => {
  if (!groups.length) return
  const exists = groups.some(group => group.name === publishForm.selectedProfileName)
  if (!publishForm.selectedProfileName || !exists) {
    selectProfile(groups[0])
  }
}, { immediate: true })

watch(publishForm, persistPublishDraft, { deep: true, flush: 'sync' })

watch(() => publishForm.selectedPlatformTypes, () => {
  const validRatios = requiredCoverSpecs.value.map(spec => spec.ratio)
  Object.keys(publishForm.coverVariants).forEach(type => {
    if (!validRatios.includes(type)) {
      delete publishForm.coverVariants[type]
    }
  })
}, { deep: true })

const createUploadedFile = (response, file) => {
  const filePath = response.data.path || response.data
  const filename = String(filePath).split('/').pop()
  return {
    name: file.name,
    url: materialApi.getMaterialPreviewUrl(filename),
    path: filePath,
    size: file.size || 0,
    type: file.type || ''
  }
}

const handleVideoUploadSuccess = (response, file) => {
  if (response.code !== 200) {
    ElMessage.error(response.msg || '上传失败')
    return
  }
  publishForm.fileList.push(createUploadedFile(response, file))
  ElMessage.success('视频已添加')
}

const handleUploadError = () => {
  ElMessage.error('文件上传失败')
}

const handleCoverUploaded = (ratio, response, file) => {
  if (response.code !== 200) {
    ElMessage.error(response.msg || '封面上传失败')
    return
  }
  publishForm.coverVariants[ratio] = createUploadedFile(response, file)
  ElMessage.success(`${ratio} 封面已更新`)
}

const removeCoverVariant = (ratio) => {
  delete publishForm.coverVariants[ratio]
}

const removeVideo = (index) => {
  publishForm.fileList.splice(index, 1)
}

const ensureMaterialsLoaded = async () => {
  if (materials.value.length > 0) return true
  try {
    const response = await materialApi.getAllMaterials()
    if (response.code === 200) {
      appStore.setMaterials(response.data)
      return true
    }
  } catch (e) {
    console.error('获取素材列表出错:', e)
  }
  ElMessage.error('获取素材列表失败')
  return false
}

const openVideoLibrary = async () => {
  if (!await ensureMaterialsLoaded()) return
  selectedVideoMaterialIds.value = []
  videoLibraryVisible.value = true
}

const confirmVideoSelection = () => {
  if (!selectedVideoMaterialIds.value.length) {
    ElMessage.warning('请选择至少一个视频素材')
    return
  }
  selectedVideoMaterialIds.value.forEach(materialId => {
    const material = materials.value.find(item => item.id === materialId)
    if (!material) return
    const exists = publishForm.fileList.some(file => file.path === material.file_path)
    if (exists) return
    const filename = String(material.file_path || '').split('/').pop()
    publishForm.fileList.push({
      name: material.filename,
      url: materialApi.getMaterialPreviewUrl(filename),
      path: material.file_path,
      size: Number(material.filesize || 0) * 1024 * 1024,
      type: 'video/mp4'
    })
  })
  videoLibraryVisible.value = false
  ElMessage.success('已添加视频素材')
}

const openCoverLibrary = async (type) => {
  if (!await ensureMaterialsLoaded()) return
  coverSelectingType.value = type
  selectedCoverMaterialId.value = null
  coverLibraryVisible.value = true
}

const confirmCoverSelection = () => {
  const material = imageMaterials.value.find(item => item.id === selectedCoverMaterialId.value)
  if (!material) {
    ElMessage.warning('请选择一张封面')
    return
  }
  const filename = String(material.file_path || '').split('/').pop()
  const cover = {
    materialId: material.id,
    name: material.filename,
    url: materialApi.getMaterialPreviewUrl(filename),
    path: material.file_path,
    size: Number(material.filesize || 0) * 1024 * 1024,
    type: 'image/*'
  }
  publishForm.coverVariants[coverSelectingType.value] = cover
  coverLibraryVisible.value = false
  ElMessage.success('封面已选择')
}

const addTopic = () => {
  const topic = String(publishForm.topicDraft || '').trim().replace(/^#+/, '')
  if (!topic) return
  if (topic.length > 20) {
    ElMessage.warning('单个话题不能超过20字')
    return
  }
  if (publishForm.selectedTopics.includes(topic)) {
    publishForm.topicDraft = ''
    return
  }
  if (publishForm.selectedTopics.length >= selectedTopicLimit.value) {
    ElMessage.warning(topicLimitHint.value)
    return
  }
  publishForm.selectedTopics.push(topic)
  publishForm.topicDraft = ''
}

const removeTopic = (topic) => {
  publishForm.selectedTopics = publishForm.selectedTopics.filter(item => item !== topic)
}

const setScheduleEnabled = (enabled) => {
  publishForm.scheduleEnabled = enabled
  if (!enabled) {
    publishForm.videosPerDay = 1
    publishForm.dailyTimes = ['10:00']
    publishForm.startDays = 0
    publishForm.timeJitterMinutes = 15
  }
}

const buildPublishPayloads = () => {
  return selectedPlatformAccounts.value.map(account => {
    const type = Number(account.type)
    const platformTopicLimit = getPlatformConfig(type).topicLimit || GLOBAL_TOPIC_LIMIT
    const coverRatios = platformCoverRatios[type] || []
    const coverPaths = {}
    coverRatios.forEach(ratio => {
      const cover = publishForm.coverVariants[ratio]
      if (cover?.path) coverPaths[ratio] = cover.path
    })
    const platformCover = coverRatios
      .map(ratio => publishForm.coverVariants[ratio])
      .find(Boolean)
    const payload = {
      type,
      title: type === 5 ? publishForm.biliTitle : publishForm.title,
      tags: normalizeTopics(publishForm.selectedTopics, platformTopicLimit),
      fileList: publishForm.fileList.map(file => file.path),
      accountList: [account.filePath],
      enableTimer: publishForm.scheduleEnabled ? 1 : 0,
      videosPerDay: publishForm.scheduleEnabled ? publishForm.videosPerDay || 1 : 1,
      dailyTimes: publishForm.scheduleEnabled ? publishForm.dailyTimes || ['10:00'] : ['10:00'],
      startDays: publishForm.scheduleEnabled ? publishForm.startDays || 0 : 0,
      timeJitterMinutes: publishForm.scheduleEnabled ? publishForm.timeJitterMinutes || 0 : 0,
      debugDryRun: debugDryRunEnabled,
      debugDryRunHoldBrowser: true,
      category: 0
    }

    if (platformCover?.path) payload.coverPath = platformCover.path
    if (Object.keys(coverPaths).length) payload.coverPaths = coverPaths
    if (type === 5) {
      payload.biliTitle = publishForm.biliTitle
      payload.biliType = publishForm.biliType
      payload.biliPartition = publishForm.biliPartition
      payload.biliDesc = publishForm.biliDesc
    }

    return { account, payload }
  })
}

const ensurePublishReady = () => {
  const validation = validatePublishForm(publishForm)
  if (!validation.valid) return Object.values(validation.errors)[0]
  if (selectedPlatformAccounts.value.length !== publishForm.selectedPlatformTypes.length) {
    return '所选账号主体缺少对应的平台账号'
  }
  if (hasBilibili.value && !publishForm.biliTitle.trim()) {
    return '请填写B站稿件标题'
  }
  if (hasBilibili.value && !publishForm.biliPartition) {
    return '请选择B站分区'
  }
  return ''
}

const confirmPublish = async () => {
  if (publishing.value) return
  const error = ensurePublishReady()
  if (error) {
    publishStatus.value = { message: error, type: 'error' }
    ElMessage.error(error)
    return
  }

  publishing.value = true
  const results = []
  try {
    const payloadItems = buildPublishPayloads()
    if (payloadItems.length > 1) {
      const response = await fetch(`${apiBaseUrl}/postVideoBatch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders.value
        },
        body: JSON.stringify(payloadItems.map(item => item.payload))
      })
      const data = await response.json()
      const batchResults = Array.isArray(data.data?.results) ? data.data.results : []
      if (batchResults.length) {
        batchResults.forEach(result => {
          results.push({
            type: Number(result.type),
            ok: result.ok !== false,
            message: result.message || data.msg || '发布失败'
          })
        })
      } else {
        payloadItems.forEach(item => {
          results.push({
            type: Number(item.account.type),
            ok: data.code === 200,
            message: data.msg || '发布失败'
          })
        })
      }
    } else {
      for (const item of payloadItems) {
        const response = await fetch(`${apiBaseUrl}/postVideo`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...authHeaders.value
          },
          body: JSON.stringify(item.payload)
        })
        const data = await response.json()
        results.push({
          type: Number(item.account.type),
          ok: data.code === 200,
          message: data.msg || '发布失败'
        })
      }
    }

    const failures = results.filter(result => !result.ok)
    if (failures.length) {
      const message = failures.map(result => `${platformByType(result.type).name}: ${result.message}`).join('；')
      publishStatus.value = { message: `部分平台发布失败：${message}`, type: 'error' }
      ElMessage.error('部分平台发布失败')
      return
    }

    const successMessage = debugDryRunEnabled
      ? `预发布检查完成：${results.length} 个平台均已停在最终发布前`
      : `已提交 ${results.length} 个平台发布任务`
    publishStatus.value = { message: successMessage, type: 'success' }
    ElMessage.success(debugDryRunEnabled ? '预发布检查完成' : '发布任务已提交')
    resetContentOnly()
  } catch (e) {
    console.error('发布错误:', e)
    publishStatus.value = { message: '发布失败，请检查网络连接', type: 'error' }
    ElMessage.error('发布失败')
  } finally {
    publishing.value = false
  }
}

const resetContentOnly = () => {
  publishForm.fileList = []
  publishForm.title = ''
  publishForm.selectedTopics = []
  publishForm.topicDraft = ''
  publishForm.coverVariants = {}
  publishForm.biliTitle = ''
  publishForm.scheduleEnabled = false
  publishForm.videosPerDay = 1
  publishForm.dailyTimes = ['10:00']
  publishForm.startDays = 0
  publishForm.timeJitterMinutes = 15
}

const resetForm = () => {
  resetContentOnly()
  publishForm.biliType = '自制'
  publishForm.biliTitle = ''
  publishForm.biliPartition = ''
  publishForm.biliDesc = ''
  publishStatus.value = null
}
</script>

<style lang="scss" scoped>
.publish-center {
  min-width: 0;
  min-height: 100%;
  padding: 22px 28px 36px;
  color: #16181d;
  background:
    radial-gradient(circle at 50% 0%, rgba(255, 255, 255, 0.92), rgba(245, 246, 248, 0.92) 42%, #f4f5f7 100%);
}

.account-dock,
.panel {
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 18px;
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.055);
  backdrop-filter: blur(18px);
}

.dock-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;

  :deep(.el-button) {
    height: 36px;
    border-radius: 10px;
    font-weight: 650;
  }

  :deep(.el-tag) {
    height: 30px;
    padding: 0 12px;
    border-radius: 999px;
    background: rgba(248, 250, 252, 0.86);
  }
}

.account-dock {
  padding: 12px 16px 14px;
  margin-bottom: 12px;
}

.dock-head,
.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;

  h2,
  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 750;
    letter-spacing: 0;
  }
}

.dock-head {
  align-items: center;
  margin-bottom: 10px;
}

.account-dock-body {
  display: grid;
  grid-template-columns: minmax(166px, 0.22fr) minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
}

.account-rail {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  min-height: 100%;
}

.account-pill {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 66px;
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
  background: rgba(248, 250, 252, 0.58);
  border: 1px solid transparent;
  border-radius: 18px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;

  &:hover {
    transform: translateY(-1px);
    background: rgba(248, 250, 252, 0.82);
    box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  }

  &.active {
    background: rgba(244, 249, 255, 0.9);
    border-color: rgba(64, 158, 255, 0.18);
    box-shadow: inset 3px 0 0 rgba(64, 158, 255, 0.9), 0 14px 34px rgba(15, 23, 42, 0.055);
  }
}

.profile-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  overflow: hidden;
  place-items: center;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #4b5563, #111827);
  border-radius: 50%;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}

.profile-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;

  strong,
  small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    font-size: 13px;
  }

  small {
    font-size: 11px;
    color: #8a94a6;
  }
}

.profile-platforms {
  display: none;
}

.platform-picker {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  align-items: stretch;
  padding: 0;
  min-width: 0;
  min-height: 66px;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.platform-card {
  display: flex;
  flex: 1 1 0;
  align-items: center;
  min-width: 0;
  min-height: 66px;
  padding: 8px 10px;
  background: rgba(248, 250, 252, 0.62);
  border: 1px solid transparent;
  border-radius: 14px;
  transition: transform 0.16s ease, border-color 0.16s ease, background 0.16s ease, box-shadow 0.16s ease;

  &:hover {
    transform: translateY(-1px);
    background: rgba(255, 255, 255, 0.9);
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.045);
  }

  &.disabled {
    opacity: 0.58;
  }

  :deep(.el-checkbox) {
    display: flex;
    align-items: center;
    width: 100%;
    height: 100%;
    margin: 0;
  }

  :deep(.el-checkbox__label) {
    display: grid;
    grid-template-columns: 26px minmax(0, 1fr) auto;
    align-items: center;
    gap: 7px;
    width: 100%;
    height: 100%;
    min-width: 0;
    padding-left: 7px;
    padding-right: 0;
  }

  :deep(.el-checkbox__input) {
    align-self: center;
  }

  :deep(.el-tag) {
    position: static;
    height: 22px;
    padding: 0 8px;
    margin-left: 1px;
    font-size: 11px;
    line-height: 20px;
    transform: none;
  }
}

.platform-mark,
.platform-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  overflow: hidden;
  background: #fff;
  border-radius: 9px;
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08), 0 6px 14px rgba(15, 23, 42, 0.08);

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
  }
}

.platform-badge {
  width: 26px;
  height: 26px;
}

.platform-mark--channels img,
.platform-badge--channels img {
  width: 82%;
  height: 82%;
  object-fit: contain;
}

.platform-mark--bilibili img,
.platform-badge--bilibili img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.platform-info {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1px;
  min-width: 0;

  strong,
  small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    font-size: 12px;
    font-weight: 760;
    line-height: 1.25;
  }

  small {
    max-width: 100%;
    font-size: 11px;
    line-height: 1.25;
    color: #8a94a6;
  }
}

.publish-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 16px;
  padding: 14px 16px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 18px;
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.065);
  backdrop-filter: blur(18px);

  :deep(.el-button) {
    min-width: 176px;
    height: 42px;
    border-radius: 12px;
    font-weight: 760;
  }
}

.publish-action-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;

  strong {
    color: #16181d;
    font-size: 14px;
    font-weight: 780;
  }

  span {
    overflow: hidden;
    color: #8a94a6;
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(380px, 0.9fr) minmax(460px, 1.1fr);
  gap: 16px;
  align-items: start;

  &.has-bili {
    align-items: stretch;
  }
}

.panel {
  min-width: 0;
  padding: 17px;

  :deep(.el-input__wrapper),
  :deep(.el-textarea__inner),
  :deep(.el-select__wrapper) {
    border-radius: 12px;
    box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08) inset;
    transition: box-shadow 0.16s ease, background 0.16s ease;
  }

  :deep(.el-input__wrapper:hover),
  :deep(.el-textarea__inner:hover),
  :deep(.el-select__wrapper:hover) {
    box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.28) inset;
  }

  :deep(.el-form-item__label) {
    margin-bottom: 7px;
    color: #555f70;
    font-size: 12px;
    font-weight: 700;
  }

  :deep(.el-button) {
    border-radius: 10px;
    font-weight: 650;
  }
}

.media-panel,
.cover-panel {
  --publish-tray-height: 318px;
  grid-column: span 1;
  height: 386px;
  overflow: hidden;
}

.media-panel {
  display: flex;
  flex-direction: column;
}

.content-panel,
.bili-panel,
.schedule-panel {
  grid-column: 1 / -1;
}

.workspace-grid.has-bili {
  .content-panel,
  .bili-panel {
    display: flex;
    flex-direction: column;
    grid-column: span 1;
  }

  .content-panel :deep(.el-form),
  .bili-panel :deep(.el-form) {
    flex: 1;
  }
}

.drop-upload {
  display: flex;
  flex: 1;
  min-height: 0;
  width: 100%;

  :deep(.el-upload) {
    display: flex;
    width: 100%;
    flex: 1;
  }

  :deep(.el-upload-dragger) {
    display: flex;
    align-items: stretch;
    justify-content: center;
    width: 100%;
    height: var(--publish-tray-height);
    min-height: 0;
    padding: 16px;
    overflow-y: scroll;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
    background: rgba(248, 250, 252, 0.72);
    border-color: rgba(15, 23, 42, 0.08);
    border-radius: 16px;
    transition: background 0.18s ease, border-color 0.18s ease;

    &:hover {
      background: rgba(246, 251, 255, 0.92);
      border-color: rgba(64, 158, 255, 0.48);
    }

    &::-webkit-scrollbar {
      width: 8px;
    }

    &::-webkit-scrollbar-thumb {
      background: rgba(148, 163, 184, 0.42);
      border: 2px solid rgba(248, 250, 252, 0.72);
      border-radius: 999px;
    }

    &::-webkit-scrollbar-track {
      background: transparent;
    }
  }
}

.drop-empty-state {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.drop-icon {
  width: 42px;
  height: 42px;
  margin-bottom: 2px;
  color: #409eff;
}

.drop-title {
  font-size: 15px;
  font-weight: 750;
}

.drop-subtitle {
  margin-top: 6px;
  font-size: 12px;
  color: #8a94a6;
}

.drop-library-button {
  margin-top: 12px;
}

.video-file-list {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 8px;
  align-content: start;
}

.video-file-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  height: 48px;
  min-height: 48px;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 12px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.045);
}

.video-file-index {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  color: #2f6fcb;
  font-size: 12px;
  font-weight: 800;
  background: rgba(64, 158, 255, 0.12);
  border-radius: 9px;
}

.video-file-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
  text-align: left;

  strong,
  small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    color: #1d2433;
    font-size: 13px;
    font-weight: 750;
  }

  small {
    color: #8a94a6;
    font-size: 11px;
  }
}

.video-drop-hint {
  display: flex;
  min-height: 82px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  color: #8a94a6;
  background: rgba(255, 255, 255, 0.66);
  border: 1px dashed rgba(64, 158, 255, 0.28);
  border-radius: 14px;

  span {
    font-size: 12px;
    font-weight: 650;
  }
}

.cover-layout {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  height: var(--publish-tray-height);
  min-height: 0;
}

.cover-card {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  padding: 12px;
  background: rgba(248, 250, 252, 0.72);
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 15px;
  overflow: hidden;
  transition: background 0.16s ease, border-color 0.16s ease, opacity 0.16s ease;

  &.is-inactive {
    background: rgba(248, 250, 252, 0.42);
    border-color: rgba(15, 23, 42, 0.045);

    .cover-spec span,
    .cover-spec strong {
      color: #a4adba;
    }
  }
}

.cover-spec {
  display: flex;
  min-height: 45px;
  flex-direction: column;
  justify-content: flex-start;
  min-width: 0;
  gap: 3px;

  span {
    overflow: hidden;
    font-size: 12px;
    color: #409eff;
    font-weight: 750;
    line-height: 1.35;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    font-size: 20px;
    line-height: 1.1;
  }

  small {
    font-size: 12px;
    color: #8a94a6;
  }
}

.cover-stage {
  display: flex;
  flex: 1;
  min-height: 0;
  align-items: center;
  justify-content: center;
  padding: 6px 0 10px;
  overflow: hidden;
}

.cover-drop {
  display: flex;
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  max-height: 100%;
}

.cover-drop--3-4 {
  width: min(100%, 126px);
  aspect-ratio: 3 / 4;
}

.cover-drop--4-3 {
  width: min(100%, 190px);
  aspect-ratio: 4 / 3;
}

.cover-drop--16-9 {
  width: min(100%, 220px);
  aspect-ratio: 16 / 9;
}

:deep(.cover-drop .el-upload) {
  display: flex;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
}

:deep(.cover-drop .el-upload-dragger) {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.92);
  border-color: rgba(15, 23, 42, 0.08);
  border-radius: 13px;
}

:deep(.cover-drop.is-disabled .el-upload-dragger) {
  cursor: default;
  background: rgba(248, 250, 252, 0.6);
  border-color: rgba(15, 23, 42, 0.045);
}

:deep(.cover-thumb),
:deep(.cover-empty) {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  height: 100%;
  min-width: 0;
  margin: 0;
}

:deep(.cover-thumb img) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

:deep(.cover-empty) {
  display: flex;
  min-width: 74px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 8px;
  color: #8a94a6;
  background: linear-gradient(180deg, #ffffff, #f7f9fc);
}

:deep(.cover-empty span) {
  display: block;
  margin-top: 4px;
  font-size: 11px;
}

:deep(.cover-empty-icon) {
  width: 20px;
  height: 20px;
  color: #409eff;
}

:deep(.cover-tools) {
  display: flex;
  min-height: 32px;
  gap: 8px;
  align-items: center;
  justify-content: center;
}

.topic-editor {
  width: 100%;
}

.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-content: flex-start;
  min-height: 34px;
  max-height: 70px;
  padding: 2px 0;
  margin-bottom: 10px;
  overflow-y: auto;
}

.topic-placeholder {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 10px;
  color: #a0a8b5;
  font-size: 12px;
  background: rgba(248, 250, 252, 0.74);
  border: 1px dashed rgba(148, 163, 184, 0.32);
  border-radius: 999px;
}

.topic-input-row,
.form-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}

.form-grid {
  grid-template-columns: minmax(180px, 240px) 1fr;
}

.title-textarea {
  :deep(.el-textarea__inner) {
    min-height: 92px !important;
    line-height: 1.55;
  }
}

.schedule-panel {
  :deep(.schedule-section) {
    margin-bottom: 0;
  }

  :deep(.schedule-section h3) {
    display: none;
  }
}

.floating-status {
  position: sticky;
  bottom: 16px;
  z-index: 6;
  max-width: 980px;
  margin: 16px auto 0;
  box-shadow: 0 16px 34px rgba(15, 23, 42, 0.1);
}

.library-content {
  max-height: 420px;
  overflow: auto;
}

.material-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.material-item {
  padding: 12px;
  background: rgba(248, 250, 252, 0.72);
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 12px;

  :deep(.el-checkbox),
  :deep(.el-radio) {
    width: 100%;
    height: auto;
  }
}

.material-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;

  strong {
    color: #111827;
  }

  small {
    color: #8a94a6;
  }
}

@media (max-width: 980px) {
  .workspace-grid,
  .account-dock-body,
  .form-grid,
  .topic-input-row {
    grid-template-columns: 1fr;
  }

  .account-pill {
    min-height: 72px;
  }

  .platform-picker {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    min-height: 0;
  }

  .cover-layout {
    grid-template-columns: repeat(3, minmax(150px, 1fr));
    grid-template-rows: 1fr;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .cover-card:nth-child(3) {
    grid-column: auto;
  }

  .dock-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .dock-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .publish-action-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .publish-action-bar :deep(.el-button) {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .publish-center {
    padding: 14px;
  }

  .account-pill {
    grid-template-columns: 36px minmax(0, 1fr);
  }
}
</style>
