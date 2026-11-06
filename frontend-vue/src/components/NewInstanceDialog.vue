<script setup>
import { computed, reactive, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import BakaSelect from './BakaSelect.vue'
import { useLauncher } from '../composables/useLauncher'

const launcher = useLauncher()
const {
  state,
  api,
  safe,
  closeModal,
  loadVersions,
  loadLoaders,
  createInstance,
  installJava,
  javaMajor,
  versionCategoryLabel,
  toast,
} = launcher

const prefill = state.modalData || {}
const form = reactive({
  name: '',
  mcVersion: prefill.mc_version || state.settings?.last_version || '',
  loader: prefill.loader || 'vanilla',
  loaderVersion: prefill.loader_version || '',
  autoJava: state.settings?.auto_download_java !== false,
})
const nameEdited = ref(false)
const loaderVersions = ref([])
const loadingLoaderVersions = ref(false)
const loaderVersionError = ref('')
const localInstaller = ref(null)
const inspectingInstaller = ref(false)
const submitting = ref(false)
let loaderVersionRequest = 0

const versions = computed(() => {
  const known = new Set()
  const list = []
  for (const version of [...(state.versions.installed || []), ...(state.versions.available || [])]) {
    if ((version.loader || 'vanilla') !== 'vanilla' || known.has(version.id)) continue
    known.add(version.id)
    list.push(version)
  }
  return list
})

const loaderOptions = computed(() => [
  { id: 'vanilla', name: '原版（无模组加载器）' },
  ...state.loaders.filter((loader) => loader.id !== 'vanilla'),
])
const versionOptions = computed(() =>
  [
    ...versions.value.map((version) => ({
      value: version.id,
      label: version.id,
      hint: versionCategoryLabel(version),
    })),
    ...(form.mcVersion && !versions.value.some((version) => version.id === form.mcVersion)
      ? [{ value: form.mcVersion, label: form.mcVersion, hint: '本地安装包' }]
      : []),
  ],
)
const loaderSelectOptions = computed(() =>
  loaderOptions.value.map((loader) => ({ value: loader.id, label: loader.name })),
)
const loaderVersionOptions = computed(() => [
  {
    value: '',
    label: form.loader === 'vanilla' ? '原版实例不使用加载器' : '自动选择最新版本',
  },
  ...loaderVersions.value.map((version) => ({ value: version, label: version })),
])
const requiredJava = computed(() => javaMajor(form.mcVersion))
const javaInstalled = computed(() =>
  state.java.all.some((runtime) => Number(runtime.major || 0) === requiredJava.value),
)
const loaderInstallerConflict = computed(() => {
  if (!localInstaller.value) return ''
  if (localInstaller.value.loader && localInstaller.value.loader !== form.loader) {
    return `安装包属于 ${localInstaller.value.loader}，请重新选择或切回对应加载器`
  }
  if (
    localInstaller.value.minecraft_version &&
    localInstaller.value.minecraft_version !== form.mcVersion
  ) {
    return `安装包适用于 Minecraft ${localInstaller.value.minecraft_version}`
  }
  return ''
})

watch(
  () => form.mcVersion,
  (value) => {
    if (!nameEdited.value) {
      form.name = value
        ? `${value}${form.loader !== 'vanilla' ? `-${form.loader}` : ''}`
        : ''
    }
    safe(() => refreshLoaderVersions())
  },
)
watch(
  () => form.loader,
  () => {
    if (!nameEdited.value) form.name = `${form.mcVersion || ''}${form.loader !== 'vanilla' ? `-${form.loader}` : ''}`
    safe(() => refreshLoaderVersions())
  },
)

async function refreshLoaderVersions(preferredLoaderVersion = '') {
  const request = ++loaderVersionRequest
  const loader = form.loader
  const minecraftVersion = form.mcVersion
  loaderVersions.value = []
  loaderVersionError.value = ''
  if (localInstaller.value) {
    loadingLoaderVersions.value = false
    return
  }
  form.loaderVersion = preferredLoaderVersion
  if (!minecraftVersion || loader === 'vanilla') {
    loadingLoaderVersions.value = false
    return
  }
  loadingLoaderVersions.value = true
  try {
    const payload = await api(
      `/api/loaders/${encodeURIComponent(loader)}/versions?minecraft_version=${encodeURIComponent(minecraftVersion)}`,
      { timeoutMs: 22000 },
    )
    if (
      request !== loaderVersionRequest ||
      form.loader !== loader ||
      form.mcVersion !== minecraftVersion
    ) {
      return
    }
    loaderVersions.value = payload.versions || []
    form.loaderVersion = loaderVersions.value.includes(preferredLoaderVersion)
      ? preferredLoaderVersion
      : loaderVersions.value[0] || ''
  } catch (error) {
    if (
      request === loaderVersionRequest &&
      form.loader === loader &&
      form.mcVersion === minecraftVersion
    ) {
      loaderVersionError.value = `加载器版本读取失败：${error.message}`
    }
    throw error
  } finally {
    if (request === loaderVersionRequest) loadingLoaderVersions.value = false
  }
}

async function chooseLoaderInstaller() {
  const path = await window.neo?.pickFile('选择加载器官网下载的 .jar 安装包', [
    { name: '模组加载器安装包', extensions: ['jar'] },
  ])
  if (!path) return
  inspectingInstaller.value = true
  try {
    const details = await api('/api/loaders/inspect-jar', {
      method: 'POST',
      body: { path },
    })
    localInstaller.value = details
    loaderVersionRequest += 1
    if (details.loader) form.loader = details.loader
    if (details.minecraft_version) form.mcVersion = details.minecraft_version
    if (details.loader_version) form.loaderVersion = details.loader_version
    toast(
      `已读取 ${details.loader} 安装包${details.loader_version ? ` ${details.loader_version}` : ''}`,
      'ok',
    )
  } finally {
    inspectingInstaller.value = false
  }
}

function removeLoaderInstaller() {
  localInstaller.value = null
  safe(() => refreshLoaderVersions(form.loaderVersion))
}

async function submit() {
  if (!form.name.trim() || !form.mcVersion) {
    toast('请填写实例名称并选择 Minecraft 版本', 'error')
    return
  }
  if (loaderInstallerConflict.value) {
    toast(loaderInstallerConflict.value, 'error')
    return
  }
  if (localInstaller.value && form.loader !== 'vanilla' && !form.loaderVersion.trim()) {
    toast('请填写与本地安装包匹配的加载器版本', 'error')
    return
  }
  submitting.value = true
  try {
    await createInstance({
      name: form.name.trim(),
      mc_version: form.mcVersion,
      loader: form.loader,
      loader_version: form.loader === 'vanilla' ? null : form.loaderVersion || null,
      loader_installer: form.loader === 'vanilla' ? null : localInstaller.value?.path || null,
      isolation: true,
    })
    if (form.autoJava && !javaInstalled.value && form.loader === 'vanilla') {
      await installJava(requiredJava.value)
    }
  } finally {
    submitting.value = false
  }
}

Promise.all([loadVersions(), loadLoaders()])
  .then(() => {
    if (!form.mcVersion) form.mcVersion = versions.value[0]?.id || ''
    if (prefill.loader_version) form.loaderVersion = prefill.loader_version
    if (!nameEdited.value) form.name = `${form.mcVersion || ''}${form.loader !== 'vanilla' ? `-${form.loader}` : ''}`
  })
  .then(() => refreshLoaderVersions(prefill.loader_version || ''))
  .catch((error) => toast(error.message, 'error'))
</script>

<template>
  <BaseModal title="创建新实例" subtitle="版本、加载器、Java 与游戏数据会绑定在这个实例中。" wide @close="closeModal()">
    <form class="dialog-form" @submit.prevent="submit">
      <label class="form-field">
        <span>实例名称</span>
        <input v-model="form.name" class="baka-input" @input="nameEdited = true" />
      </label>
      <div class="form-grid">
        <label class="form-field">
          <span>Minecraft 版本</span>
          <BakaSelect v-model="form.mcVersion" :options="versionOptions" aria-label="Minecraft 版本" />
        </label>
        <label class="form-field">
          <span>模组加载器</span>
          <BakaSelect v-model="form.loader" :options="loaderSelectOptions" aria-label="模组加载器" />
        </label>
      </div>
      <div class="form-field">
        <span>加载器版本</span>
        <input
          v-if="localInstaller && form.loader !== 'vanilla'"
          v-model="form.loaderVersion"
          class="baka-input"
          placeholder="填写与安装包匹配的加载器版本"
        />
        <BakaSelect
          v-else
          v-model="form.loaderVersion"
          :options="loaderVersionOptions"
          :disabled="form.loader === 'vanilla' || loadingLoaderVersions"
          aria-label="加载器版本"
        />
        <div class="loader-version-status">
          <small v-if="loaderInstallerConflict" class="bad">{{ loaderInstallerConflict }}</small>
          <small v-else-if="loaderVersionError">{{ loaderVersionError }}</small>
          <small v-else-if="localInstaller">将直接运行所选官网安装包，不再下载安装器</small>
          <small v-else>{{ loadingLoaderVersions ? '正在读取兼容版本…' : `${loaderVersions.length} 个可选版本` }}</small>
          <button
            v-if="loaderVersionError && form.loader !== 'vanilla' && !localInstaller"
            type="button"
            class="text-button"
            :disabled="loadingLoaderVersions"
            @click="safe(() => refreshLoaderVersions(form.loaderVersion))"
          >
            重新获取
          </button>
        </div>
      </div>
      <section v-if="form.loader !== 'vanilla'" class="local-loader-installer">
        <div class="local-loader-installer__head">
          <span class="local-loader-installer__icon">JAR</span>
          <div>
            <strong>安装包来源</strong>
            <small>可自动从官网下载，也可使用提前下载好的安装器</small>
          </div>
        </div>
        <div class="local-loader-source">
          <button
            type="button"
            :class="{ active: !localInstaller }"
            @click="removeLoaderInstaller"
          >
            自动从官网下载
          </button>
          <button
            type="button"
            :class="{ active: localInstaller }"
            :disabled="inspectingInstaller"
            @click="safe(chooseLoaderInstaller)"
          >
            {{ inspectingInstaller ? '正在检查…' : '使用本地 JAR' }}
          </button>
        </div>
        <div v-if="localInstaller" class="local-loader-file">
          <div>
            <strong>{{ localInstaller.file_name }}</strong>
            <small>
              {{ localInstaller.loader?.toUpperCase() }}
              <template v-if="localInstaller.minecraft_version"> · MC {{ localInstaller.minecraft_version }}</template>
              <template v-if="localInstaller.loader_version"> · {{ localInstaller.loader_version }}</template>
            </small>
          </div>
          <button type="button" class="text-button danger" @click="removeLoaderInstaller">移除</button>
        </div>
        <p v-else class="local-loader-auto-note">
          创建实例时将按照所选版本，自动下载官方加载器安装器 JAR。
        </p>
      </section>
      <p v-if="localInstaller" class="local-loader-installer__note">
        安装包会复制到启动器缓存后执行；请只使用加载器官网提供的安装器，不要选择普通模组 JAR。
      </p>
      <div class="info-strip" :class="{ warn: !javaInstalled }">
        <strong>{{ javaInstalled ? `Java ${requiredJava} 已就绪` : `需要 Java ${requiredJava}` }}</strong>
        <span>{{ javaInstalled ? '创建后可以直接启动。' : '可勾选自动下载，在后台准备 Zulu Java。' }}</span>
      </div>
      <label class="check-line">
        <input v-model="form.autoJava" type="checkbox" />
        <span><strong>自动准备 Zulu Java</strong><small>缺少兼容运行环境时在后台下载。</small></span>
      </label>
    </form>
    <template #footer>
      <button class="baka-button baka-button--plain" @click="closeModal()">取消</button>
      <button
        class="baka-button baka-button--primary"
        :disabled="submitting || loadingLoaderVersions"
        @click="submit"
      >
        {{ submitting ? '正在创建…' : localInstaller ? '创建并安装' : '创建并下载' }}
      </button>
    </template>
  </BaseModal>
</template>
