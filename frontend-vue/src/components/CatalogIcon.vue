<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  src: { type: String, default: '' },
  name: { type: String, default: '' },
  kind: { type: String, default: 'mod' },
  size: { type: String, default: 'normal' },
})
const failed = ref(false)
const glyph = computed(
  () =>
    ({
      mod: (props.name || '?').slice(0, 1).toUpperCase(),
      modpack: '▦',
      resourcepack: '▧',
      shader: '✧',
      datapack: '◇',
    })[props.kind] || (props.name || '?').slice(0, 1).toUpperCase(),
)

watch(
  () => props.src,
  () => {
    failed.value = false
  },
)
</script>

<template>
  <span class="catalog-icon" :class="[`catalog-icon--${kind}`, `catalog-icon--${size}`]">
    <span class="catalog-icon__fallback">{{ glyph }}</span>
    <img
      v-if="src && !failed"
      :src="src"
      :alt="name || '模组图标'"
      loading="lazy"
      referrerpolicy="no-referrer"
      @error="failed = true"
    />
  </span>
</template>
