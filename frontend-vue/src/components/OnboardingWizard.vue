<script setup>
import { computed } from 'vue'
import { useLauncher } from '../composables/useLauncher'
import MicrosoftLogo from './MicrosoftLogo.vue'
import BakaSelect from './BakaSelect.vue'

const launcher = useLauncher()
const {
  state,
  safe,
  saveSettings,
  finishFirstRun,
  installJava,
  openNewInstance,
  showModal,
} = launcher
const steps = ['存储位置', 'Java', '玩家账户', '第一个实例', '准备完成']
const javaOptions = [8, 11, 16, 17, 21, 25].map((major) => ({
  value: major,
  label: `Java ${major}`,
}))
const current = computed(() => state.wizard.step)

async function next() {
  if (current.value === 0) {
    if (!state.wizard.path.trim()) return
    await saveSettings({ minecraft_directory: state.wizard.path.trim() })
  }
  if (current.value >= steps.length - 1) {
    await finishFirstRun()
    return
  }
  state.wizard.step += 1
}

function choosePath() {
  safe(async () => {
    const path = await window.neo?.pickDirectory('选择 .minecraft 根目录')
    if (path) state.wizard.path = path
  })
}
</script>

<template>
  <Teleport to="body">
    <div class="overlay wizard-overlay">
      <section class="wizard-dialog">
        <header class="wizard-head">
          <div class="wizard-brand">
            <img src="../assets/icon.jpg" alt="" />
            <div>
              <small>WELCOME TO NEOCAT</small>
              <h2>开始你的第一个世界</h2>
            </div>
          </div>
          <div class="wizard-progress">
            <span v-for="(label, index) in steps" :key="label" :class="{ active: index === current, done: index < current }">
              <i>{{ index + 1 }}</i>
              {{ label }}
            </span>
          </div>
        </header>

        <div class="wizard-body">
          <template v-if="current === 0">
            <span class="wizard-emoji">⌂</span>
            <h2>游戏文件放在哪里？</h2>
            <p>默认使用 Minecraft 标准目录。每个实例的模组、存档和配置都会独立保存。</p>
            <div class="folder-row">
              <input v-model="state.wizard.path" class="baka-input" />
              <button class="baka-button" @click="choosePath">浏览</button>
            </div>
          </template>
          <template v-else-if="current === 1">
            <span class="wizard-emoji">☕</span>
            <h2>准备 Java 运行环境</h2>
            <p>选择需要下载的 Zulu Java 主版本。启动器之后也会按游戏版本自动匹配。</p>
            <BakaSelect
              v-model="state.wizard.javaMajor"
              :options="javaOptions"
              aria-label="Java 版本"
            />
            <button class="baka-button baka-button--primary" @click="safe(() => installJava(state.wizard.javaMajor))">
              下载 Zulu Java {{ state.wizard.javaMajor }}
            </button>
          </template>
          <template v-else-if="current === 2">
            <span class="wizard-emoji wizard-emoji--microsoft">
              <MicrosoftLogo />
            </span>
            <h2>登录玩家账户</h2>
            <p>使用 mcauth3 的 Microsoft 设备代码登录，或创建用于本地的离线账户。</p>
            <button class="baka-button baka-button--primary" @click="showModal('account')">
              {{ state.accounts.length ? '管理玩家账户' : '选择登录方式' }}
            </button>
          </template>
          <template v-else-if="current === 3">
            <span class="wizard-emoji">▦</span>
            <h2>创建你的第一个实例</h2>
            <p>可以现在创建，也可以稍后从下载中心热门整合包开始。</p>
            <button class="baka-button baka-button--primary" @click="openNewInstance()">新建实例</button>
            <div v-if="state.instances.length" class="wizard-preview">
              <span>{{ state.instances[0].name }}</span>
              <small>{{ state.instances[0].mc_version }} · {{ state.instances[0].display_loader }}</small>
            </div>
          </template>
          <template v-else>
            <span class="wizard-emoji">✦</span>
            <h2>准备完毕！</h2>
            <p>之后可以在设置中修改主题、目录、Java 和下载选项。</p>
            <div class="wizard-summary">
              <span>游戏目录 <b>{{ state.settings?.minecraft_directory }}</b></span>
              <span>账户 <b>{{ state.accounts.find((item) => item.active)?.name || '尚未登录' }}</b></span>
              <span>实例 <b>{{ state.instances.length }} 个</b></span>
            </div>
          </template>
        </div>

        <footer class="wizard-foot">
          <button class="text-button" @click="safe(finishFirstRun)">跳过引导</button>
          <div>
            <button class="baka-button baka-button--plain" :disabled="current === 0" @click="state.wizard.step -= 1">上一步</button>
            <button class="baka-button baka-button--primary" @click="safe(next)">
              {{ current === steps.length - 1 ? '进入启动器' : '下一步' }}
            </button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
