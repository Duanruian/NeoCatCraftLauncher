<script setup>
import { reactive, watch } from 'vue'
import { useLauncher } from '../composables/useLauncher'
import BakaSelect from '../components/BakaSelect.vue'

const launcher = useLauncher()
const {
  state,
  safe,
  saveSettings,
  navigate,
  showWizard,
  applyTheme,
  toast,
} = launcher

const form = reactive({
  minecraft_directory: '',
  javas_directory: '',
  java_path: '',
  auto_download_java: true,
  memory_mb: 4096,
  min_memory_mb: 512,
  jvm_args: '',
  resolution_enabled: false,
  resolution_width: 1280,
  resolution_height: 720,
  download_retries: 3,
  download_timeout: 60,
  minecraft_download_source: 'official',
  bmclapi_base: 'https://bmclapi2.bangbang93.com',
  preferred_platform: 'all',
  microsoft_client_id: '',
  curseforge_api_key: '',
  curseforge_api_key_set: false,
  theme: 'ocean',
  theme_mode: 'light',
  close_animation: true,
})

const accents = [
  { id: 'ocean', label: '天空蓝', color: '#4cc2ff' },
  { id: 'forest', label: '草方块绿', color: '#63d879' },
  { id: 'amber', label: '暖阳橙', color: '#f2a63b' },
  { id: 'violet', label: '紫水晶', color: '#b68cff' },
  { id: 'rose', label: '樱花粉', color: '#ff7a90' },
]
const themeModeOptions = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '跟随系统' },
]
const platformOptions = [
  { value: 'all', label: '双平台聚合', hint: '推荐' },
  { value: 'modrinth', label: 'Modrinth' },
  { value: 'curseforge', label: 'CurseForge' },
]
const downloadSourceOptions = [
  { value: 'official', label: 'Mojang 官方源', hint: '默认' },
  { value: 'bmclapi', label: 'BMCLAPI 镜像', hint: '国内加速' },
]

watch(
  () => state.settings,
  (settings) => {
    if (!settings) return
    Object.assign(form, {
      minecraft_directory: settings.minecraft_directory || '',
      javas_directory: settings.javas_directory || '',
      java_path: settings.java_path || '',
      auto_download_java: settings.auto_download_java !== false,
      memory_mb: settings.memory_mb || 4096,
      min_memory_mb: settings.min_memory_mb || 512,
      jvm_args: settings.jvm_args || '',
      resolution_enabled: settings.resolution?.enabled || false,
      resolution_width: settings.resolution?.width || 1280,
      resolution_height: settings.resolution?.height || 720,
      download_retries: settings.download_retries || 3,
      download_timeout: settings.download_timeout || 60,
      minecraft_download_source: settings.minecraft_download_source || 'official',
      bmclapi_base: settings.bmclapi_base || 'https://bmclapi2.bangbang93.com',
      preferred_platform: settings.preferred_platform || 'all',
      microsoft_client_id: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        settings.microsoft_client_id || '',
      )
        ? settings.microsoft_client_id
        : '',
      curseforge_api_key: '',
      curseforge_api_key_set: settings.curseforge_api_key_set === true,
      theme: settings.theme || 'ocean',
      theme_mode: settings.theme_mode || 'light',
      close_animation: settings.close_animation !== false,
    })
  },
  { immediate: true, deep: true },
)

function previewTheme() {
  applyTheme({ ...form, theme_mode: form.theme_mode, theme: form.theme })
}

function chooseFolder(key, title) {
  safe(async () => {
    const path = await window.neo?.pickDirectory(title)
    if (path) form[key] = path
  })
}

function submit() {
  safe(async () => {
    await saveSettings({
      minecraft_directory: form.minecraft_directory.trim(),
      javas_directory: form.javas_directory.trim(),
      java_path: form.java_path.trim(),
      auto_download_java: form.auto_download_java,
      memory_mb: Number(form.memory_mb),
      min_memory_mb: Number(form.min_memory_mb),
      jvm_args: form.jvm_args,
      resolution: {
        enabled: form.resolution_enabled,
        width: Number(form.resolution_width),
        height: Number(form.resolution_height),
      },
      download_retries: Number(form.download_retries),
      download_timeout: Number(form.download_timeout),
      minecraft_download_source: form.minecraft_download_source,
      bmclapi_base: form.bmclapi_base.trim() || 'https://bmclapi2.bangbang93.com',
      preferred_platform: form.preferred_platform,
      microsoft_client_id: form.microsoft_client_id.trim(),
      ...(form.curseforge_api_key.trim()
        ? { curseforge_api_key: form.curseforge_api_key.trim() }
        : {}),
      theme: form.theme,
      theme_mode: form.theme_mode,
      close_animation: form.close_animation,
    })
    await launcher.loadJava(true)
  })
}
</script>

<template>
  <div class="page-view settings-view">
    <header class="page-hero page-hero--settings">
      <div>
        <span class="eyebrow">MAKE IT YOURS</span>
        <h1>设置你的启动器</h1>
        <p>从主题、存储到 Java 运行时，所有选项都在这里。</p>
      </div>
      <div class="hero-actions">
        <button class="baka-button baka-button--plain" @click="navigate('java')">Java 运行环境</button>
        <button class="baka-button baka-button--plain" @click="showWizard">重新运行引导</button>
      </div>
      <span class="hero-doodle">★</span>
    </header>

    <div class="settings-grid">
      <section class="baka-card setting-section theme-section">
        <header><span class="set-icon">✦</span><div><small>APPEARANCE</small><h2>外观与主题</h2></div></header>
        <label class="setting-line">
          <span><strong>显示模式</strong><small>浅色主题采用 BakaXL 风格的明亮青蓝配色。</small></span>
          <BakaSelect
            v-model="form.theme_mode"
            :options="themeModeOptions"
            compact
            aria-label="显示模式"
            @change="previewTheme"
          />
        </label>
        <div class="setting-line theme-line">
          <span><strong>主题颜色</strong><small>用于按钮、高亮和选中状态。</small></span>
          <div class="theme-dots">
            <button
              v-for="accent in accents"
              :key="accent.id"
              class="theme-dot"
              :class="{ active: form.theme === accent.id }"
              :style="{ '--dot': accent.color }"
              :title="accent.label"
              :aria-label="accent.label"
              @click="form.theme = accent.id; previewTheme()"
            ></button>
          </div>
        </div>
        <label class="setting-line">
          <span><strong>关闭动画</strong><small>退出时播放简短的过渡动画。</small></span>
          <button class="toggle" :class="{ on: form.close_animation }" @click="form.close_animation = !form.close_animation">
            <i></i>
          </button>
        </label>
      </section>

      <section class="baka-card setting-section">
        <header><span class="set-icon">⌂</span><div><small>STORAGE</small><h2>游戏目录</h2></div></header>
        <label class="setting-line stack">
          <span><strong>Minecraft 根目录</strong><small>默认版本、资源缓存和实例目录的根路径。</small></span>
          <div class="folder-row">
            <input v-model="form.minecraft_directory" class="baka-input" />
            <button class="baka-button baka-button--mini" @click="chooseFolder('minecraft_directory', '选择 .minecraft 根目录')">浏览</button>
          </div>
        </label>
        <label class="setting-line stack">
          <span><strong>Java 运行时目录</strong><small>受管 Zulu 运行时的保存位置。</small></span>
          <div class="folder-row">
            <input v-model="form.javas_directory" class="baka-input" />
            <button class="baka-button baka-button--mini" @click="chooseFolder('javas_directory', '选择 Java 运行时目录')">浏览</button>
          </div>
        </label>
      </section>

      <section class="baka-card setting-section">
        <header><span class="set-icon">⇄</span><div><small>DOWNLOAD</small><h2>下载加速</h2></div></header>
        <label class="setting-line">
          <span>
            <strong>Minecraft 下载源</strong>
            <small>控制游戏本体、资源文件、库文件与加载器相关下载。</small>
          </span>
          <BakaSelect
            v-model="form.minecraft_download_source"
            :options="downloadSourceOptions"
            compact
            aria-label="Minecraft 下载源"
          />
        </label>
        <label v-if="form.minecraft_download_source === 'bmclapi'" class="setting-line stack">
          <span>
            <strong>BMCLAPI 地址</strong>
            <small>镜像失败时会自动回退到对应的官方地址。</small>
          </span>
          <input
            v-model="form.bmclapi_base"
            class="baka-input"
            placeholder="https://bmclapi2.bangbang93.com"
          />
        </label>
      </section>

      <section class="baka-card setting-section">
        <header><span class="set-icon">⚡</span><div><small>PERFORMANCE</small><h2>运行与内存</h2></div></header>
        <label class="setting-line">
          <span><strong>自动安装 Java</strong><small>发现实例缺少 Java 时自动下载 Zulu。</small></span>
          <button class="toggle" :class="{ on: form.auto_download_java }" @click="form.auto_download_java = !form.auto_download_java"><i></i></button>
        </label>
        <label class="setting-line">
          <span><strong>最大内存</strong><small>单位为 MB。</small></span>
          <input v-model.number="form.memory_mb" class="baka-input number-input" type="number" min="512" />
        </label>
        <label class="setting-line">
          <span><strong>最小内存</strong><small>单位为 MB。</small></span>
          <input v-model.number="form.min_memory_mb" class="baka-input number-input" type="number" min="256" />
        </label>
        <label class="setting-line">
          <span><strong>固定游戏窗口</strong><small>关闭时由 Minecraft 自行决定窗口尺寸。</small></span>
          <button class="toggle" :class="{ on: form.resolution_enabled }" @click="form.resolution_enabled = !form.resolution_enabled"><i></i></button>
        </label>
        <div class="setting-line">
          <span><strong>窗口尺寸</strong><small>仅在开启固定窗口时生效。</small></span>
          <div class="resolution-inputs">
            <input v-model.number="form.resolution_width" class="baka-input number-input" type="number" :disabled="!form.resolution_enabled" />
            <span>×</span>
            <input v-model.number="form.resolution_height" class="baka-input number-input" type="number" :disabled="!form.resolution_enabled" />
          </div>
        </div>
        <label class="setting-line stack">
          <span><strong>JVM 参数</strong><small>留空或使用默认兼容参数。</small></span>
          <textarea v-model="form.jvm_args" class="baka-input code-input"></textarea>
        </label>
      </section>

      <section class="baka-card setting-section">
        <header><span class="set-icon">◎</span><div><small>ACCOUNT</small><h2>Microsoft 登录</h2></div></header>
        <label class="setting-line stack">
          <span><strong>自定义 Client ID</strong><small>留空使用 mcauth3 内置公共 Client ID。</small></span>
          <input v-model="form.microsoft_client_id" class="baka-input" placeholder="可选" />
        </label>
        <label class="setting-line">
          <span><strong>默认下载平台</strong><small>用于模组和整合包搜索。</small></span>
          <BakaSelect
            v-model="form.preferred_platform"
            :options="platformOptions"
            aria-label="默认下载平台"
          />
        </label>
        <label class="setting-line stack">
          <span>
            <strong>CurseForge API Key</strong>
            <small>{{ form.curseforge_api_key_set ? '已保存，留空不会覆盖现有密钥。' : '仅保存在本机设置中，不会写入安装包。' }}</small>
          </span>
          <input
            v-model="form.curseforge_api_key"
            class="baka-input"
            type="password"
            autocomplete="off"
            placeholder="粘贴 CurseForge API Key"
          />
        </label>
      </section>
    </div>

    <div class="settings-save-row">
      <span>版本隔离会确保每个实例拥有独立的模组、存档与配置。</span>
      <button class="baka-button baka-button--primary" @click="submit">保存全部设置</button>
    </div>
  </div>
</template>
