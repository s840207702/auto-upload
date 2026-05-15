<template>
  <div class="dashboard">
    <div class="page-header">
      <div>
        <h1>非丨自媒体一键分发</h1>
        <p>本地化多平台视频分发工作台</p>
      </div>
    </div>
    
    <div class="dashboard-content">
      <el-row :gutter="20">
        <!-- 账号统计卡片 -->
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-card-content">
              <div class="stat-icon">
                <el-icon><User /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ accountStats.total }}</div>
                <div class="stat-label">账号总数</div>
              </div>
            </div>
            <div class="stat-footer">
              <div class="stat-detail">
                <span>正常: {{ accountStats.normal }}</span>
                <span>异常: {{ accountStats.abnormal }}</span>
              </div>
            </div>
          </el-card>
        </el-col>
        
        <!-- 平台统计卡片 -->
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-card-content">
              <div class="stat-icon platform-icon">
                <el-icon><Platform /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ platformStats.total }}</div>
                <div class="stat-label">平台总数</div>
              </div>
            </div>
            <div class="stat-footer">
              <div class="stat-detail">
                <el-tooltip
                  v-for="item in platformStats.items"
                  :key="item.name"
                  :content="`${item.name}账号`"
                  placement="top"
                >
                  <el-tag size="small" :type="item.type">{{ item.count }}</el-tag>
                </el-tooltip>
              </div>
            </div>
          </el-card>
        </el-col>
        
        <!-- 任务统计卡片 -->
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-card-content">
              <div class="stat-icon task-icon">
                <el-icon><List /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ taskStats.total }}</div>
                <div class="stat-label">任务总数</div>
              </div>
            </div>
            <div class="stat-footer">
              <div class="stat-detail">
                <span>完成: {{ taskStats.completed }}</span>
                <span>进行中: {{ taskStats.inProgress }}</span>
                <span>失败: {{ taskStats.failed }}</span>
              </div>
            </div>
          </el-card>
        </el-col>
        
        <!-- 内容统计卡片 -->
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-card-content">
              <div class="stat-icon content-icon">
                <el-icon><Document /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ contentStats.total }}</div>
                <div class="stat-label">内容总数</div>
              </div>
            </div>
            <div class="stat-footer">
              <div class="stat-detail">
                <span>视频: {{ contentStats.video }}</span>
                <span>图片: {{ contentStats.image }}</span>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
      
      <!-- 快捷操作区域 -->
      <div class="quick-actions">
        <h2>快捷操作</h2>
        <el-row :gutter="20">
          <el-col :span="6">
            <el-card class="action-card" @click="navigateTo('/account-management')">
              <div class="action-icon">
                <el-icon><UserFilled /></el-icon>
              </div>
              <div class="action-title">账号管理</div>
              <div class="action-desc">管理所有平台账号</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card class="action-card" @click="navigateTo('/material-management')">
              <div class="action-icon">
                <el-icon><Upload /></el-icon>
              </div>
              <div class="action-title">内容上传</div>
              <div class="action-desc">上传视频和图文内容</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card class="action-card" @click="navigateTo('/publish-center')">
              <div class="action-icon">
                <el-icon><Timer /></el-icon>
              </div>
              <div class="action-title">定时发布</div>
              <div class="action-desc">设置内容发布时间</div>
            </el-card>
          </el-col>
        </el-row>
      </div>
      
      <!-- 最近任务列表 -->
      <div class="recent-tasks">
        <div class="section-header">
          <h2>最近任务</h2>
          <el-button text disabled>本地版</el-button>
        </div>
        
        <el-table v-if="recentTasks.length" :data="recentTasks" style="width: 100%">
          <el-table-column prop="title" label="任务名称" width="250" />
          <el-table-column prop="platform" label="平台" width="120">
            <template #default="scope">
              <el-tag
                :type="getPlatformTagType(scope.row.platform)"
                effect="plain"
              >
                {{ scope.row.platform }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="account" label="账号" width="150" />
          <el-table-column prop="createTime" label="创建时间" width="180" />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="scope">
              <el-tag
                :type="getStatusTagType(scope.row.status)"
                effect="plain"
              >
                {{ scope.row.status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="empty-tasks">
          <el-empty description="暂无本地任务记录。当前一键包优先记录账号和素材，平台发布结果以后再接入。">
            <el-button type="primary" @click="navigateTo('/publish-center')">去发布中心</el-button>
          </el-empty>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  User, UserFilled, Platform, List, Document, 
  Upload, Timer
} from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi } from '@/api/account'
import { materialApi } from '@/api/material'

const router = useRouter()
const accountStore = useAccountStore()
const appStore = useAppStore()

// 账号统计数据
const accountStats = computed(() => {
  const total = accountStore.accounts.length
  const normal = accountStore.accounts.filter(account => account.status === '正常').length
  return {
    total,
    normal,
    abnormal: total - normal
  }
})

// 平台统计数据
const platformStats = computed(() => {
  const platformTypes = [
    { name: '快手', type: 'success' },
    { name: '抖音', type: 'danger' },
    { name: '视频号', type: 'warning' },
    { name: '小红书', type: 'info' },
    { name: 'B站', type: 'primary' }
  ]
  const items = platformTypes.map(item => ({
    ...item,
    count: accountStore.accounts.filter(account => account.platform === item.name).length
  }))

  return {
    total: items.filter(item => item.count > 0).length,
    items
  }
})

// 任务统计数据
const taskStats = computed(() => ({
  total: recentTasks.value.length,
  completed: recentTasks.value.filter(task => task.status === '已完成').length,
  inProgress: recentTasks.value.filter(task => task.status === '进行中').length,
  failed: recentTasks.value.filter(task => task.status === '已失败').length
}))

// 内容统计数据
const contentStats = computed(() => {
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
  const videoExtensions = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.m4v']
  const materials = appStore.materials
  return {
    total: materials.length,
    video: materials.filter(item => videoExtensions.some(ext => String(item.filename || '').toLowerCase().endsWith(ext))).length,
    image: materials.filter(item => imageExtensions.some(ext => String(item.filename || '').toLowerCase().endsWith(ext))).length
  }
})

// 最近任务数据
const recentTasks = ref([])

// 根据平台获取标签类型
const getPlatformTagType = (platform) => {
  const typeMap = {
    '快手': 'success',
    '抖音': 'danger',
    '视频号': 'warning',
    '小红书': 'info'
  }
  return typeMap[platform] || 'info'
}

// 根据状态获取标签类型
const getStatusTagType = (status) => {
  const typeMap = {
    '已完成': 'success',
    '进行中': 'warning',
    '待执行': 'info',
    '已失败': 'danger'
  }
  return typeMap[status] || 'info'
}

// 导航到指定路由
const navigateTo = (path) => {
  router.push(path)
}

onMounted(async () => {
  if (!accountStore.accounts.length) {
    const accounts = await accountApi.getValidAccounts({ validate: 0 })
    if (accounts.code === 200 && Array.isArray(accounts.data)) {
      accountStore.setAccounts(accounts.data)
    }
  }

  if (!appStore.materials.length) {
    const materials = await materialApi.getAllMaterials()
    if (materials.code === 200 && Array.isArray(materials.data)) {
      appStore.setMaterials(materials.data)
    }
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.dashboard {
  .page-header {
    margin-bottom: 20px;
    
    h1 {
      font-size: 24px;
      color: $text-primary;
      margin: 0;
    }

    p {
      margin: 8px 0 0;
      color: $text-secondary;
      font-size: 13px;
    }
  }
  
  .dashboard-content {
    .stat-card {
      height: 140px;
      margin-bottom: 20px;
      
      .stat-card-content {
        display: flex;
        align-items: center;
        margin-bottom: 15px;
        
        .stat-icon {
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background-color: rgba($primary-color, 0.1);
          display: flex;
          justify-content: center;
          align-items: center;
          margin-right: 15px;
          
          .el-icon {
            font-size: 30px;
            color: $primary-color;
          }
          
          &.platform-icon {
            background-color: rgba($success-color, 0.1);
            
            .el-icon {
              color: $success-color;
            }
          }
          
          &.task-icon {
            background-color: rgba($warning-color, 0.1);
            
            .el-icon {
              color: $warning-color;
            }
          }
          
          &.content-icon {
            background-color: rgba($info-color, 0.1);
            
            .el-icon {
              color: $info-color;
            }
          }
        }
        
        .stat-info {
          .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: $text-primary;
            line-height: 1.2;
          }
          
          .stat-label {
            font-size: 14px;
            color: $text-secondary;
          }
        }
      }
      
      .stat-footer {
        border-top: 1px solid $border-lighter;
        padding-top: 10px;
        
        .stat-detail {
          display: flex;
          justify-content: space-between;
          color: $text-secondary;
          font-size: 13px;
          
          .el-tag {
            margin-right: 5px;
          }
        }
      }
    }
    
    .quick-actions {
      margin: 20px 0 30px;
      
      h2 {
        font-size: 18px;
        margin-bottom: 15px;
        color: $text-primary;
      }
      
      .action-card {
        height: 160px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.3s;
        
        &:hover {
          transform: translateY(-5px);
          box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
        }
        
        .action-icon {
          width: 50px;
          height: 50px;
          border-radius: 50%;
          background-color: rgba($primary-color, 0.1);
          display: flex;
          justify-content: center;
          align-items: center;
          margin-bottom: 15px;
          
          .el-icon {
            font-size: 24px;
            color: $primary-color;
          }
        }
        
        .action-title {
          font-size: 16px;
          font-weight: bold;
          color: $text-primary;
          margin-bottom: 5px;
        }
        
        .action-desc {
          font-size: 13px;
          color: $text-secondary;
          text-align: center;
        }
      }
    }
    
    .recent-tasks {
      margin-top: 30px;
      
      .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
        
        h2 {
          font-size: 18px;
          color: $text-primary;
          margin: 0;
        }
      }

      .empty-tasks {
        padding: 34px 0;
        background: #fff;
        border-radius: 4px;
      }
    }
  }
}
</style>
