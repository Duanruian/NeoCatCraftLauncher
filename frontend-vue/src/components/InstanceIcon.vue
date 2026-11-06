<script setup>
import { computed } from 'vue'

const props = defineProps({
  loader: { type: String, default: 'vanilla' },
  icon: { type: String, default: '' },
  size: { type: String, default: 'normal' },
})

const iconType = computed(() => {
  const loader = String(props.loader || 'vanilla').toLowerCase().replace(/[\s_-]+/g, '')
  const icon = String(props.icon || '').toLowerCase().replace(/[\s_-]+/g, '')
  const supported = ['grass', 'vanilla', 'fabric', 'forge', 'neoforge', 'quilt']

  if (loader && !['vanilla', 'original'].includes(loader) && supported.includes(loader)) return loader
  if (supported.includes(icon)) return icon === 'vanilla' ? 'grass' : icon
  if (!loader || ['vanilla', 'original'].includes(loader)) return 'grass'
  return supported.includes(loader) ? loader : 'grass'
})

const label = computed(
  () =>
    ({
      grass: 'Minecraft 原版',
      fabric: 'Fabric',
      forge: 'Forge',
      neoforge: 'NeoForge',
      quilt: 'Quilt',
    })[iconType.value],
)
</script>

<template>
  <span
    class="instance-icon"
    :class="[`instance-icon--${iconType}`, `instance-icon--${size}`]"
    :title="label"
    role="img"
    :aria-label="label"
  >
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <g v-if="iconType === 'grass'">
        <path d="M16 3 29 9 16 15 3 9Z" fill="#72d764" />
        <path d="M3 9 16 15v15L3 24Z" fill="#9a633d" />
        <path d="M16 15 29 9v15L16 30Z" fill="#75462c" />
        <path d="m5 11 10 4.7V16L5 11.4Zm12 4.7V28l10-4.7V11Z" fill="#b97948" opacity=".72" />
        <path d="m4 10 12 5 11-5v4L16 19 4 14Z" fill="#55b94d" />
        <path d="M5 10h4v3H5Zm7 3h3v3h-3Zm5-2h3v3h-3Zm4 1h3v3h-3Z" fill="#91e875" />
        <path d="M7 26h3v2H7Zm5-4h2v3h-2Zm8 0h3v3h-3Z" fill="#5d3926" opacity=".55" />
      </g>

      <g v-else-if="iconType === 'fabric'">
        <rect x="3" y="3" width="26" height="26" rx="8" fill="#e9e4f8" />
        <path d="M9 7c-3 5-3 11 2 18 4-4 5-9 3-15Z" fill="#70569c" />
        <path d="M19 7c4 5 6 10 4 18-5-3-7-8-6-14Z" fill="#a994df" />
        <path d="M12 9c1 5 3 8 7 11-1-5-3-8-7-11Zm7 14c-3-1-6-4-8-8-1 4 1 7 4 9.5 1-2 2-2.5 4-1.5Z" fill="#fff" opacity=".85" />
        <circle cx="23.5" cy="8.5" r="1.6" fill="#55c98b" />
      </g>

      <g v-else-if="iconType === 'forge'">
        <rect x="3" y="3" width="26" height="26" rx="8" fill="#fff0d7" />
        <path d="M9 8h14v4h-3v10h5v4H7v-4h5V12H9Z" fill="#e58e25" />
        <path d="M11 11h10v3h-2v9h-3v-9h-3v6H11Z" fill="#ffc05c" />
        <path d="m23 4 1.5 3.5L28 9l-3.5 1.5L23 14l-1.5-3.5L18 9l3.5-1.5Z" fill="#ffb23e" />
        <path d="M6 21h4v2H6Z" fill="#c56f17" opacity=".7" />
      </g>

      <g v-else-if="iconType === 'neoforge'">
        <rect x="3" y="3" width="26" height="26" rx="8" fill="#dff6ff" />
        <path d="M9 7h14v4h-3v10h5v5H7v-5h5V11H9Z" fill="#188fb0" />
        <path d="M11 10h10v4h-2v7h-3v-7h-3v5H11Z" fill="#76d8ef" />
        <path d="m23 4 1.5 3.5L28 9l-3.5 1.5L23 14l-1.5-3.5L18 9l3.5-1.5Z" fill="#ff9d38" />
        <circle cx="9" cy="24" r="2" fill="#ff9d38" />
      </g>

      <g v-else>
        <rect x="3" y="3" width="26" height="26" rx="8" fill="#e7f5e5" />
        <path d="M5 6 15 3 16 14 5 16Z" fill="#6fc584" />
        <path d="m17 3 10 4-1 11-10-4Z" fill="#a3d57a" />
        <path d="m5 18 11-2 1 12L5 27Z" fill="#ecd477" />
        <path d="m18 16 10 2-1 9-8 3Z" fill="#79bcdc" />
        <path d="m15 4 .5 10m2-10 9 4m-20 2 10-1m-1 3 .7 10m2-10 8 2m-19 2 9-1m0 3 .5 7" fill="none" stroke="#fff" stroke-width="1.3" stroke-dasharray="2 2" stroke-linecap="round" />
      </g>
    </svg>
  </span>
</template>
