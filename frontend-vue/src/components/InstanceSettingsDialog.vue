<script setup>
import { computed, reactive } from 'vue'
import BaseModal from './BaseModal.vue'
import BakaSelect from './BakaSelect.vue'
import { useLauncher } from '../composables/useLauncher'

const launcher = useLauncher()
const {
  state,
  safe,
  closeModal,
  saveInstanceSettings,
  deleteInstance,
  duplicateInstance,
  openFolder,
} = launcher
const instance = state.instance
const form = reactive({
  name: instance?.name || '',
  memory_mb: instance?.memory_mb || state.settings?.memory_mb || 4096,
  min_memory_mb: instance?.min_memory_mb || state.settings?.min_memory_mb || 512,
  java_path: instance?.java_path || '',
  jvm_args: instance?.jvm_args ?? '',
})
const javaOptions = computed(() => [
  { value: '', label: '自动匹配 Minecraft 版本' },
  ...state.java.all.map((runtime) => ({ value: runtime.path, label: runtime.label })),
])

function submit() {
  safe(() =>
    saveInstanceSettings({
      name: form.name.trim() || instance.name,
      memory_mb: Number(form.memory_mb),
      min_memory_mb: Number(form.min_memory_mb),
      java_path: form.java_path,
      jvm_args: form.jvm_args,
    }),
  )
}
</script>

<template>
  <BaseModal title="实例设置" :subtitle="instance?.name" wide @close="closeModal()">
    <div class="dialog-form">
      <label class="form-field">
        <span>实例名称</span>
        <input v-model="form.name" class="baka-input" />
      </label>
      <div class="form-grid">
        <label class="form-field">
          <span>最大内存（MB）</span>
          <input v-model.number="form.memory_mb" class="baka-input" type="number" />
        </label>
        <label class="form-field">
          <span>最小内存（MB）</span>
          <input v-model.number="form.min_memory_mb" class="baka-input" type="number" />
        </label>
      </div>
      <label class="form-field">
        <span>Java 运行时</span>
        <BakaSelect v-model="form.java_path" :options="javaOptions" aria-label="Java 运行时" />
      </label>
      <label class="form-field">
        <span>JVM 参数</span>
        <textarea v-model="form.jvm_args" class="baka-input code-input"></textarea>
      </label>
      <div class="folder-preview">
        <span>独立实例目录</span>
        <code>{{ instance?.directory }}</code>
      </div>
      <div class="danger-zone">
        <button class="text-button" @click="safe(() => openFolder())">打开游戏目录</button>
        <button class="text-button" @click="safe(duplicateInstance)">复制实例</button>
        <button class="text-button danger" @click="safe(deleteInstance)">删除实例</button>
      </div>
    </div>
    <template #footer>
      <button class="baka-button baka-button--plain" @click="closeModal()">取消</button>
      <button class="baka-button baka-button--primary" @click="submit">保存设置</button>
    </template>
  </BaseModal>
</template>
