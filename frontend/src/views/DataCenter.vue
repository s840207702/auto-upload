<template>
  <div class="data-center">
    <div class="page-header">
      <h1>数据</h1>
      <p>当前一键包优先保证账号登录、素材管理和发布流程，本地版暂未接入平台数据同步。</p>
    </div>

    <div class="status-panel">
      <div class="status-main">
        <div class="status-title">本地数据概览</div>
        <div class="status-desc">这里展示的是本机一键包可直接统计的数据，不代表平台后台真实播放量。</div>
      </div>
      <el-button type="primary" @click="goPublish">去发布中心</el-button>
    </div>

    <div class="metric-grid">
      <div v-for="item in metrics" :key="item.label" class="metric-item">
        <div class="metric-value">{{ item.value }}</div>
        <div class="metric-label">{{ item.label }}</div>
      </div>
    </div>

    <div class="empty-state">
      <el-empty description="平台播放、点赞、评论等数据需要后续接入各平台后台或开放接口" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi } from '@/api/account'
import { materialApi } from '@/api/material'

const router = useRouter()
const accountStore = useAccountStore()
const appStore = useAppStore()

const metrics = computed(() => [
  { label: '本地账号', value: accountStore.accounts.length },
  { label: '本地素材', value: appStore.materials.length },
  { label: '已接入平台', value: 5 },
  { label: '数据同步', value: '未接入' }
])

const goPublish = () => {
  router.push('/publish-center')
}

onMounted(async () => {
  try {
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
  } catch (error) {
    console.warn('数据概览加载失败:', error)
  }
})
</script>

<style lang="scss" scoped>
.data-center {
  padding: 24px;

  .page-header {
    margin-bottom: 24px;

    h1 {
      margin: 0 0 8px;
      color: #1d1d1f;
      font-size: 28px;
      font-weight: 700;
    }

    p {
      margin: 0;
      color: #6e6e73;
      font-size: 14px;
    }
  }

  .status-panel {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
    padding: 20px 22px;
    background: #fff;
    border: 1px solid #e8edf3;
    border-radius: 14px;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
  }

  .status-title {
    color: #1d1d1f;
    font-size: 17px;
    font-weight: 650;
  }

  .status-desc {
    margin-top: 6px;
    color: #6e6e73;
    font-size: 13px;
  }

  .metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-bottom: 16px;
  }

  .metric-item {
    padding: 18px 20px;
    background: #fff;
    border: 1px solid #e8edf3;
    border-radius: 14px;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
  }

  .metric-value {
    color: #1d1d1f;
    font-size: 26px;
    font-weight: 750;
  }

  .metric-label {
    margin-top: 6px;
    color: #6e6e73;
    font-size: 13px;
  }

  .empty-state {
    padding: 36px 0;
    background: #fff;
    border: 1px solid #e8edf3;
    border-radius: 14px;
  }
}
</style>
