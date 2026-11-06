<script setup>
import { ref } from 'vue'
import BaseModal from './BaseModal.vue'
import MicrosoftLogo from './MicrosoftLogo.vue'
import { useLauncher } from '../composables/useLauncher'

const launcher = useLauncher()
const {
  state,
  activeAccount,
  closeModal,
  safe,
  beginMicrosoftLogin,
  openSkinPreview,
  selectAccount,
  offlineLogin,
  removeAccount,
  toast,
} = launcher
const offlineName = ref('')

function copyCode() {
  navigator.clipboard?.writeText(state.deviceFlow.code).then(() => toast('设备代码已复制', 'ok'))
}
function openLink() {
  window.neo?.openExternal(state.deviceFlow.uri)
}
function submitOffline() {
  if (!offlineName.value.trim()) {
    toast('请输入离线账户名称', 'error')
    return
  }
  safe(async () => {
    await offlineLogin(offlineName.value.trim())
    offlineName.value = ''
  })
}
</script>

<template>
  <BaseModal title="玩家账户" subtitle="账号状态会同步到启动检查和游戏进程。" @close="closeModal()">
    <div class="account-list">
      <article
        v-for="account in state.accounts"
        :key="account.uuid"
        class="account-item"
        :class="{ active: account.active }"
      >
        <span class="account-avatar" :class="{ 'account-avatar--microsoft': account.type === 'microsoft' }">
          <MicrosoftLogo v-if="account.type === 'microsoft'" />
          <template v-else>{{ (account.name || '?').slice(0, 1) }}</template>
        </span>
        <div>
          <strong>{{ account.name }}</strong>
          <small>{{ account.type === 'microsoft' ? '微软正版' : '离线账户' }}</small>
        </div>
        <span v-if="account.active" class="soft-tag">当前</span>
        <button v-else class="text-button" @click="safe(() => selectAccount(account.uuid))">切换</button>
        <button class="text-button danger" @click="safe(() => removeAccount(account))">移除</button>
      </article>
      <div v-if="!state.accounts.length" class="empty-inline">
        <strong>还没有账户</strong>
        <p>登录微软正版，或创建一个本地离线账户。</p>
      </div>
    </div>

    <button
      v-if="activeAccount?.type === 'microsoft'"
      class="account-skin-preview"
      @click="safe(() => openSkinPreview(activeAccount))"
    >
      <span class="account-skin-preview__icon">3D</span>
      <span>
        <strong>预览当前正版皮肤</strong>
        <small>从 Mojang 同步最新纹理并旋转查看</small>
      </span>
      <em>→</em>
    </button>

    <section class="account-login-panel">
      <div class="login-panel-head">
        <span class="login-panel-icon login-panel-icon--microsoft">
          <MicrosoftLogo />
        </span>
        <div>
          <strong>Microsoft 正版登录</strong>
          <small>mcauth3 · Device Code Flow</small>
        </div>
      </div>
      <p>点击后获取一次性代码，在浏览器完成授权。启动器会自动检查结果，无需粘贴回调地址。</p>
      <button
        v-if="!state.deviceFlow.active"
        class="baka-button baka-button--primary baka-button--block"
        @click="safe(beginMicrosoftLogin)"
      >
        获取设备代码并登录
      </button>
      <div v-else class="device-flow-card">
        <small>{{ state.deviceFlow.status }}</small>
        <code>{{ state.deviceFlow.code || '••••••••' }}</code>
        <p>{{ state.deviceFlow.message || '请在浏览器中输入上面的代码。' }}</p>
        <div class="device-actions">
          <button class="baka-button baka-button--mini" @click="copyCode">复制代码</button>
          <button class="baka-button baka-button--mini baka-button--plain" @click="openLink">打开登录页</button>
        </div>
      </div>
    </section>

    <section class="account-login-panel account-login-panel--offline">
      <div class="login-panel-head">
        <span class="login-panel-icon">O</span>
        <div>
          <strong>离线账户</strong>
          <small>本地或已授权的离线服务器</small>
        </div>
      </div>
      <form class="inline-action" @submit.prevent="submitOffline">
        <input v-model="offlineName" class="baka-input" placeholder="输入 3-16 位玩家名称" />
        <button class="baka-button baka-button--mini">创建并登录</button>
      </form>
    </section>
  </BaseModal>
</template>
