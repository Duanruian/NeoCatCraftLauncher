<script setup>
import { computed, onMounted, ref } from 'vue'
import { useLauncher } from '../composables/useLauncher'
import InstanceIcon from '../components/InstanceIcon.vue'
import BakaSelect from '../components/BakaSelect.vue'
import CatalogIcon from '../components/CatalogIcon.vue'

const launcher = useLauncher()
const {
  state,
  activeAccount,
  safe,
  relativeTime,
  formatBytes,
  formatCount,
  loaderLabel,
  openFolder,
  repairInstance,
  launchGame,
  setTab,
  toggleMod,
  deleteMod,
  searchMods,
  installMod,
  isModDownloading,
  openDetails,
  setContentKind,
  loadContentLocal,
  selectContentWorld,
  searchContent,
  installContent,
  toggleContent,
  deleteContent,
  openContentFolder,
  contentKindLabel,
  readLog,
  showModal,
} = launcher

const modFilter = ref('')
const tabs = [
  { id: 'overview', label: '概览', icon: '⌂' },
  { id: 'mods', label: '模组管理', icon: '▦' },
  { id: 'content', label: '资源扩展', icon: '◇' },
  { id: 'saves', label: '存档', icon: '▣' },
  { id: 'logs', label: '日志', icon: '≡' },
]

const instance = computed(() => state.instance)
const requiredJava = computed(() => instance.value?.required_java || 17)
const javaReady = computed(() => {
  const java = instance.value?.java
  return Boolean(java?.path && Number(java.major || 0) >= requiredJava.value && !java.mismatch)
})
const launchBlocked = computed(() => {
  if (!activeAccount.value) return '请先登录玩家账户'
  if (!instance.value?.installed) return '实例版本尚未安装'
  if (!javaReady.value) return `需要 Java ${requiredJava.value}`
  return ''
})
const running = computed(() => Boolean(state.running[state.selectedId]))
const filteredMods = computed(() => {
  const list = state.mods?.mods || []
  const query = modFilter.value.trim().toLowerCase()
  if (!query) return list
  return list.filter((mod) => [mod.name, mod.file_name, mod.mod_id].filter(Boolean).join(' ').toLowerCase().includes(query))
})
function modDisplayName(mod) {
  const fallback = String(mod?.file_name || '未命名模组').replace(/\.jar(?:\.disabled)?$/i, '')
  return String(mod?.name || fallback)
}
const latestSave = computed(() => state.saves?.saves?.[0] || null)
const platformOptions = [
  { value: 'all', label: 'CurseForge + Modrinth', hint: '聚合搜索' },
  { value: 'modrinth', label: 'Modrinth', hint: '开源社区' },
  { value: 'curseforge', label: 'CurseForge', hint: '大型目录' },
]
const contentKindOptions = [
  { value: 'resourcepack', label: '资源包', hint: '材质与界面' },
  { value: 'shader', label: '光影包', hint: '画面效果' },
  { value: 'datapack', label: '数据包', hint: '游戏规则与内容' },
]
const contentWorldOptions = computed(() => [
  { value: '', label: '实例暂存目录', hint: '未绑定存档' },
  ...(state.saves?.saves || []).map((save) => ({ value: save.name, label: save.name })),
])
const logOptions = computed(() =>
  state.logs.map((log) => ({ value: log.name, label: log.name })),
)

function run(task) {
  safe(task)
}

onMounted(() => {
  safe(launcher.loadOverview)
})
</script>

<template>
  <div v-if="instance" class="instance-view">
    <header class="instance-header">
      <div class="instance-identity">
        <InstanceIcon
          class="instance-badge"
          :loader="instance.loader"
          :icon="instance.icon"
          size="hero"
        />
        <div>
          <span class="eyebrow">CURRENT INSTANCE</span>
          <div class="instance-title-row">
            <h1>{{ instance.name }}</h1>
            <span class="soft-tag">{{ instance.isolation === false ? '共享目录' : '隔离实例' }}</span>
          </div>
          <p>
            Minecraft {{ instance.mc_version }}
            <i>•</i>
            {{ loaderLabel(instance.loader) }} {{ instance.loader_version }}
            <i>•</i>
            {{ relativeTime(instance.last_played) }}
          </p>
        </div>
      </div>
      <div class="instance-actions">
        <button class="baka-button baka-button--plain" @click="run(() => openFolder())">打开文件夹</button>
        <button class="baka-button baka-button--plain" @click="showModal('instance-settings')">实例设置</button>
        <button class="round-action" title="更多" @click="run(repairInstance)">＋</button>
      </div>
    </header>

    <section class="launch-banner">
      <div class="launch-banner__art" aria-hidden="true">
        <span class="pixel-cloud pixel-cloud--one"></span>
        <span class="pixel-cloud pixel-cloud--two"></span>
        <span class="pixel-hill"></span>
        <span class="pixel-grass"></span>
      </div>
      <div class="launch-banner__copy">
        <span class="banner-kicker">READY TO PLAY?</span>
        <h2>{{ running ? '冒险正在进行中' : launchBlocked ? '再检查一下就能出发' : '欢迎回来，冒险家！' }}</h2>
        <p>{{ launchBlocked || '账户、Java 与游戏文件均已准备就绪。' }}</p>
        <div class="launch-facts">
          <span :class="{ warn: !activeAccount }"><i>●</i>{{ activeAccount?.name || '未登录' }}</span>
          <span :class="{ warn: !javaReady }"><i>●</i>{{ javaReady ? `Java ${instance.java?.major}` : `缺少 Java ${requiredJava}` }}</span>
          <span><i>●</i>{{ state.mods?.count ?? '—' }} 个模组</span>
        </div>
      </div>
      <div class="launch-banner__action">
        <button
          class="launch-orb"
          :class="{ disabled: launchBlocked || state.launchBusy, running }"
          :disabled="Boolean(launchBlocked) || running || state.launchBusy"
          @click="run(launchGame)"
        >
          <span class="launch-orb__icon">{{ running ? 'Ⅱ' : '▶' }}</span>
          <span>
            <strong>{{ state.launchBusy ? '正在准备' : running ? '游戏运行中' : '启动游戏' }}</strong>
            <small>{{ launchBlocked || 'LET’S GO!' }}</small>
          </span>
        </button>
      </div>
    </section>

    <nav class="baka-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="{ active: state.tab === tab.id }"
        @click="setTab(tab.id)"
      >
        <span>{{ tab.icon }}</span>
        {{ tab.label }}
      </button>
    </nav>

    <section v-if="state.tab === 'overview'" class="tab-stage">
      <div class="overview-layout">
        <article class="baka-card readiness-card">
          <header>
            <span class="card-icon">✓</span>
            <div>
              <small>LAUNCH CHECK</small>
              <h3>启动检查</h3>
            </div>
          </header>
          <div class="readiness-list">
            <div><span>账户</span><b :class="{ bad: !activeAccount }">{{ activeAccount?.name || '未登录' }}</b></div>
            <div><span>Java</span><b :class="{ bad: !javaReady }">{{ javaReady ? `Java ${instance.java?.major}` : '未就绪' }}</b></div>
            <div><span>游戏版本</span><b :class="{ bad: !instance.installed }">{{ instance.installed ? '已安装' : '需要修复' }}</b></div>
            <div><span>实例隔离</span><b>{{ instance.isolation === false ? '关闭' : '已启用' }}</b></div>
          </div>
        </article>
        <article class="baka-card stat-card stat-card--blue">
          <span class="stat-emoji">▦</span>
          <small>MODS</small>
          <strong>{{ state.mods?.count ?? '—' }}</strong>
          <p>{{ (state.mods?.mods || []).filter((mod) => mod.enabled !== false).length }} 个模组已启用</p>
          <button class="text-button" @click="setTab('mods')">管理模组 →</button>
        </article>
        <article class="baka-card stat-card stat-card--orange">
          <span class="stat-emoji">▣</span>
          <small>WORLDS</small>
          <strong>{{ state.saves?.count ?? '—' }}</strong>
          <p>{{ latestSave ? `最近：${latestSave.name}` : '还没有本地存档' }}</p>
          <button class="text-button" @click="setTab('saves')">查看存档 →</button>
        </article>
        <article class="baka-card path-card">
          <div>
            <small>INSTANCE FOLDER</small>
            <h3>独立游戏目录</h3>
            <code>{{ instance.directory }}</code>
          </div>
          <button class="baka-button baka-button--plain" @click="run(() => openFolder())">打开目录</button>
        </article>
      </div>
    </section>

    <section v-else-if="state.tab === 'mods'" class="tab-stage mods-layout">
      <div class="baka-card mods-local">
        <header class="section-head">
          <div>
            <small>INSTANCE MODS</small>
            <h3>本地模组</h3>
            <p>{{ instance.name }} · {{ state.mods?.count || 0 }} 个文件</p>
          </div>
          <div class="section-actions">
            <input v-model="modFilter" class="baka-input compact" placeholder="筛选模组" />
            <button class="icon-button" title="刷新" @click="run(() => launcher.loadMods(true))">↻</button>
            <button class="icon-button" title="打开目录" @click="run(() => openFolder('mods'))">↗</button>
          </div>
        </header>
        <div v-if="state.modLoading" class="loading-row"><span class="spinner"></span> 正在读取模组…</div>
        <div v-else-if="!filteredMods.length" class="empty-inline">
          <strong>这里还是空的</strong>
          <p>{{ instance.loader === 'vanilla' ? '当前是原版实例，安装加载器后才能加载模组。' : '从右侧搜索并安装第一个模组吧。' }}</p>
        </div>
        <div v-else class="mod-list">
          <article
            v-for="mod in filteredMods"
            :key="mod.file_name"
            class="mod-row is-clickable"
            :class="{ disabled: mod.enabled === false }"
            role="button"
            tabindex="0"
            @click="openDetails(mod, 'mod')"
            @keydown.enter.self="openDetails(mod, 'mod')"
          >
            <CatalogIcon :src="mod.icon" :name="modDisplayName(mod)" kind="mod" />
            <div class="mod-copy">
              <strong :title="modDisplayName(mod)">{{ modDisplayName(mod) }}</strong>
              <small>{{ mod.file_name }} · {{ formatBytes(mod.size) }}</small>
            </div>
            <button class="toggle" :class="{ on: mod.enabled !== false }" @click.stop="run(() => toggleMod(mod))">
              <i></i>
            </button>
            <button class="text-button danger" @click.stop="run(() => deleteMod(mod))">删除</button>
          </article>
        </div>
      </div>

      <div class="baka-card mods-online">
        <header class="section-head">
          <div>
            <small>FIND SOMETHING NEW</small>
            <h3>在线模组</h3>
            <p>结果自动匹配 {{ instance.mc_version }} · {{ loaderLabel(instance.loader) }}</p>
          </div>
        </header>
        <form class="search-box" @submit.prevent="run(searchMods)">
          <BakaSelect
            v-model="state.modPlatform"
            :options="platformOptions"
            compact
            aria-label="模组搜索平台"
          />
          <input v-model="state.modQuery" class="baka-input" placeholder="搜索模组名称…" />
          <button class="baka-button baka-button--primary" :disabled="state.modSearching">
            {{ state.modSearching ? '搜索中' : '搜索' }}
          </button>
        </form>
        <p v-if="state.modSearchSummary" class="catalog-summary">{{ state.modSearchSummary }}</p>
        <p v-if="state.modSearchWarnings.length" class="catalog-warning">
          {{ state.modSearchWarnings.join(' · ') }}
        </p>
        <div v-if="state.modSearching && !state.modSearchHits.length" class="loading-row">
          <span class="spinner"></span> 正在加载热门模组…
        </div>
        <div v-else-if="!state.modSearchHits.length" class="empty-inline">
          <strong>寻找新伙伴</strong>
          <p>在线搜索结果只会安装到“{{ instance.name }}”。</p>
        </div>
        <div v-else class="mod-result-list">
          <article
            v-for="hit in state.modSearchHits"
            :key="`${hit.platform}-${hit.id}`"
            class="mod-result is-clickable"
            role="button"
            tabindex="0"
            @click="openDetails(hit, 'mod')"
            @keydown.enter.self="openDetails(hit, 'mod')"
          >
            <CatalogIcon :src="hit.icon" :name="hit.title" kind="mod" />
            <div>
              <strong>{{ hit.title }}</strong>
              <p>{{ hit.description }}</p>
              <small>{{ formatCount(hit.downloads) }} 次下载</small>
            </div>
            <button
              class="baka-button baka-button--mini"
              :disabled="instance.loader === 'vanilla' || isModDownloading(hit)"
              @click.stop="run(() => installMod(hit))"
            >
              {{ isModDownloading(hit) ? '准备中…' : '安装' }}
            </button>
          </article>
        </div>
      </div>
    </section>

    <section v-else-if="state.tab === 'content'" class="tab-stage content-layout">
      <div class="baka-card content-local">
        <header class="section-head">
          <div>
            <small>INSTANCE CONTENT</small>
            <h3>{{ contentKindLabel(state.content.kind) }}管理</h3>
            <p>{{ state.content.items.length }} 个本地文件 · {{ state.content.directory || '正在读取目录…' }}</p>
          </div>
          <div class="section-actions">
            <button class="icon-button" title="刷新" @click="run(loadContentLocal)">↻</button>
            <button class="icon-button" title="打开目录" @click="run(openContentFolder)">↗</button>
          </div>
        </header>

        <div class="content-kind-tabs">
          <button
            v-for="option in contentKindOptions"
            :key="option.value"
            :class="{ active: state.content.kind === option.value }"
            @click="run(() => setContentKind(option.value))"
          >
            <strong>{{ option.label }}</strong>
            <small>{{ option.hint }}</small>
          </button>
        </div>

        <div v-if="state.content.kind === 'datapack'" class="content-world-row">
          <span>安装到存档</span>
          <BakaSelect
            v-model="state.content.world"
            :options="contentWorldOptions"
            compact
            aria-label="数据包目标存档"
            @change="(world) => run(() => selectContentWorld(world))"
          />
        </div>

        <div v-if="state.content.loading" class="loading-row">
          <span class="spinner"></span> 正在读取{{ contentKindLabel(state.content.kind) }}…
        </div>
        <div v-else-if="!state.content.items.length" class="empty-inline">
          <strong>还没有本地{{ contentKindLabel(state.content.kind) }}</strong>
          <p>从右侧热门列表安装，或者直接把文件放进对应文件夹。</p>
        </div>
        <div v-else class="content-local-list">
          <article
            v-for="item in state.content.items"
            :key="item.file_name"
            class="content-row"
            :class="{ disabled: item.enabled === false }"
          >
            <CatalogIcon :src="item.icon" :name="item.name" :kind="state.content.kind" />
            <div>
              <strong>{{ item.name }}</strong>
              <small>{{ formatBytes(item.size) }} · {{ relativeTime(item.modified) }}</small>
            </div>
            <button class="toggle" :class="{ on: item.enabled !== false }" @click="run(() => toggleContent(item))">
              <i></i>
            </button>
            <button class="text-button danger" @click="run(() => deleteContent(item))">删除</button>
          </article>
        </div>
      </div>

      <div class="baka-card content-online">
        <header class="section-head">
          <div>
            <small>DISCOVER CONTENT</small>
            <h3>在线{{ contentKindLabel(state.content.kind) }}</h3>
            <p>默认聚合 CurseForge 与 Modrinth</p>
          </div>
        </header>
        <form class="search-box" @submit.prevent="run(searchContent)">
          <BakaSelect
            v-model="state.content.platform"
            :options="platformOptions"
            compact
            aria-label="内容搜索平台"
          />
          <input
            v-model="state.content.query"
            class="baka-input"
            :placeholder="`搜索${contentKindLabel(state.content.kind)}…`"
          />
          <button class="baka-button baka-button--primary" :disabled="state.content.searching">
            {{ state.content.searching ? '搜索中…' : '搜索' }}
          </button>
        </form>
        <p class="catalog-summary">{{ state.content.summary }}</p>
        <p v-if="state.content.warnings.length" class="catalog-warning">
          {{ state.content.warnings.join(' · ') }}
        </p>
        <div v-if="state.content.searching && !state.content.catalog.length" class="loading-row">
          <span class="spinner"></span> 正在获取热门内容…
        </div>
        <div v-else class="content-result-grid">
          <article
            v-for="hit in state.content.catalog"
            :key="`${hit.platform}-${hit.id}`"
            class="content-result is-clickable"
            role="button"
            tabindex="0"
            @click="openDetails(hit, state.content.kind)"
            @keydown.enter.self="openDetails(hit, state.content.kind)"
          >
            <CatalogIcon :src="hit.icon" :name="hit.title" :kind="state.content.kind" size="card" />
            <div>
              <strong>{{ hit.title }}</strong>
              <p>{{ hit.description }}</p>
              <small>{{ hit.platform }} · {{ formatCount(hit.downloads) }} 次下载</small>
            </div>
            <button class="baka-button baka-button--mini" @click.stop="run(() => installContent(hit))">
              安装
            </button>
          </article>
        </div>
      </div>
    </section>

    <section v-else-if="state.tab === 'saves'" class="tab-stage">
      <div class="section-head standalone">
        <div>
          <small>YOUR WORLDS</small>
          <h2>{{ instance.name }} 的存档</h2>
          <p>{{ state.saves?.directory || '正在读取…' }}</p>
        </div>
        <button class="baka-button baka-button--plain" @click="run(() => openFolder('saves'))">打开存档目录</button>
      </div>
      <div v-if="state.saves?.saves?.length" class="save-grid">
        <article v-for="save in state.saves.saves" :key="save.name" class="save-card">
          <div class="save-art">{{ save.name.slice(0, 1).toUpperCase() }}</div>
          <strong>{{ save.name }}</strong>
          <span>{{ formatBytes(save.size) }} · {{ relativeTime(save.modified) }}</span>
        </article>
      </div>
      <div v-else class="empty-inline baka-card">
        <strong>还没有存档</strong>
        <p>进入游戏并创建世界后，存档会显示在这里。</p>
      </div>
    </section>

    <section v-else class="tab-stage">
      <div class="baka-card log-card">
        <header class="section-head">
          <div>
            <small>DEBUG LOG</small>
            <h3>实例日志</h3>
          </div>
          <div class="section-actions">
            <BakaSelect
              v-model="state.selectedLog"
              :options="logOptions"
              compact
              aria-label="日志文件"
              @change="run(() => readLog(state.selectedLog))"
            />
            <button class="icon-button" title="刷新" @click="run(launcher.loadLogs)">↻</button>
            <button class="icon-button" title="打开目录" @click="run(() => openFolder('logs'))">↗</button>
          </div>
        </header>
        <pre class="log-viewer">{{ state.logContent || '暂无日志内容。启动一次游戏后再来看看。' }}</pre>
      </div>
    </section>
  </div>
</template>
