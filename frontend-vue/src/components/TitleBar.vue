<script setup>
import logoUrl from '../assets/icon.jpg'

defineProps({
  state: { type: Object, required: true },
})

const win = window.neo?.window
</script>

<template>
  <header class="titlebar">
    <div class="titlebar__brand">
      <img :src="logoUrl" class="titlebar__logo" alt="" />
      <div>
        <strong>NeoCatCraft</strong>
        <span>LAUNCHER</span>
      </div>
    </div>
    <div class="titlebar__drag"></div>
    <div class="hello-chip">
      <span class="hello-chip__spark">✦</span>
      <span>Hello, Minecraft!</span>
    </div>
    <div class="connection-pill" :class="`is-${state.appStatusKind}`">
      <i></i>
      {{ state.appStatus }}
    </div>
    <div class="window-buttons">
      <button aria-label="最小化" title="最小化" @click="win?.minimize()">
        <svg viewBox="0 0 12 12"><path d="M2 6h8" /></svg>
      </button>
      <button aria-label="最大化" title="最大化" @click="win?.maximize()">
        <svg viewBox="0 0 12 12"><rect x="2" y="2" width="8" height="8" /></svg>
      </button>
      <button class="is-close" aria-label="关闭" title="关闭" @click="win?.close()">
        <svg viewBox="0 0 12 12"><path d="m2 2 8 8M10 2 2 10" /></svg>
      </button>
    </div>
  </header>
</template>
