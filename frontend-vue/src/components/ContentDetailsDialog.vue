<script setup>
import { computed, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import BakaSelect from './BakaSelect.vue'
import CatalogIcon from './CatalogIcon.vue'
import { useLauncher } from '../composables/useLauncher'

const {
  state,
  closeModal,
  safe,
  formatCount,
  relativeTime,
  installMod,
  installModpack,
  installContent,
  isModDownloading,
} = useLauncher()

const detail = computed(() => state.details.item || {})
const kindLabel = computed(
  () =>
    ({
      mod: '模组',
      modpack: '整合包',
      resourcepack: '资源包',
      shader: '光影包',
      datapack: '数据包',
    })[state.details.kind] || '内容',
)
const selectedVersionId = ref('')
const versionOptions = computed(() =>
  (state.details.versions || [])
    .map((version) => {
      const value = String(version.version_id || version.id || '')
      const label = String(version.version_number || version.name || value)
      const facts = [
        version.channel && versionChannelLabel(version.channel),
        ...(version.loaders || []),
        ...(version.game_versions || []).slice(0, 2),
      ].filter(Boolean)
      return {
        value,
        label,
        hint: [...new Set(facts)].join(' · '),
      }
    })
    .filter((version) => version.value),
)
const selectedVersion = computed(
  () => versionOptions.value.find((version) => version.value === selectedVersionId.value) || null,
)
const canInstall = computed(() => !detail.value.local && Boolean(detail.value.id))
const installBusy = computed(
  () => state.details.kind === 'mod' && isModDownloading(detail.value),
)
const installDisabled = computed(
  () =>
    installBusy.value ||
    state.details.loading ||
    Boolean(versionOptions.value.length && !selectedVersionId.value),
)

watch(
  versionOptions,
  (options) => {
    if (!options.some((option) => option.value === selectedVersionId.value)) {
      selectedVersionId.value = options[0]?.value || ''
    }
  },
  { immediate: true },
)

function versionChannelLabel(channel) {
  return {
    release: '正式版',
    beta: '测试版',
    alpha: '预览版',
  }[String(channel || '').toLowerCase()] || String(channel || '')
}

function openPage() {
  if (detail.value.url) window.neo?.openExternal(detail.value.url)
}

function install() {
  const item = detail.value
  if (!item?.id) return
  safe(async () => {
    if (state.details.kind === 'mod') {
      const result = await installMod(item, selectedVersionId.value)
      if (result === 'waiting-dependencies') return
    } else if (state.details.kind === 'modpack') {
      await installModpack(item, selectedVersionId.value)
    } else {
      await installContent(item, state.details.kind, selectedVersionId.value)
    }
    closeModal()
  })
}
</script>

<template>
  <BaseModal :title="detail.title || '内容详情'" :subtitle="`${kindLabel} · ${detail.platform || '聚合搜索'}`" wide @close="closeModal()">
    <div class="content-detail">
      <div class="content-detail__hero">
        <CatalogIcon
          :src="detail.icon"
          :name="detail.title"
          :kind="state.details.kind"
          size="detail"
        />
        <div class="content-detail__intro">
          <div class="content-detail__chips">
            <span>{{ detail.platform || '聚合搜索' }}</span>
            <span v-if="detail.author">作者 {{ detail.author }}</span>
            <span>{{ formatCount(detail.downloads) }} 次下载</span>
          </div>
          <p>{{ detail.description || '暂无简介。' }}</p>
          <div class="content-detail__actions">
            <button
              v-if="canInstall"
              class="baka-button baka-button--primary"
              :disabled="installDisabled"
              @click="install"
            >
              {{ installBusy ? '正在准备…' : state.details.kind === 'modpack' ? '安装所选版本' : '下载所选版本' }}
            </button>
            <span v-else class="soft-tag">本地内容</span>
            <button v-if="detail.url" class="baka-button baka-button--plain" @click="openPage">打开项目页面</button>
          </div>
        </div>
      </div>

      <div class="content-detail__grid">
        <div>
          <small>PROJECT</small>
          <strong>{{ detail.slug || detail.id }}</strong>
        </div>
        <div>
          <small>VERSION</small>
          <strong>{{ detail.version || detail.version_number || '最新版本' }}</strong>
        </div>
        <div>
          <small>UPDATED</small>
          <strong>{{ detail.date_modified ? relativeTime(detail.date_modified) : '未知' }}</strong>
        </div>
        <div>
          <small>GAME VERSIONS</small>
          <strong>{{ (detail.game_versions || []).slice(-5).join(', ') || '未标注' }}</strong>
        </div>
        <div>
          <small>CATEGORIES</small>
          <strong>{{ (detail.categories || []).slice(0, 5).join(', ') || '未分类' }}</strong>
        </div>
      </div>

      <div class="content-detail__versions">
        <header>
          <div>
            <small>AVAILABLE VERSIONS</small>
            <strong>选择下载版本</strong>
          </div>
          <span v-if="state.details.loading" class="spinner"></span>
        </header>
        <p v-if="state.details.error">{{ state.details.error }}</p>
        <p v-else-if="state.details.loading">正在读取版本…</p>
        <template v-else-if="versionOptions.length">
          <BakaSelect
            v-model="selectedVersionId"
            :options="versionOptions"
            compact
            aria-label="选择下载版本"
          />
          <p v-if="selectedVersion?.hint">{{ selectedVersion.hint }}</p>
        </template>
        <p v-else>暂无版本信息，将继续使用平台默认版本。</p>
      </div>
    </div>
  </BaseModal>
</template>
