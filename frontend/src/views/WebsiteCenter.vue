<template>
  <div class="website-center">
    <div class="page-header">
      <h1>网站</h1>
      <p>常用创作者后台入口。账号管理里的“作品查看”会用已登录账号打开对应后台。</p>
    </div>

    <div class="link-grid">
      <a
        v-for="site in sites"
        :key="site.name"
        class="site-item"
        :href="site.url"
        target="_blank"
        rel="noreferrer"
      >
        <div>
          <div class="site-name">{{ site.name }}</div>
          <div class="site-desc">{{ site.desc }}</div>
        </div>
        <el-icon><Right /></el-icon>
      </a>
    </div>
  </div>
</template>

<script setup>
import { Right } from '@element-plus/icons-vue'

const sites = [
  {
    name: '抖音创作者中心',
    desc: '作品管理、发布记录、账号状态',
    url: 'https://creator.douyin.com/creator-micro/content/manage'
  },
  {
    name: '小红书创作服务平台',
    desc: '笔记管理、数据查看、发布入口',
    url: 'https://creator.xiaohongshu.com/new/note-manager'
  },
  {
    name: '视频号助手',
    desc: '视频号作品列表和发布管理',
    url: 'https://channels.weixin.qq.com/platform/post/list'
  },
  {
    name: '快手创作者服务平台',
    desc: '作品发布和内容管理',
    url: 'https://cp.kuaishou.com/article/publish/video'
  },
  {
    name: 'B站创作中心',
    desc: '稿件管理和内容发布',
    url: 'https://member.bilibili.com/platform/upload-manager/article'
  }
]
</script>

<style lang="scss" scoped>
.website-center {
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

  .link-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }

  .site-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 88px;
    padding: 18px 20px;
    color: inherit;
    text-decoration: none;
    background: #fff;
    border: 1px solid #e8edf3;
    border-radius: 14px;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;

    &:hover {
      border-color: #b8cdf8;
      box-shadow: 0 14px 34px rgba(37, 99, 235, 0.08);
      transform: translateY(-1px);
    }

    .site-name {
      color: #1d1d1f;
      font-size: 16px;
      font-weight: 650;
    }

    .site-desc {
      margin-top: 6px;
      color: #6e6e73;
      font-size: 13px;
    }

    .el-icon {
      flex: 0 0 auto;
      color: #8a8f98;
    }
  }
}
</style>
