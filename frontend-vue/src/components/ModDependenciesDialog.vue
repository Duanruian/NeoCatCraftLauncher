<script setup>
import { computed, ref } from 'vue'
import BaseModal from './BaseModal.vue'
import CatalogIcon from './CatalogIcon.vue'
import { useLauncher } from '../composables/useLauncher'

const { state, confirmModDependencies, cancelModDependencies } = useLauncher()
const dependencies = computed(() => state.modalData?.dependencies || [])
const selected = ref(
  new Set(
    dependencies.value
      .filter((item) => !item.installed && item.dependency_type === 'required')
      .map((item) => String(item.project_id)),
  ),
)
const selectedCount = computed(() => selected.value.size)

function toggle(projectId) {
  const key = String(projectId)
  if (selected.value.has(key)) selected.value.delete(key)
  else selected.value.add(key)
}

function installSelected() {
  confirmModDependencies([...selected.value])
}

function installOnlyMod() {
  confirmModDependencies([])
}
</script>

<template>
  <BaseModal
    title="检查模组前置"
    :subtitle="state.modalData?.hit?.title || '下载前确认'"
    wide
    @close="cancelModDependencies"
  >
    <div class="dependency-intro">
      <CatalogIcon
        :src="state.modalData?.hit?.icon"
        :name="state.modalData?.hit?.title"
        kind="mod"
        size="card"
      />
      <div>
        <strong>{{ state.modalData?.hit?.title }}</strong>
        <p>检测到以下前置模组。它们可能需要安装才能正常运行，请选择要一起安装的项目。</p>
      </div>
    </div>

    <div class="dependency-list">
      <label
        v-for="dependency in dependencies"
        :key="dependency.project_id"
        class="dependency-item"
        :class="{ installed: dependency.installed }"
      >
        <input
          type="checkbox"
          :checked="dependency.installed || selected.has(String(dependency.project_id))"
          :disabled="dependency.installed"
          @change="toggle(dependency.project_id)"
        />
        <CatalogIcon :src="dependency.icon" :name="dependency.name" kind="mod" />
        <span>
          <strong>{{ dependency.name }}</strong>
          <small>
            {{ dependency.dependency_type === 'required' ? '必需前置' : '可选前置' }}
            · {{ dependency.installed ? '已安装' : '尚未安装' }}
          </small>
        </span>
        <em v-if="dependency.installed">已安装</em>
        <em v-else :class="{ required: dependency.dependency_type === 'required' }">
          {{ dependency.dependency_type === 'required' ? '建议安装' : '可选' }}
        </em>
      </label>
      <div v-if="!dependencies.length" class="empty-inline">
        <strong>没有检测到前置</strong>
        <p>可以直接下载当前模组。</p>
      </div>
    </div>

    <template #footer>
      <button class="baka-button baka-button--plain" @click="cancelModDependencies">取消</button>
      <button class="baka-button" @click="installOnlyMod">仅下载本体</button>
      <button class="baka-button baka-button--primary" @click="installSelected">
        {{ selectedCount ? `安装 ${selectedCount} 个前置并下载` : '继续下载' }}
      </button>
    </template>
  </BaseModal>
</template>
