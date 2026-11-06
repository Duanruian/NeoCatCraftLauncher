<script setup>
import { computed } from 'vue'
import { useLauncher } from '../composables/useLauncher'
import BakaSelect from '../components/BakaSelect.vue'
import CatalogIcon from '../components/CatalogIcon.vue'

const launcher = useLauncher()
const {
  state,
  visibleVersions,
  versionCategories,
  versionCategoryLabel,
  safe,
  formatCount,
  formatBytes,
  loadPopularModpacks,
  searchModpacks,
  installModpack,
  importModpack,
  loadVersions,
  loadLoaderVersions,
  openNewInstance,
  openDetails,
} = launcher

const platformOptions = [
  { value: 'all', label: 'CurseForge + Modrinth', hint: '聚合搜索' },
  { value: 'modrinth', label: 'Modrinth', hint: '开源社区' },
  { value: 'curseforge', label: 'CurseForge', hint: '大型目录' },
]
const loaderTypeOptions = computed(() =>
  state.loaders.map((loader) => ({ value: loader.id, label: loader.name })),
)
const modpackCards = computed(() =>
  state.modpacks.results.length ? state.modpacks.results : state.modpacks.popular,
)
</script>

<template>
  <div class="page-view download-view">
    <header class="page-hero page-hero--download">
      <div>
        <span class="eyebrow">DISCOVER & DOWNLOAD</span>
        <h1>今天想玩点什么？</h1>
        <p>先看看大家都在玩的热门整合包，也可以搜索特定主题。</p>
      </div>
      <button class="baka-button baka-button--plain" @click="safe(importModpack)">导入本地整合包</button>
      <span class="hero-doodle">✦</span>
    </header>

    <section class="baka-card discover-card">
      <header class="section-head">
        <div>
          <small>POPULAR MODPACKS</small>
          <h2>{{ state.modpacks.results.length ? '搜索结果' : '热门整合包' }}</h2>
          <p>{{ state.modpacks.summary }}</p>
        </div>
        <button class="baka-button baka-button--mini" @click="safe(() => loadPopularModpacks(true))">刷新热门</button>
      </header>
      <form class="search-box search-box--large" @submit.prevent="safe(searchModpacks)">
        <BakaSelect
          v-model="state.modpacks.platform"
          :options="platformOptions"
          compact
          aria-label="整合包搜索平台"
        />
        <input v-model="state.modpacks.query" class="baka-input" placeholder="搜索整合包，例如空岛、冒险、科技…" />
        <input v-model="state.modpacks.minecraft" class="baka-input compact" placeholder="MC 版本（可选）" />
        <button class="baka-button baka-button--primary" :disabled="state.modpacks.searching">
          {{ state.modpacks.searching ? '搜索中…' : '搜索' }}
        </button>
      </form>
      <div v-if="state.modpacks.loading" class="loading-row"><span class="spinner"></span> 正在获取热门整合包…</div>
      <div v-else class="modpack-grid">
        <article
          v-for="(pack, index) in modpackCards"
          :key="`${pack.platform}-${pack.id}`"
          class="modpack-card is-clickable"
          role="button"
          tabindex="0"
          @click="openDetails(pack, 'modpack')"
          @keydown.enter.self="openDetails(pack, 'modpack')"
        >
          <span class="modpack-rank">#{{ index + 1 }}</span>
          <CatalogIcon :src="pack.icon" :name="pack.title" kind="modpack" size="card" />
          <div class="modpack-copy">
            <strong>{{ pack.title || pack.slug }}</strong>
            <small>{{ pack.author || '未知作者' }}</small>
            <p>{{ pack.description || '没有简介' }}</p>
            <div class="modpack-facts">
              <span>↓ {{ formatCount(pack.downloads) }}</span>
              <span v-for="version in (pack.game_versions || []).slice(0, 2)" :key="version">{{ version }}</span>
            </div>
          </div>
          <button
            class="baka-button baka-button--primary baka-button--mini"
            @click.stop="safe(() => installModpack(pack))"
          >
            安装
          </button>
        </article>
      </div>
      <p v-if="state.modpacks.warnings.length" class="catalog-warning">
        {{ state.modpacks.warnings.join(' · ') }}
      </p>
    </section>

    <div class="download-columns">
      <section class="baka-card version-card">
        <header class="section-head">
          <div>
            <small>MINECRAFT VERSIONS</small>
            <h2>游戏版本</h2>
            <p>{{ visibleVersions.length }} 个可选版本</p>
          </div>
          <button class="icon-button" title="刷新" @click="safe(() => loadVersions(true))">↻</button>
        </header>
        <div class="segmented version-segments" role="tablist" aria-label="Minecraft 版本类型">
          <button
            v-for="category in versionCategories"
            :key="category.id"
            role="tab"
            :aria-selected="state.versions.filter === category.id"
            :class="{ active: state.versions.filter === category.id }"
            @click="state.versions.filter = category.id"
          >
            {{ category.label }}
          </button>
        </div>
        <input v-model="state.versions.query" class="baka-input" placeholder="搜索版本号" />
        <div class="compact-list">
          <button
            v-for="version in visibleVersions.slice(0, 80)"
            :key="version.id"
            class="version-item"
            @click="openNewInstance({ mc_version: version.id })"
          >
            <span>{{ version.id }}</span>
            <small>{{ versionCategoryLabel(version) }} · 创建实例 →</small>
          </button>
        </div>
      </section>

      <section class="baka-card loader-card">
        <header class="section-head">
          <div>
            <small>MOD LOADERS</small>
            <h2>模组加载器</h2>
            <p>查看指定版本的加载器版本</p>
          </div>
        </header>
        <div class="two-fields">
          <BakaSelect
            v-model="state.loaderType"
            :options="loaderTypeOptions"
            aria-label="模组加载器"
            @change="safe(loadLoaderVersions)"
          />
          <input v-model="state.loaderMinecraft" class="baka-input" placeholder="例如 1.20.1" @change="safe(loadLoaderVersions)" />
        </div>
        <div class="compact-list loader-list">
          <button
            v-for="version in state.loaderVersions.slice(0, 30)"
            :key="version"
            class="version-item"
            @click="openNewInstance({ mc_version: state.loaderMinecraft, loader: state.loaderType, loader_version: version })"
          >
            <span>{{ version }}</span>
            <small>创建 {{ state.loaderType }} 实例 →</small>
          </button>
          <div v-if="!state.loaderVersions.length" class="empty-inline">
            <strong>输入 Minecraft 版本</strong>
            <p>选择加载器版本后可直接创建对应实例。</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
