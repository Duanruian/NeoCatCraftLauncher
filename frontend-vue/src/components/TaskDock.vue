<script setup>
import { computed } from 'vue'
import { useLauncher } from '../composables/useLauncher'

const { state, clearTasks } = useLauncher()
const tasks = computed(() =>
  [...state.tasks]
    .sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0))
    .slice(0, 5),
)
const activeCount = computed(() => tasks.value.filter((task) => task.state === 'running').length)
</script>

<template>
  <Transition name="task-dock">
    <aside v-if="tasks.length" class="task-dock">
      <header class="task-dock__head">
        <span>后台任务 <b v-if="activeCount">{{ activeCount }}</b></span>
        <button class="text-button" @click="clearTasks">清空</button>
      </header>
      <article v-for="task in tasks" :key="task.id" class="task-card" :class="`is-${task.state}`">
        <div class="task-card__title">
          <span>{{ task.state === 'running' ? '✦' : task.state === 'done' ? '✓' : '!' }}</span>
          <strong>{{ task.title }}</strong>
          <small>{{ task.state === 'done' ? '完成' : task.state === 'error' ? '失败' : `${Math.round(task.percent || 0)}%` }}</small>
        </div>
        <p>{{ task.error || task.message || '正在处理…' }}</p>
        <div class="task-progress"><i :style="{ width: `${task.state === 'done' ? 100 : task.percent || 0}%` }"></i></div>
      </article>
    </aside>
  </Transition>
</template>
