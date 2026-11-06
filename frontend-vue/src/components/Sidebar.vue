<script setup>
import { computed } from 'vue'
import { useLauncher } from '../composables/useLauncher'
import InstanceIcon from './InstanceIcon.vue'
import MicrosoftLogo from './MicrosoftLogo.vue'

const props = defineProps({
  state: { type: Object, required: true },
  account: { type: Object, default: null },
  activeNav: { type: String, default: '' },
})
const emit = defineEmits(['navigate'])
const { filteredInstances, loaderLabel, openSkinPreview } = useLauncher()

const activeTasks = computed(() => props.state.tasks.filter((task) => task.state === 'running').length)

function openAccount() {
  useLauncher().showModal('account')
}

function formatCreatedAt(value) {
  const timestamp = Number(value)
  if (!Number.isFinite(timestamp) || timestamp <= 0) return '创建时间未知'
  const date = new Date(timestamp > 100000000000 ? timestamp : timestamp * 1000)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function instanceVersion(instance) {
  const loader = loaderLabel(instance.loader)
  const loaderVersion = instance.loader_version ? ` ${instance.loader_version}` : ''
  return `Minecraft ${instance.mc_version || '未知版本'} · ${loader}${loaderVersion}`
}
</script>

<template>
  <aside class="sidebar">
    <button class="player-card" @click="openAccount">
      <span class="player-card__avatar" :style="account?.skin ? { backgroundImage: `url(${account.skin})` } : null">
        <MicrosoftLogo
          v-if="account?.type === 'microsoft' && !account?.skin"
          class="player-card__microsoft"
        />
        <template v-else>{{ account?.skin ? '' : (account?.name || '?').slice(0, 1).toUpperCase() }}</template>
      </span>
      <span class="player-card__copy">
        <small>PLAYER</small>
        <strong>{{ account?.name || '未登录' }}</strong>
        <em>
          <i :class="{ online: account }"></i>
          {{ account ? (account.type === 'microsoft' ? '微软正版' : '离线账户') : '点击登录账号' }}
        </em>
      </span>
      <span class="player-card__arrow">›</span>
    </button>

    <button
      v-if="account?.type === 'microsoft'"
      class="skin-quick-preview"
      @click="openSkinPreview()"
    >
      <span class="skin-quick-preview__badge">SKIN</span>
      <span>
        <strong>皮肤预览</strong>
        <small>旋转查看正版皮肤</small>
      </span>
      <em>3D</em>
    </button>

    <div class="sidebar-heading">
      <div>
        <span>我的世界</span>
        <small>{{ state.instances.length }} 个实例</small>
      </div>
      <button class="mini-add" title="新建实例" @click="useLauncher().openNewInstance()">＋</button>
    </div>

    <label class="sidebar-search">
      <span>⌕</span>
      <input v-model="state.instanceQuery" type="search" placeholder="找一找实例…" />
    </label>

    <div class="instance-stack">
      <button
        v-for="instance in filteredInstances"
        :key="instance.id"
        class="instance-pill"
        :class="{ active: instance.id === state.selectedId }"
        @click="useLauncher().selectInstance(instance.id)"
      >
        <InstanceIcon
          class="instance-pill__icon"
          :loader="instance.loader"
          :icon="instance.icon"
          size="list"
        />
        <span class="instance-pill__body">
          <strong :title="instance.name">{{ instance.name }}</strong>
          <small :title="instanceVersion(instance)">{{ instanceVersion(instance) }}</small>
          <em :title="formatCreatedAt(instance.created_at)">创建于 {{ formatCreatedAt(instance.created_at) }}</em>
        </span>
        <i v-if="state.running[instance.id]" class="running-dot"></i>
        <span v-else class="instance-pill__chev">›</span>
      </button>
      <div v-if="!filteredInstances.length" class="sidebar-empty">
        <span>✦</span>
        <p>还没有实例<br />创建第一个冒险吧</p>
      </div>
    </div>

    <button class="new-instance-button" @click="useLauncher().openNewInstance()">
      <span>＋</span>
      新建实例
    </button>

    <nav class="sidebar-nav">
      <button :class="{ active: activeNav === 'download' }" @click="emit('navigate', 'download')">
        <span class="nav-icon">↓</span>
        <span>下载中心</span>
        <em v-if="activeTasks">{{ activeTasks }}</em>
      </button>
      <button :class="{ active: activeNav === 'settings' }" @click="emit('navigate', 'settings')">
        <span class="nav-icon">⚙</span>
        <span>设置</span>
      </button>
    </nav>
  </aside>
</template>
