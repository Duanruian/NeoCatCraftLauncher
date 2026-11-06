<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '请选择' },
  compact: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '下拉选择' },
})
const emit = defineEmits(['update:modelValue', 'change'])
const root = ref(null)
const trigger = ref(null)
const menu = ref(null)
const open = ref(false)
const menuStyle = reactive({
  top: '0px',
  left: '0px',
  width: '0px',
})

const normalized = computed(() =>
  props.options.map((option) =>
    typeof option === 'object' && option !== null
      ? { label: String(option.label ?? option.name ?? option.value ?? ''), value: option.value, hint: option.hint || '' }
      : { label: String(option ?? ''), value: option, hint: '' },
  ),
)
const selected = computed(
  () => normalized.value.find((option) => String(option.value) === String(props.modelValue)) || null,
)
const selectedIndex = computed(() =>
  normalized.value.findIndex((option) => String(option.value) === String(props.modelValue)),
)

function choose(option) {
  if (props.disabled) return
  emit('update:modelValue', option.value)
  emit('change', option.value)
  open.value = false
}

function move(step) {
  if (props.disabled || !normalized.value.length) return
  const start = selectedIndex.value >= 0 ? selectedIndex.value : 0
  const next = (start + step + normalized.value.length) % normalized.value.length
  choose(normalized.value[next])
}

function updatePosition() {
  if (!open.value || !trigger.value) return
  const rect = trigger.value.getBoundingClientRect()
  const menuHeight = Math.min(menu.value?.offsetHeight || normalized.value.length * 37 + 10, 280)
  const gap = 6
  const viewportPadding = 8
  const below = window.innerHeight - rect.bottom - gap - viewportPadding
  const above = rect.top - gap - viewportPadding
  const top =
    below >= menuHeight || below >= above
      ? rect.bottom + gap
      : Math.max(viewportPadding, rect.top - menuHeight - gap)
  const left = Math.max(
    viewportPadding,
    Math.min(rect.left, window.innerWidth - rect.width - viewportPadding),
  )
  menuStyle.top = `${Math.round(top)}px`
  menuStyle.left = `${Math.round(left)}px`
  menuStyle.width = `${Math.round(rect.width)}px`
}

async function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    await nextTick()
    updatePosition()
  }
}

function closeOutside(event) {
  if (!root.value?.contains(event.target) && !menu.value?.contains(event.target)) {
    open.value = false
  }
}

function reposition() {
  if (open.value) updatePosition()
}

onMounted(() => {
  document.addEventListener('pointerdown', closeOutside)
  window.addEventListener('resize', reposition)
  window.addEventListener('scroll', reposition, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOutside)
  window.removeEventListener('resize', reposition)
  window.removeEventListener('scroll', reposition, true)
})
</script>

<template>
  <div
    ref="root"
    class="baka-select"
    :class="{ 'is-open': open, 'is-disabled': disabled, 'is-compact': compact }"
    @keydown.esc.stop="open = false"
  >
    <button
      ref="trigger"
      type="button"
      class="baka-select__trigger"
      :disabled="disabled"
      :aria-label="ariaLabel"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="toggle"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
    >
      <span :class="{ 'is-placeholder': !selected }">{{ selected?.label || placeholder }}</span>
      <i aria-hidden="true"></i>
    </button>
    <Teleport to="body">
      <Transition name="baka-select-menu">
        <div
          v-if="open"
          ref="menu"
          class="baka-select__menu"
          :style="menuStyle"
          role="listbox"
        >
          <button
            v-for="option in normalized"
            :key="String(option.value)"
            type="button"
            class="baka-select__option"
            :class="{ active: String(option.value) === String(modelValue) }"
            role="option"
            :aria-selected="String(option.value) === String(modelValue)"
            @click="choose(option)"
          >
            <span>{{ option.label }}</span>
            <small v-if="option.hint">{{ option.hint }}</small>
            <i v-if="String(option.value) === String(modelValue)" aria-hidden="true">✓</i>
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
