<script setup>
import { useLauncher } from '../composables/useLauncher'

const launcher = useLauncher()
const { state, safe, loadJava, installJava, api, navigate, toast } = launcher

async function openJavaFolder() {
  try {
    await api('/api/java/open-folder', { method: 'POST' })
  } catch (error) {
    toast(error.message, 'error')
  }
}
</script>

<template>
  <div class="page-view java-view">
    <header class="page-hero page-hero--java">
      <div>
        <span class="eyebrow">JAVA RUNTIME</span>
        <h1>给每个世界合适的 Java</h1>
        <p>自动匹配 Minecraft 版本，同时支持系统 Java 与 Minecraft 内置运行时。</p>
      </div>
      <div class="hero-actions">
        <button class="baka-button baka-button--plain" @click="navigate('settings')">返回设置</button>
        <button class="baka-button" @click="safe(openJavaFolder)">打开 Java 目录</button>
      </div>
      <span class="hero-doodle">☕</span>
    </header>

    <div class="java-grid">
      <section class="baka-card java-installed">
        <header class="section-head">
          <div>
            <small>MANAGED ZULU</small>
            <h2>受管运行时</h2>
            <p>{{ state.java.directory }}</p>
          </div>
          <button class="icon-button" title="重新检测" @click="safe(() => loadJava(true))">↻</button>
        </header>
        <div v-if="state.java.managed.length" class="runtime-list">
          <article v-for="java in state.java.managed" :key="java.path" class="runtime-card is-managed">
            <span class="runtime-logo">J</span>
            <div>
              <strong>{{ java.label || `Java ${java.major}` }}</strong>
              <small>{{ java.version }} · {{ java.path }}</small>
            </div>
            <span class="soft-tag">Zulu</span>
          </article>
        </div>
        <div v-else class="empty-inline">
          <strong>还没有受管 Zulu</strong>
          <p>在右侧选择 Java 主版本即可自动下载。</p>
        </div>
      </section>

      <section class="baka-card java-downloads">
        <header class="section-head">
          <div>
            <small>ZULU DOWNLOADS</small>
            <h2>下载 Java</h2>
            <p>Windows x64 · SHA-256 校验</p>
          </div>
        </header>
        <div class="java-download-grid">
          <article v-for="entry in state.java.available" :key="entry.major" class="java-version-card">
            <span class="java-cube">{{ entry.major }}</span>
            <strong>{{ entry.label }}</strong>
            <small>{{ entry.major === 21 ? '推荐用于 1.20.5+' : entry.major === 17 ? '适用于 1.17 - 1.20.4' : '兼容旧版游戏' }}</small>
            <button class="baka-button baka-button--primary baka-button--mini" @click="safe(() => installJava(entry.major))">
              下载
            </button>
          </article>
        </div>
      </section>

      <section class="baka-card java-system">
        <header class="section-head">
          <div>
            <small>DETECTED RUNTIMES</small>
            <h2>系统与内置 Java</h2>
          </div>
        </header>
        <div v-if="state.java.system.length" class="runtime-list compact">
          <article v-for="java in state.java.system" :key="java.path" class="runtime-card">
            <span class="runtime-logo">J</span>
            <div>
              <strong>{{ java.label }}</strong>
              <small>{{ java.path }}</small>
            </div>
            <span class="soft-tag">{{ java.source === 'minecraft-runtime' ? '内置' : '系统' }}</span>
          </article>
        </div>
        <div v-else class="empty-inline"><strong>没有检测到其他 Java</strong><p>仍可使用受管 Zulu 运行时。</p></div>
      </section>
    </div>
  </div>
</template>
