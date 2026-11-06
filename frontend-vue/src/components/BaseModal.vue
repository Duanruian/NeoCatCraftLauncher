<script setup>
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  wide: { type: Boolean, default: false },
  closable: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])
</script>

<template>
  <Teleport to="body">
    <div class="overlay" @mousedown.self="closable && emit('close')">
      <section class="dialog" :class="{ 'dialog--wide': wide }" role="dialog" aria-modal="true">
        <button v-if="closable" class="dialog-close" aria-label="关闭" @click="emit('close')">×</button>
        <header v-if="title" class="dialog-head">
          <span class="dialog-kicker">NEOCAT</span>
          <h2>{{ title }}</h2>
          <p v-if="subtitle">{{ subtitle }}</p>
        </header>
        <div class="dialog-body">
          <slot></slot>
        </div>
        <footer v-if="$slots.footer" class="dialog-actions">
          <slot name="footer"></slot>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
