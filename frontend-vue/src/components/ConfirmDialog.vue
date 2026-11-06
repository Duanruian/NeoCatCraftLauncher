<script setup>
import BaseModal from './BaseModal.vue'
import { useLauncher } from '../composables/useLauncher'

const { state, closeModal } = useLauncher()
</script>

<template>
  <BaseModal :title="state.modalData?.title" @close="closeModal(false)">
    <p class="confirm-message">{{ state.modalData?.message }}</p>
    <template #footer>
      <button class="baka-button baka-button--plain" @click="closeModal(false)">取消</button>
      <button
        class="baka-button"
        :class="state.modalData?.danger ? 'baka-button--danger' : 'baka-button--primary'"
        @click="closeModal(true)"
      >
        {{ state.modalData?.confirmLabel || '确认' }}
      </button>
    </template>
  </BaseModal>
</template>
