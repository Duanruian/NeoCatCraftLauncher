<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import TitleBar from './components/TitleBar.vue'
import Sidebar from './components/Sidebar.vue'
import InstanceView from './views/InstanceView.vue'
import DownloadView from './views/DownloadView.vue'
import JavaView from './views/JavaView.vue'
import SettingsView from './views/SettingsView.vue'
import TaskDock from './components/TaskDock.vue'
import ToastHost from './components/ToastHost.vue'
import AccountDialog from './components/AccountDialog.vue'
import SkinPreviewDialog from './components/SkinPreviewDialog.vue'
import NewInstanceDialog from './components/NewInstanceDialog.vue'
import InstanceSettingsDialog from './components/InstanceSettingsDialog.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ContentDetailsDialog from './components/ContentDetailsDialog.vue'
import ModDependenciesDialog from './components/ModDependenciesDialog.vue'
import OnboardingWizard from './components/OnboardingWizard.vue'
import { useLauncher } from './composables/useLauncher'
import { useActionFeedback } from './composables/useActionFeedback'

const {
  state,
  activeAccount,
  initialize,
  navigate,
  acceptDisclaimer,
  safe,
  openNewInstance,
} = useLauncher()

const close = () => window.neo?.window.close()
const actionFeedback = useActionFeedback()
const activeNav = computed(() => {
  if (state.view === 'java') return 'settings'
  if (state.view === 'modpacks') return 'download'
  return state.view
})

let closeSubscription = null
onMounted(() => {
  actionFeedback.start()
  safe(initialize)
  closeSubscription = window.neo?.onCloseRequest?.(() => {
    document.body.classList.add('is-closing')
    window.setTimeout(() => window.neo?.closeReady(), window.__neoCloseAnim === false ? 30 : 460)
  })
})
onBeforeUnmount(() => {
  actionFeedback.stop()
  closeSubscription?.()
})
</script>

<template>
  <div class="app-frame" :class="{ 'is-ready': state.ready }">
    <div class="baka-backdrop" aria-hidden="true">
      <span class="baka-orb baka-orb--blue"></span>
      <span class="baka-orb baka-orb--orange"></span>
      <span class="baka-grid"></span>
      <span class="baka-stripe"></span>
    </div>

    <TitleBar :state="state" />

    <div class="app-workspace">
      <Sidebar :state="state" :account="activeAccount" :active-nav="activeNav" @navigate="navigate" />

      <main class="main-stage">
        <Transition name="view-swap" mode="out-in">
        <InstanceView v-if="state.view === 'instance'" :key="state.selectedId || 'instance'" />
        <DownloadView v-else-if="state.view === 'download'" key="download" />
        <JavaView v-else-if="state.view === 'java'" key="java" />
        <SettingsView v-else-if="state.view === 'settings'" key="settings" />
        <section v-else class="empty-stage">
          <div class="empty-card">
            <span class="empty-card__bubble">MC</span>
            <span class="eyebrow">Welcome to NeoCatCraft</span>
            <h1>准备好进入方块世界了吗？</h1>
            <p>在左侧选择一个实例，或创建新的冒险配置。每个实例都会独立保存模组、存档和设置。</p>
            <div class="empty-actions">
              <button class="baka-button baka-button--primary" @click="openNewInstance()">
                新建实例
              </button>
              <button class="baka-button" @click="navigate('download')">浏览下载中心</button>
            </div>
          </div>
        </section>
        </Transition>
      </main>
    </div>

    <TaskDock />
    <ToastHost />

    <AccountDialog v-if="state.modal === 'account'" />
    <SkinPreviewDialog v-if="state.modal === 'skin-preview'" />
    <NewInstanceDialog v-if="state.modal === 'new-instance'" />
    <InstanceSettingsDialog v-if="state.modal === 'instance-settings'" />
    <ConfirmDialog v-if="state.modal === 'confirm'" />
    <ContentDetailsDialog v-if="state.modal === 'content-details'" />
    <ModDependenciesDialog v-if="state.modal === 'mod-dependencies'" />

    <OnboardingWizard v-if="state.wizard.open" />

    <div v-if="state.modal === 'disclaimer'" class="overlay">
      <div class="dialog disclaimer-dialog">
        <span class="dialog-kicker">FIRST STEP</span>
        <h2>开始前的小约定</h2>
        <p>
          NeoCatCraftLauncher 是免费的非官方 Minecraft 启动器，与 Mojang、Microsoft
          没有隶属关系。启动器不提供游戏、账号或服务器付费服务。
        </p>
        <div class="notice-row">
          <span>请使用自己拥有授权的游戏副本</span>
          <span>离线账户仅用于本地或获授权服务器</span>
          <span>第三方模组与整合包版权归原作者</span>
        </div>
        <div class="dialog-actions dialog-actions--split">
          <button class="text-button" @click="close">退出</button>
          <button class="baka-button baka-button--primary" @click="safe(acceptDisclaimer)">
            我已阅读并同意
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
