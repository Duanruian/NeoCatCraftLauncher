import { computed, reactive } from 'vue'

const API = window.neo?.apiBase || 'http://127.0.0.1:47821'
const bridge = window.neo || null

const state = reactive({
  ready: false,
  view: 'empty',
  tab: 'overview',
  selectedId: null,
  instanceQuery: '',
  instance: null,
  instances: [],
  accounts: [],
  settings: null,
  health: null,
  firstRunDone: false,
  disclaimerAccepted: false,
  java: { managed: [], system: [], all: [], available: [], directory: '' },
  versions: { available: [], installed: [], filter: 'release', query: '' },
  loaders: [],
  loaderType: 'fabric',
  loaderMinecraft: '',
  loaderVersions: [],
  mods: null,
  modLoading: false,
  modQuery: '',
  modPlatform: 'all',
  modSearchHits: [],
  modSearching: false,
  modSearchSummary: '',
  modSearchWarnings: [],
  modDownloading: {},
  saves: null,
  logs: [],
  selectedLog: '',
  logContent: '',
  modpacks: {
    popular: [],
    results: [],
    loading: false,
    searching: false,
    platform: 'all',
    query: '',
    minecraft: '',
    summary: '正在获取热门整合包…',
    warnings: [],
  },
  content: {
    kind: 'resourcepack',
    platform: 'all',
    query: '',
    world: '',
    items: [],
    catalog: [],
    directory: '',
    loading: false,
    searching: false,
    summary: '正在获取热门内容…',
    warnings: [],
  },
  details: {
    item: null,
    kind: 'mod',
    versions: [],
    loading: false,
    error: '',
    requestId: 0,
  },
  tasks: [],
  running: {},
  toasts: [],
  modal: null,
  modalData: null,
  wizard: { open: false, step: 0, path: '', javaMajor: 21, createdInstanceId: null },
  deviceFlow: { active: false, code: '', uri: '', status: '', message: '' },
  appStatus: '正在连接本地服务',
  appStatusKind: 'busy',
  launchBusy: false,
})

let eventSource = null
let recountTimer = null
let deviceFlowGeneration = 0
let pendingSelectTask = null
let modalResolver = null
let detailRequestId = 0
const knownTasks = new Map()

export const activeAccount = computed(() => state.accounts.find((account) => account.active) || null)
export const filteredInstances = computed(() => {
  const query = (state.instanceQuery || '').trim().toLowerCase()
  if (!query) return state.instances
  return state.instances.filter((item) =>
    [item.name, item.mc_version, item.loader].filter(Boolean).join(' ').toLowerCase().includes(query),
  )
})

const APRIL_FOOLS_VERSION_IDS = new Set([
  '15w14a',
  '1.rv-pre1',
  '3d shareware v1.34',
  '20w14∞',
  '22w13oneblockatatime',
  '23w13a_or_b',
  '24w14potato',
  '25w14craftmine',
])

export const VERSION_CATEGORIES = [
  { id: 'release', label: '正式版' },
  { id: 'snapshot', label: '快照版' },
  { id: 'april_fools', label: '愚人节版' },
  { id: 'ancient', label: '远古版' },
]

export function versionCategory(version) {
  if (version?.category) return version.category
  const type = String(version?.type || '').toLowerCase()
  if (['old_alpha', 'old_beta', 'alpha', 'beta'].includes(type)) return 'ancient'
  if (type === 'release') return 'release'
  const id = String(version?.id || '').toLowerCase()
  const releaseTime = String(version?.releaseTime || '')
  if (APRIL_FOOLS_VERSION_IDS.has(id) || releaseTime.slice(5, 10) === '04-01') {
    return 'april_fools'
  }
  return 'snapshot'
}

export function versionCategoryLabel(version) {
  const category = versionCategory(version)
  return VERSION_CATEGORIES.find((item) => item.id === category)?.label || '快照版'
}

export const visibleVersions = computed(() => {
  const known = new Set()
  const merged = []
  for (const version of [...(state.versions.installed || []), ...(state.versions.available || [])]) {
    if (!known.has(version.id) && (version.loader || 'vanilla') === 'vanilla') {
      known.add(version.id)
      merged.push(version)
    }
  }
  const query = state.versions.query.trim().toLowerCase()
  return merged.filter((version) => {
    if (state.versions.filter !== 'all' && versionCategory(version) !== state.versions.filter) {
      return false
    }
    return !query || String(version.id).toLowerCase().includes(query)
  })
})

function el(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text != null) node.textContent = text
  return node
}

async function api(path, options = {}) {
  const { timeoutMs = 0, ...fetchOptions } = options
  const headers = { ...(fetchOptions.headers || {}) }
  let body = fetchOptions.body
  if (body && typeof body !== 'string') {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(body)
  }
  const controller = timeoutMs && !fetchOptions.signal ? new AbortController() : null
  const timer = controller
    ? window.setTimeout(() => controller.abort(), timeoutMs)
    : null
  let response
  try {
    response = await fetch(API + path, {
      ...fetchOptions,
      headers,
      body,
      signal: fetchOptions.signal || controller?.signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error(`请求超时（${Math.round(timeoutMs / 1000)} 秒）`)
    }
    throw error
  } finally {
    if (timer) window.clearTimeout(timer)
  }
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!response.ok) {
    throw new Error(data?.error || data?.detail || `HTTP ${response.status}`)
  }
  if (data?.ok === false) throw new Error(data.error || '请求失败')
  return data
}

function toast(message, kind = 'info', timeout = 3800) {
  const item = { id: Date.now() + Math.random(), message: String(message), kind }
  state.toasts.push(item)
  window.setTimeout(() => {
    const index = state.toasts.findIndex((entry) => entry.id === item.id)
    if (index >= 0) state.toasts.splice(index, 1)
  }, timeout)
}

function safe(task) {
  return Promise.resolve().then(task).catch((error) => toast(error.message || String(error), 'error', 6000))
}

function relativeTime(value) {
  if (!value) return '尚未游玩'
  const timestamp = Number(value)
  const date = Number.isFinite(timestamp)
    ? new Date(timestamp > 100000000000 ? timestamp : timestamp * 1000)
    : new Date(value)
  if (Number.isNaN(date.getTime())) return '尚未游玩'
  const diff = Date.now() - date.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)} 天前`
  return date.toLocaleDateString('zh-CN')
}

function formatBytes(value) {
  const size = Number(value) || 0
  if (size < 1024) return `${size} B`
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 ** 3) return `${(size / 1024 ** 2).toFixed(1)} MB`
  return `${(size / 1024 ** 3).toFixed(2)} GB`
}

function formatCount(value) {
  const count = Number(value) || 0
  if (count >= 100000000) return `${(count / 100000000).toFixed(1)} 亿`
  if (count >= 10000) return `${(count / 10000).toFixed(1)} 万`
  return String(count)
}

function loaderLabel(loader) {
  return {
    vanilla: '原版',
    fabric: 'Fabric',
    forge: 'Forge',
    neoforge: 'NeoForge',
    quilt: 'Quilt',
  }[loader || 'vanilla'] || loader || '原版'
}

function javaMajor(version) {
  const value = String(version || '')
  if (value.startsWith('1.21') || value.startsWith('1.20.5')) return 21
  if (/^1\.(17|18|19|20)(\.|$)/.test(value)) return 17
  if (value.startsWith('1.17')) return 16
  if (/^1\.(7|8|9|10|11|12|13|14|15|16)/.test(value)) return 8
  return 21
}

function applyTheme(preview) {
  const settings = preview || state.settings
  if (!settings) return
  const requested = settings.theme_mode || 'light'
  const resolved =
    requested === 'system'
      ? window.matchMedia?.('(prefers-color-scheme: light)').matches
        ? 'light'
        : 'dark'
      : requested
  document.documentElement.dataset.theme = resolved
  document.documentElement.dataset.accent = settings.theme || 'ocean'
  const closeAnimation =
    settings.close_animation === undefined ? state.settings?.close_animation : settings.close_animation
  window.__neoCloseAnim = closeAnimation !== false
}

function showModal(type, data = null) {
  state.modal = type
  state.modalData = data
}

function closeModal(value = null) {
  state.modal = null
  state.modalData = null
  if (modalResolver) {
    const resolve = modalResolver
    modalResolver = null
    resolve(value)
  }
  deviceFlowGeneration += 1
  state.deviceFlow.active = false
  state.details.item = null
  state.details.versions = []
  state.details.error = ''
}

function confirmAction(title, message, confirmLabel = '确认', danger = false) {
  return new Promise((resolve) => {
    modalResolver = resolve
    showModal('confirm', { title, message, confirmLabel, danger })
  })
}

function setStatus(text, kind = 'ok') {
  state.appStatus = text
  state.appStatusKind = kind
}

function updateStatus() {
  const running = Object.keys(state.running).length
  const activeTasks = state.tasks.filter((task) => task.state === 'running').length
  if (running) setStatus(`${running} 个游戏正在运行`, 'ok')
  else if (activeTasks) setStatus(`${activeTasks} 个任务进行中`, 'busy')
  else if (state.health) setStatus('准备就绪', 'ok')
  else setStatus('等待本地服务', 'off')
}

function upsertTask(task) {
  if (!task?.id) return
  const oldState = knownTasks.get(task.id)
  const index = state.tasks.findIndex((item) => item.id === task.id)
  if (index >= 0) state.tasks.splice(index, 1, task)
  else state.tasks.unshift(task)
  knownTasks.set(task.id, task.state)
  if (task.state === 'done' || task.state === 'error') {
    for (const [key, taskId] of Object.entries(state.modDownloading)) {
      if (taskId === task.id) delete state.modDownloading[key]
    }
  }
  updateStatus()
  if (task.state === 'error' && oldState !== 'error' && task.kind === 'download') {
    toast(task.error || task.message || '下载任务失败', 'error', 7000)
  }
  if (task.state === 'done' && oldState !== 'done') {
    if (task.kind === 'java') safe(() => loadJava(true))
    if (task.kind === 'instance' || task.kind === 'modpack') {
      const target = pendingSelectTask || task.result?.instance || state.selectedId
      safe(async () => {
        await refreshInstances(target)
        if (target) await selectInstance(target)
      })
      pendingSelectTask = null
    }
    if (task.kind === 'install' || task.kind === 'loader') {
      state.versions.available = []
      safe(() => loadVersions(true))
    }
  }
}

async function loadBootstrap() {
  const payload = await api('/api/app/bootstrap')
  state.settings = payload.settings
  state.accounts = payload.accounts || []
  state.instances = payload.instances || []
  state.firstRunDone = Boolean(payload.first_run_done)
  state.disclaimerAccepted = Boolean(payload.disclaimer_accepted)
  if (payload.java) {
    state.java = {
      managed: payload.java.installed || [],
      system: payload.java.system || [],
      available: payload.java.available_majors || [],
      all: [...(payload.java.installed || []), ...(payload.java.system || [])],
      directory: state.settings?.javas_directory || '',
    }
  }
  applyTheme()
  state.selectedId = payload.active_instance || state.instances[0]?.id || null
  if (state.selectedId) {
    state.view = 'instance'
    await loadInstance(state.selectedId)
  } else {
    state.view = 'empty'
  }
  if (!state.disclaimerAccepted) state.modal = 'disclaimer'
  else if (!state.firstRunDone) showWizard()
  ;(payload.tasks || []).forEach(upsertTask)
}

async function refreshInstances(preferredId) {
  const payload = await api('/api/instances')
  state.instances = payload.instances || []
  const candidate = preferredId || state.selectedId || payload.active
  state.selectedId = state.instances.some((item) => item.id === candidate)
    ? candidate
    : state.instances[0]?.id || null
  if (!state.selectedId && state.view === 'instance') state.view = 'empty'
}

async function selectInstance(id) {
  if (!id) return
  state.selectedId = id
  state.instance = state.instances.find((item) => item.id === id) || null
  state.view = 'instance'
  state.tab = 'overview'
  state.mods = null
  state.saves = null
  state.logs = []
  state.logContent = ''
  state.selectedLog = ''
  try {
    await api(`/api/instances/${encodeURIComponent(id)}/select`, { method: 'POST' })
  } catch (error) {
    toast(error.message, 'error')
  }
  await loadInstance(id)
}

async function loadInstance(id) {
  const instance = await api(`/api/instances/${encodeURIComponent(id)}`)
  if (state.selectedId !== id) return
  state.instance = instance
  state.instances = state.instances.map((item) => (item.id === id ? { ...item, ...instance } : item))
  if (state.tab === 'mods') safe(loadMods)
  if (state.tab === 'saves') safe(loadSaves)
  if (state.tab === 'logs') safe(loadLogs)
}

function setTab(tab) {
  state.tab = tab
  if (tab === 'mods') {
    safe(loadMods)
    safe(loadPopularMods)
  }
  if (tab === 'saves') safe(loadSaves)
  if (tab === 'logs') safe(loadLogs)
  if (tab === 'content') safe(loadContent)
  if (tab === 'overview') safe(loadOverview)
}

async function loadOverview() {
  if (!state.instance) return
  const [mods, saves] = await Promise.all([
    api(`/api/mods?instance_id=${encodeURIComponent(state.instance.id)}`).catch(() => null),
    api(`/api/instances/${encodeURIComponent(state.instance.id)}/saves`).catch(() => null),
  ])
  if (mods) state.mods = mods
  if (saves) state.saves = saves
}

async function loadMods(force = false) {
  if (!state.instance || (state.mods && !force)) return
  state.modLoading = true
  try {
    state.mods = await api(`/api/mods?instance_id=${encodeURIComponent(state.instance.id)}`)
    safe(loadModPlatforms)
  } finally {
    state.modLoading = false
  }
}

async function loadModPlatforms() {
  const platforms = await api('/api/mods/platforms')
  if (!platforms.some((item) => item.id === state.modPlatform) && state.modPlatform !== 'all') {
    state.modPlatform = 'all'
  }
}

async function toggleMod(mod) {
  await api('/api/mods/toggle', {
    method: 'POST',
    body: { file: mod.file_name, instance_id: state.instance.id },
  })
  toast(`${mod.enabled === false ? '已启用' : '已停用'} ${mod.file_name}`, 'ok')
  await loadMods(true)
}

async function deleteMod(mod) {
  const accepted = await confirmAction('删除模组', `确定从当前实例删除 ${mod.file_name}？`, '删除', true)
  if (!accepted) return
  await api(
    `/api/mods/file?file=${encodeURIComponent(mod.file_name)}&instance_id=${encodeURIComponent(state.instance.id)}`,
    { method: 'DELETE' },
  )
  toast('模组已删除', 'ok')
  await loadMods(true)
}

async function loadPopularMods() {
  if (!state.instance) return
  state.modSearching = true
  try {
    const params = new URLSearchParams({
      platform: 'all',
      query: '',
      minecraft_version: state.instance.mc_version || '',
      loader: state.instance.loader || '',
      limit: '20',
      offset: '0',
    })
    const payload = await api(`/api/mods/search?${params}`)
    state.modSearchHits = payload.hits || []
    state.modSearchSummary = `双平台热门 · ${state.modSearchHits.length} 个模组`
    state.modSearchWarnings = payload.warnings || []
  } finally {
    state.modSearching = false
  }
}

async function searchMods() {
  if (!state.instance) return
  if (!state.modQuery.trim()) {
    await loadPopularMods()
    return
  }
  state.modSearching = true
  try {
    const params = new URLSearchParams({
      platform: state.modPlatform,
      query: state.modQuery.trim(),
      minecraft_version: state.instance.mc_version || '',
      loader: state.instance.loader || '',
      limit: '20',
      offset: '0',
    })
    const payload = await api(`/api/mods/search?${params}`)
    state.modSearchHits = payload.hits || []
    state.modSearchSummary = `聚合搜索 · ${payload.total || state.modSearchHits.length} 个结果`
    state.modSearchWarnings = payload.warnings || []
  } finally {
    state.modSearching = false
  }
}

function modDownloadKey(hit) {
  return `${hit?.platform || 'modrinth'}:${hit?.id || hit?.project_id || hit?.slug || ''}`
}

function isModDownloading(hit) {
  return Boolean(state.modDownloading[modDownloadKey(hit)])
}

function createPrepareTask(hit) {
  const task = {
    id: `prepare-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    kind: 'download',
    title: `准备下载 ${hit.title || hit.name || '模组'}`,
    state: 'running',
    progress: 2,
    total: 100,
    percent: 2,
    message: '正在检查版本与前置…',
    created_at: Date.now() / 1000,
    updated_at: Date.now() / 1000,
  }
  state.tasks.unshift(task)
  updateStatus()
  return task
}

function updateLocalTask(task, fields) {
  const index = state.tasks.findIndex((item) => item.id === task.id)
  if (index >= 0) {
    state.tasks.splice(index, 1, { ...state.tasks[index], ...fields })
  }
  updateStatus()
}

function removeLocalTask(task) {
  const index = state.tasks.findIndex((item) => item.id === task.id)
  if (index >= 0) state.tasks.splice(index, 1)
  knownTasks.delete(task.id)
  updateStatus()
}

async function performModDownload(hit, selectedDependencies, task, key, versionId = '') {
  updateLocalTask(task, {
    message: selectedDependencies.length
      ? `正在下载本体与 ${selectedDependencies.length} 个前置…`
      : '正在获取下载地址并下载…',
    percent: 8,
  })
  try {
    const backendTask = await api('/api/mods/install', {
      method: 'POST',
      body: {
        platform: hit.platform || state.modPlatform,
        project_id: hit.id,
        version_id: versionId || undefined,
        minecraft_version: state.instance.mc_version,
        loader: state.instance.loader,
        instance_id: state.instance.id,
        with_dependencies: false,
        dependency_project_ids: selectedDependencies,
        enabled: true,
      },
    })
    state.modDownloading[key] = backendTask.id
    upsertTask(backendTask)
    removeLocalTask(task)
    toast(`下载任务已创建：${backendTask.title || hit.title || '模组'}`, 'ok')
    return 'started'
  } catch (error) {
    updateLocalTask(task, {
      state: 'error',
      error: error.message,
      message: error.message,
    })
    toast(error.message, 'error', 6000)
    delete state.modDownloading[key]
    updateStatus()
  }
}

async function installMod(hit, versionId = '') {
  if (!state.instance || !hit) return
  const key = modDownloadKey(hit)
  if (state.modDownloading[key]) return
  state.modDownloading[key] = true
  const task = createPrepareTask(hit)

  try {
    const params = new URLSearchParams({
      platform: hit.platform || state.modPlatform,
      project_id: String(hit.id || ''),
      minecraft_version: state.instance.mc_version || '',
      loader: state.instance.loader || '',
      instance_id: state.instance.id,
    })
    if (versionId) params.set('version_id', versionId)
    const report = await api(`/api/mods/dependencies?${params}`)
    const dependencies = report.dependencies || []
    const pending = dependencies.filter((item) => !item.installed)
    if (pending.length) {
      updateLocalTask(task, {
        message: `发现 ${pending.length} 个待确认前置，等待选择…`,
        percent: 5,
      })
      state.modal = 'mod-dependencies'
      state.modalData = { hit, versionId, dependencies, task, key }
      return 'waiting-dependencies'
    }
    await performModDownload(hit, [], task, key, versionId)
    return 'completed'
  } catch (error) {
    updateLocalTask(task, {
      state: 'error',
      error: error.message,
      message: error.message,
    })
    delete state.modDownloading[key]
    toast(error.message, 'error', 6000)
  }
}

function confirmModDependencies(selectedProjectIds) {
  const pending = state.modalData
  if (!pending) return
  closeModal()
  return performModDownload(
    pending.hit,
    [...new Set(selectedProjectIds.map(String))],
    pending.task,
    pending.key,
    pending.versionId,
  )
}

function cancelModDependencies() {
  const pending = state.modalData
  if (pending) {
    removeLocalTask(pending.task)
    delete state.modDownloading[pending.key]
    updateStatus()
  }
  closeModal()
}

async function openDetails(item, kind = 'mod') {
  if (!item) return
  const requestId = ++detailRequestId
  const normalized = {
    ...item,
    title: item.title || item.name || item.file_name || '未命名内容',
    author: item.author || (item.authors || []).join(', '),
    description: item.description || '暂无简介。',
    platform: item.platform || 'LOCAL',
    slug: item.slug || item.mod_id || item.file_name || item.id,
    date_modified: item.date_modified || item.modified || null,
    local: Boolean(item.file_name && !item.platform),
  }
  state.details = {
    item: normalized,
    kind,
    versions: [],
    loading: true,
    error: '',
    requestId,
  }
  state.modal = 'content-details'
  state.modalData = null

  if (normalized.local || !normalized.id) {
    state.details.loading = false
    return
  }

  try {
    let payload
    if (kind === 'mod') {
      const params = new URLSearchParams({
        platform: normalized.platform,
        project_id: normalized.id,
        minecraft_version: state.instance?.mc_version || '',
        loader: state.instance?.loader || '',
      })
      payload = await api(`/api/mods/versions?${params}`)
    } else if (kind === 'modpack') {
      const params = new URLSearchParams({
        platform: normalized.platform,
        project_id: normalized.id,
        minecraft_version: state.modpacks.minecraft || '',
      })
      payload = await api(`/api/modpacks/versions?${params}`)
    } else {
      const params = new URLSearchParams({
        kind,
        platform: normalized.platform,
        project_id: normalized.id,
        minecraft_version: state.instance?.mc_version || '',
      })
      payload = await api(`/api/content/versions?${params}`)
    }
    if (state.modal === 'content-details' && state.details.requestId === requestId) {
      state.details.versions = payload.versions || []
    }
  } catch (error) {
    if (state.modal === 'content-details' && state.details.requestId === requestId) {
      state.details.error = error.message
    }
  } finally {
    if (state.modal === 'content-details' && state.details.requestId === requestId) {
      state.details.loading = false
    }
  }
}

async function loadContent() {
  if (!state.instance) return
  if (state.content.kind === 'datapack') {
    if (!state.saves) await loadSaves()
    const saves = state.saves?.saves || []
    if (!saves.some((save) => save.name === state.content.world)) {
      state.content.world = saves[0]?.name || ''
    }
  }
  await Promise.all([loadContentLocal(), loadContentPopular()])
}

async function setContentKind(kind) {
  if (state.content.kind === kind) return
  state.content.kind = kind
  state.content.query = ''
  state.content.items = []
  state.content.summary = '正在获取热门内容…'
  await loadContent()
}

async function selectContentWorld(world) {
  state.content.world = world
  await loadContentLocal()
}

async function loadContentLocal() {
  if (!state.instance) return
  state.content.loading = true
  try {
    const params = new URLSearchParams({
      kind: state.content.kind,
      instance_id: state.instance.id,
    })
    if (state.content.kind === 'datapack' && state.content.world) {
      params.set('world', state.content.world)
    }
    const payload = await api(`/api/content/local?${params}`)
    state.content.items = payload.items || []
    state.content.directory = payload.directory || ''
  } finally {
    state.content.loading = false
  }
}

async function loadContentPopular() {
  if (!state.instance) return
  state.content.searching = true
  try {
    const params = new URLSearchParams({
      kind: state.content.kind,
      platform: 'all',
      query: '',
      minecraft_version: state.instance.mc_version || '',
      limit: '20',
      offset: '0',
    })
    const payload = await api(`/api/content/search?${params}`)
    state.content.catalog = payload.hits || []
    state.content.summary = `双平台热门 · ${state.content.catalog.length} 个结果`
    state.content.warnings = payload.warnings || []
  } finally {
    state.content.searching = false
  }
}

async function searchContent() {
  if (!state.instance) return
  if (!state.content.query.trim()) {
    await loadContentPopular()
    return
  }
  state.content.searching = true
  try {
    const params = new URLSearchParams({
      kind: state.content.kind,
      platform: state.content.platform,
      query: state.content.query.trim(),
      minecraft_version: state.instance.mc_version || '',
      limit: '20',
      offset: '0',
    })
    const payload = await api(`/api/content/search?${params}`)
    state.content.catalog = payload.hits || []
    state.content.summary = `聚合搜索 · ${payload.total || state.content.catalog.length} 个结果`
    state.content.warnings = payload.warnings || []
  } finally {
    state.content.searching = false
  }
}

async function installContent(hit, kind = state.content.kind, versionId = '') {
  if (!state.instance || !hit) return
  const task = await api('/api/content/install', {
    method: 'POST',
    body: {
      kind,
      platform: hit.platform,
      project_id: hit.id,
      version_id: versionId || undefined,
      minecraft_version: state.instance.mc_version,
      instance_id: state.instance.id,
      world: kind === 'datapack' ? state.content.world : '',
    },
  })
  upsertTask(task)
  toast(`${contentKindLabel(kind)}正在后台下载`, 'ok')
}

async function toggleContent(item) {
  await api('/api/content/toggle', {
    method: 'POST',
    body: {
      kind: state.content.kind,
      file: item.file_name,
      instance_id: state.instance?.id,
      world: state.content.kind === 'datapack' ? state.content.world : '',
    },
  })
  await loadContentLocal()
}

async function deleteContent(item) {
  const label = contentKindLabel(state.content.kind)
  const accepted = await confirmAction(`删除${label}`, `确定删除 ${item.name || item.file_name}？`, '删除', true)
  if (!accepted) return
  const params = new URLSearchParams({
    kind: state.content.kind,
    file: item.file_name,
    instance_id: state.instance?.id || '',
  })
  if (state.content.kind === 'datapack' && state.content.world) params.set('world', state.content.world)
  await api(`/api/content/file?${params}`, { method: 'DELETE' })
  toast(`${label}已删除`, 'ok')
  await loadContentLocal()
}

async function openContentFolder() {
  if (!state.instance) return
  return api('/api/content/open-folder', {
    method: 'POST',
    body: {
      kind: state.content.kind,
      instance_id: state.instance.id,
      world: state.content.kind === 'datapack' ? state.content.world : '',
    },
  })
}

function contentKindLabel(kind) {
  return {
    resourcepack: '资源包',
    shader: '光影包',
    datapack: '数据包',
  }[kind] || '内容'
}

async function loadSaves() {
  if (!state.instance) return
  state.saves = await api(`/api/instances/${encodeURIComponent(state.instance.id)}/saves`)
}

async function loadLogs() {
  if (!state.instance) return
  const payload = await api(`/api/instances/${encodeURIComponent(state.instance.id)}/logs`)
  state.logs = payload.logs || []
  if (state.logs.length) {
    state.selectedLog = state.logs[0].name
    await readLog(state.selectedLog)
  } else {
    state.selectedLog = ''
    state.logContent = ''
  }
}

async function readLog(name) {
  if (!state.instance || !name) return
  const payload = await api(
    `/api/instances/${encodeURIComponent(state.instance.id)}/logs/${encodeURIComponent(name)}?lines=500`,
  )
  state.selectedLog = name
  state.logContent = payload.content || ''
}

function openFolder(sub = '') {
  if (!state.instance) return
  const suffix = sub ? `?sub=${encodeURIComponent(sub)}` : ''
  return api(`/api/instances/${encodeURIComponent(state.instance.id)}/open${suffix}`, { method: 'POST' })
}

async function repairInstance() {
  if (!state.instance) return
  const task = await api(`/api/instances/${encodeURIComponent(state.instance.id)}/repair`, { method: 'POST' })
  upsertTask(task)
  toast('已开始修复实例', 'ok')
}

async function launchGame() {
  if (!state.instance) return
  if (!activeAccount.value) {
    showModal('account')
    return
  }
  state.launchBusy = true
  try {
    const result = await api('/api/launch', {
      method: 'POST',
      body: { instance_id: state.instance.id },
    })
    upsertTask(result.task)
    state.running[state.instance.id] = result.pid
    toast('游戏已经启动', 'ok')
    updateStatus()
  } finally {
    state.launchBusy = false
  }
}

async function loadVersions(force = false) {
  if (state.versions.available.length && !force) return
  const payload = await api(`/api/versions${force ? '?force=true' : ''}`)
  state.versions.available = payload.available || []
  state.versions.installed = payload.installed || []
}

async function loadLoaders() {
  if (state.loaders.length) return
  state.loaders = await api('/api/loaders')
}

async function loadLoaderVersions() {
  if (!state.loaderMinecraft) {
    state.loaderVersions = []
    return
  }
  const payload = await api(
    `/api/loaders/${encodeURIComponent(state.loaderType)}/versions?minecraft_version=${encodeURIComponent(state.loaderMinecraft)}`,
  )
  state.loaderVersions = payload.versions || []
}

async function loadJava(force = false) {
  const payload = await api(`/api/java${force ? '?force=true' : ''}`)
  state.java = {
    managed: payload.managed || [],
    system: payload.system || [],
    all: payload.all || [],
    available: payload.available || [],
    directory: payload.directory || '',
  }
  if (state.instance) safe(() => loadInstance(state.instance.id))
}

async function installJava(major) {
  const task = await api('/api/java/install', { method: 'POST', body: { major: Number(major) } })
  upsertTask(task)
  toast(`已开始下载 Zulu Java ${major}`, 'ok')
}

async function loadPopularModpacks(force = false) {
  if (!force && state.modpacks.popular.length) return
  state.modpacks.loading = true
  state.modpacks.summary = '正在获取下载量较高的整合包…'
  try {
    const payload = await api(
      `/api/modpacks/search?platform=${encodeURIComponent(state.modpacks.platform)}&query=&limit=12&offset=0`,
    )
    state.modpacks.popular = [...(payload.hits || [])].sort(
      (a, b) => Number(b.downloads || 0) - Number(a.downloads || 0),
    )
    state.modpacks.results = []
    state.modpacks.warnings = payload.warnings || []
    state.modpacks.summary = `双平台热门 · ${state.modpacks.popular.length} 个整合包`
  } catch (error) {
    state.modpacks.summary = `热门整合包加载失败：${error.message}`
    toast(error.message, 'error', 6000)
  } finally {
    state.modpacks.loading = false
  }
}

async function searchModpacks() {
  state.modpacks.searching = true
  try {
    const params = new URLSearchParams({
      platform: state.modpacks.platform,
      query: state.modpacks.query,
      minecraft_version: state.modpacks.minecraft,
      limit: '20',
      offset: '0',
    })
    const payload = await api(`/api/modpacks/search?${params}`)
    state.modpacks.results = payload.hits || []
    state.modpacks.warnings = payload.warnings || []
    state.modpacks.summary = `搜索结果 · ${payload.total || state.modpacks.results.length} 个`
  } finally {
    state.modpacks.searching = false
  }
}

async function installModpack(hit, versionId = '') {
  const task = await api('/api/modpacks/install', {
    method: 'POST',
    body: {
      platform: hit.platform || state.modpacks.platform,
      project_id: hit.id,
      version_id: versionId || undefined,
      name: hit.title || null,
    },
  })
  upsertTask(task)
  toast('整合包正在后台安装', 'ok')
}

async function importModpack() {
  const path = await bridge?.pickFile('选择整合包', [
    { name: '整合包', extensions: ['zip', 'mrpack', 'jar'] },
  ])
  if (!path) return
  const task = await api('/api/modpacks/import', { method: 'POST', body: { path } })
  upsertTask(task)
  toast('正在导入整合包', 'ok')
}

async function saveSettings(patch) {
  state.settings = await api('/api/settings', { method: 'PUT', body: patch })
  applyTheme()
  toast('设置已保存', 'ok')
}

async function saveInstanceSettings(patch) {
  if (!state.instance) return
  const updated = await api(`/api/instances/${encodeURIComponent(state.instance.id)}`, {
    method: 'PATCH',
    body: patch,
  })
  state.instance = updated
  await refreshInstances(updated.id)
  closeModal()
  toast('实例设置已保存', 'ok')
}

async function deleteInstance() {
  if (!state.instance) return
  const accepted = await confirmAction(
    '删除实例',
    `确定删除“${state.instance.name}”的实例记录吗？实例文件会保留。`,
    '删除',
    true,
  )
  if (!accepted) return
  await api(`/api/instances/${encodeURIComponent(state.instance.id)}?delete_files=false`, { method: 'DELETE' })
  state.instance = null
  state.selectedId = null
  state.view = 'empty'
  await refreshInstances()
  toast('实例已删除', 'ok')
}

async function duplicateInstance() {
  if (!state.instance) return
  const created = await api(`/api/instances/${encodeURIComponent(state.instance.id)}/duplicate`, {
    method: 'POST',
    body: {},
  })
  closeModal()
  await refreshInstances(created.id)
  await selectInstance(created.id)
  toast(`已复制为 ${created.name}`, 'ok')
}

function clearTasks() {
  state.tasks.splice(0, state.tasks.length)
  knownTasks.clear()
  updateStatus()
}

function openNewInstance(prefill = null) {
  showModal('new-instance', prefill)
  safe(loadVersions)
  safe(loadLoaders)
}

async function createInstance(payload) {
  const result = await api('/api/instances', { method: 'POST', body: payload })
  upsertTask(result.task)
  pendingSelectTask = result.instance.id
  await refreshInstances(result.instance.id)
  closeModal()
  if (state.wizard.open) {
    state.wizard.createdInstanceId = result.instance.id
  } else {
    await selectInstance(result.instance.id)
  }
  toast('实例已创建，游戏文件正在下载', 'ok')
}

async function beginMicrosoftLogin() {
  const generation = ++deviceFlowGeneration
  state.deviceFlow = { active: true, code: '', uri: '', status: '获取设备代码…', message: '' }
  const data = await api('/api/auth/microsoft/device/start', { method: 'POST' })
  state.deviceFlow = {
    active: true,
    code: data.user_code,
    uri: data.verification_uri,
    status: '等待浏览器授权',
    message: '',
  }
  bridge?.openExternal(data.verification_uri_complete || data.verification_uri)
  let interval = Math.max(3, Number(data.interval || 5))
  const poll = async () => {
    if (generation !== deviceFlowGeneration || !state.deviceFlow.active) return
    try {
      const result = await api('/api/auth/microsoft/device/poll', { method: 'POST' })
      if (generation !== deviceFlowGeneration) return
      if (result.status === 'success') {
        await loadAccounts()
        closeModal()
        toast(`已登录 ${result.account.name}`, 'ok')
        return
      }
      if (result.status === 'pending') {
        interval = Math.max(3, Number(result.interval || interval))
        state.deviceFlow.status = '等待浏览器授权'
        state.deviceFlow.message = '启动器会自动检查登录结果。'
        window.setTimeout(poll, interval * 1000)
        return
      }
      state.deviceFlow.status =
        result.status === 'expired' ? '设备代码已过期' : '登录未完成'
      state.deviceFlow.message = result.message || '请重新获取设备代码'
    } catch (error) {
      state.deviceFlow.status = '无法检查登录状态'
      state.deviceFlow.message = error.message
    }
  }
  window.setTimeout(poll, interval * 1000)
}

async function loadAccounts() {
  const payload = await api('/api/auth/accounts')
  state.accounts = payload.accounts || []
}

function replaceAccount(account) {
  const index = state.accounts.findIndex((item) => item.uuid === account.uuid)
  if (index >= 0) state.accounts.splice(index, 1, { ...state.accounts[index], ...account })
}

async function refreshSkinPreview(account, silent = true) {
  if (!account?.uuid || account.type !== 'microsoft') {
    throw new Error('请先登录微软正版账户')
  }
  try {
    const payload = await api(`/api/auth/accounts/${encodeURIComponent(account.uuid)}/skin`)
    const updated = { ...account, ...payload }
    replaceAccount(updated)
    if (state.modal === 'skin-preview' && state.modalData?.uuid === account.uuid) {
      state.modalData = updated
    }
    return updated
  } catch (error) {
    if (!silent) throw error
    return account
  }
}

async function openSkinPreview(account = activeAccount.value) {
  if (!account || account.type !== 'microsoft') {
    toast('请先登录微软正版账户，再预览皮肤', 'error')
    return
  }
  let preview = account
  if (!account.skin) {
    try {
      preview = await refreshSkinPreview(account, false)
    } catch (error) {
      toast(error.message, 'error', 6000)
      return
    }
  }
  showModal('skin-preview', { ...preview })
  safe(() => refreshSkinPreview(preview))
}

async function selectAccount(uuid) {
  await api('/api/auth/select', { method: 'POST', body: { uuid } })
  await loadAccounts()
  toast('账户已切换', 'ok')
}

async function offlineLogin(name) {
  const account = await api('/api/auth/offline', { method: 'POST', body: { username: name } })
  await loadAccounts()
  toast(`已登录 ${account.name}`, 'ok')
}

async function removeAccount(account) {
  if (!(await confirmAction('移除账户', `移除账户“${account.name}”？`, '移除', true))) return
  await api(`/api/auth/accounts/${encodeURIComponent(account.uuid)}`, { method: 'DELETE' })
  await loadAccounts()
  toast('账户已移除', 'ok')
}

function showWizard() {
  state.wizard = {
    open: true,
    step: 0,
    path: state.settings?.minecraft_directory || '',
    javaMajor: 21,
    createdInstanceId: null,
  }
}

function closeWizard() {
  state.wizard.open = false
}

async function finishFirstRun() {
  await api('/api/app/first-run', {
    method: 'POST',
    body: { disclaimer_accepted: true },
  })
  state.firstRunDone = true
  state.wizard.open = false
  if (!state.selectedId) await refreshInstances()
  if (state.selectedId) {
    state.view = 'instance'
    await loadInstance(state.selectedId)
  }
}

function acceptDisclaimer() {
  return api('/api/app/disclaimer', { method: 'POST' }).then(() => {
    state.disclaimerAccepted = true
    state.modal = null
    if (!state.firstRunDone) showWizard()
  })
}

async function navigate(view) {
  if (view === 'instance' && !state.selectedId) view = 'empty'
  state.view = view
  if (view === 'download') {
    await Promise.all([safe(loadVersions), safe(loadLoaders), safe(loadPopularModpacks)])
  }
  if (view === 'java') safe(loadJava)
}

async function refreshHealth() {
  try {
    state.health = await api('/api/health')
    updateStatus()
    return true
  } catch {
    setStatus('本地服务未连接', 'error')
    return false
  }
}

async function connectEvents() {
  eventSource?.close()
  eventSource = new EventSource(`${API}/api/events`)
  eventSource.onerror = () => {
    setStatus('事件流断开，正在重连', 'error')
  }
  eventSource.onmessage = (message) => {
    let event
    try {
      event = JSON.parse(message.data)
    } catch {
      return
    }
    if (event.type === 'task') upsertTask(event.task)
    if (event.type === 'hello') (event.tasks || []).forEach(upsertTask)
    if (event.type === 'instances.changed') safe(() => refreshInstances(state.selectedId))
    if (event.type === 'auth.changed' || event.type === 'auth.success') safe(loadAccounts)
    if (event.type === 'java.changed') safe(() => loadJava(true))
    if (event.type === 'mods.changed' && state.instance) safe(() => loadMods(true))
    if (
      event.type === 'content.changed' &&
      state.instance &&
      (!event.content_kind || event.content_kind === state.content.kind)
    ) {
      safe(loadContentLocal)
    }
    if (event.type === 'versions.changed') safe(() => loadVersions(true))
    if (event.type === 'game.started' && event.instance) {
      state.running[event.instance] = event.pid
      updateStatus()
    }
    if (event.type === 'game.exited' && event.instance) {
      delete state.running[event.instance]
      updateStatus()
    }
  }
}

async function initialize() {
  if (!(await refreshHealth())) {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 500))
      if (await refreshHealth()) break
    }
  }
  if (!state.health) {
    state.ready = true
    return
  }
  await loadBootstrap()
  await Promise.all([safe(loadJava), safe(loadAccounts)])
  const tasks = await api('/api/tasks')
  ;(tasks || []).forEach(upsertTask)
  await connectEvents()
  state.ready = true
}

export function useLauncher() {
  return {
    state,
    activeAccount,
    filteredInstances,
    visibleVersions,
    versionCategory,
    versionCategoryLabel,
    versionCategories: VERSION_CATEGORIES,
    initialize,
    navigate,
    selectInstance,
    loadInstance,
    setTab,
    loadOverview,
    loadMods,
    loadPopularMods,
    toggleMod,
    deleteMod,
    searchMods,
    installMod,
    isModDownloading,
    confirmModDependencies,
    cancelModDependencies,
    openDetails,
    loadContent,
    setContentKind,
    selectContentWorld,
    loadContentLocal,
    loadContentPopular,
    searchContent,
    installContent,
    toggleContent,
    deleteContent,
    openContentFolder,
    contentKindLabel,
    loadSaves,
    loadLogs,
    readLog,
    openFolder,
    repairInstance,
    launchGame,
    openNewInstance,
    createInstance,
    saveInstanceSettings,
    deleteInstance,
    duplicateInstance,
    clearTasks,
    loadVersions,
    loadLoaders,
    loadLoaderVersions,
    loadJava,
    installJava,
    loadPopularModpacks,
    searchModpacks,
    installModpack,
    importModpack,
    saveSettings,
    showModal,
    closeModal,
    confirmAction,
    beginMicrosoftLogin,
    loadAccounts,
    openSkinPreview,
    refreshSkinPreview,
    selectAccount,
    offlineLogin,
    removeAccount,
    showWizard,
    closeWizard,
    finishFirstRun,
    acceptDisclaimer,
    applyTheme,
    toast,
    relativeTime,
    formatBytes,
    formatCount,
    loaderLabel,
    javaMajor,
    safe,
    api,
  }
}
