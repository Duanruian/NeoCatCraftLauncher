<script setup>
import { useLauncher } from '../composables/useLauncher'

const { state } = useLauncher()
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="toast in state.toasts" :key="toast.id" class="toast" :class="`toast--${toast.kind}`">
        <span>{{ toast.kind === 'error' ? '!' : toast.kind === 'ok' ? '✓' : '✦' }}</span>
        {{ toast.message }}
      </div>
    </TransitionGroup>
  </div>
</template>
