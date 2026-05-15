import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAccountStore = defineStore('account', () => {
  // 存储所有账号信息
  const accounts = ref([])
  
  // 平台类型映射
  const platformTypes = {
    1: '小红书',
    2: '视频号',
    3: '抖音',
    4: '快手',
    5: 'B站'
  }

  const fallbackAvatarColors = [
    '#3b82f6',
    '#14b8a6',
    '#8b5cf6',
    '#f97316',
    '#0f766e',
    '#64748b'
  ]

  const getStableAvatarColor = (value) => {
    const seed = String(value || '')
      .split('')
      .reduce((sum, char) => sum + char.charCodeAt(0), 0)
    return fallbackAvatarColors[seed % fallbackAvatarColors.length]
  }

  const normalizeStatus = (status) => {
    if (status === 1 || status === '1' || status === true || status === '正常') {
      return '正常'
    }
    if (status === 0 || status === '0' || status === false || status === '异常') {
      return '异常'
    }
    return status ? String(status) : '异常'
  }
  
  // 设置账号列表
  const setAccounts = (accountsData) => {
    // 转换后端返回的数据格式为前端使用的格式
    accounts.value = accountsData.map(item => {
      const isArrayRow = Array.isArray(item)
      const id = isArrayRow ? item[0] : item.id
      const type = isArrayRow ? item[1] : item.type
      const filePath = isArrayRow ? item[2] : item.filePath
      const userName = isArrayRow ? item[3] : item.userName
      const status = isArrayRow ? item[4] : item.status
      const profileName = isArrayRow ? item[5] : item.profileName
      const avatarPath = isArrayRow ? item[6] : item.avatarPath
      const avatarUrl = isArrayRow ? null : item.avatarUrl
      const avatarUpdatedAt = isArrayRow ? null : item.avatarUpdatedAt
      const fallbackName = userName || profileName || platformTypes[type] || '?'
      return {
        id,
        type,
        filePath,
        name: userName,
        profileName: profileName || userName,
        status: normalizeStatus(status),
        platform: platformTypes[type] || '未知',
        avatarPath,
        avatarUrl,
        avatarUpdatedAt,
        avatarText: String(fallbackName).slice(0, 1).toUpperCase(),
        avatarColor: getStableAvatarColor(fallbackName)
      }
    })
  }
  
  // 添加账号
  const addAccount = (account) => {
    accounts.value.push(account)
  }
  
  // 更新账号
  const updateAccount = (id, updatedAccount) => {
    const index = accounts.value.findIndex(acc => acc.id === id)
    if (index !== -1) {
      accounts.value[index] = { ...accounts.value[index], ...updatedAccount }
    }
  }
  
  // 删除账号
  const deleteAccount = (id) => {
    accounts.value = accounts.value.filter(acc => acc.id !== id)
  }
  
  // 根据平台获取账号
  const getAccountsByPlatform = (platform) => {
    return accounts.value.filter(acc => acc.platform === platform)
  }
  
  return {
    accounts,
    setAccounts,
    addAccount,
    updateAccount,
    deleteAccount,
    getAccountsByPlatform
  }
})
