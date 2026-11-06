<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import { useLauncher } from '../composables/useLauncher'

const UNIT = 7
const { state, activeAccount, closeModal, refreshSkinPreview, toast } = useLauncher()

const account = computed(() => state.modalData || activeAccount.value)
const skinUrl = computed(() => account.value?.skin || '')
const slim = computed(() => account.value?.skin_model === 'slim')
const imageState = ref('loading')
const rotationX = ref(-7)
const rotationY = ref(24)
const dragging = ref(false)
const refreshing = ref(false)
let pointerStart = null

const atlas = {
  head: {
    front: [8, 8, 8, 8],
    back: [24, 8, 8, 8],
    right: [16, 8, 8, 8],
    left: [0, 8, 8, 8],
    top: [8, 0, 8, 8],
    bottom: [16, 0, 8, 8],
  },
  body: {
    front: [20, 20, 8, 12],
    back: [32, 20, 8, 12],
    right: [16, 20, 4, 12],
    left: [28, 20, 4, 12],
    top: [20, 16, 8, 4],
    bottom: [28, 16, 8, 4],
  },
  rightLeg: {
    front: [4, 20, 4, 12],
    back: [12, 20, 4, 12],
    right: [0, 20, 4, 12],
    left: [8, 20, 4, 12],
    top: [4, 16, 4, 4],
    bottom: [8, 16, 4, 4],
  },
  leftLeg: {
    front: [20, 52, 4, 12],
    back: [28, 52, 4, 12],
    right: [16, 52, 4, 12],
    left: [24, 52, 4, 12],
    top: [20, 48, 4, 4],
    bottom: [24, 48, 4, 4],
  },
  rightArm: {
    front: [44, 20, 4, 12],
    back: [52, 20, 4, 12],
    right: [40, 20, 4, 12],
    left: [48, 20, 4, 12],
    top: [44, 16, 4, 4],
    bottom: [48, 16, 4, 4],
  },
  leftArm: {
    front: [36, 52, 4, 12],
    back: [44, 52, 4, 12],
    right: [32, 52, 4, 12],
    left: [40, 52, 4, 12],
    top: [36, 48, 4, 4],
    bottom: [40, 48, 4, 4],
  },
  headOverlay: {
    front: [40, 8, 8, 8],
    back: [56, 8, 8, 8],
    right: [48, 8, 8, 8],
    left: [32, 8, 8, 8],
    top: [40, 0, 8, 8],
    bottom: [48, 0, 8, 8],
  },
  bodyOverlay: {
    front: [20, 36, 8, 12],
    back: [32, 36, 8, 12],
    right: [16, 36, 4, 12],
    left: [28, 36, 4, 12],
    top: [20, 32, 8, 4],
    bottom: [28, 32, 8, 4],
  },
  rightLegOverlay: {
    front: [4, 36, 4, 12],
    back: [12, 36, 4, 12],
    right: [0, 36, 4, 12],
    left: [8, 36, 4, 12],
    top: [4, 32, 4, 4],
    bottom: [8, 32, 4, 4],
  },
  leftLegOverlay: {
    front: [4, 52, 4, 12],
    back: [12, 52, 4, 12],
    right: [0, 52, 4, 12],
    left: [8, 52, 4, 12],
    top: [4, 48, 4, 4],
    bottom: [8, 48, 4, 4],
  },
  rightArmOverlay: {
    front: [44, 36, 4, 12],
    back: [52, 36, 4, 12],
    right: [40, 36, 4, 12],
    left: [48, 36, 4, 12],
    top: [44, 32, 4, 4],
    bottom: [48, 32, 4, 4],
  },
  leftArmOverlay: {
    front: [52, 52, 4, 12],
    back: [60, 52, 4, 12],
    right: [48, 52, 4, 12],
    left: [56, 52, 4, 12],
    top: [52, 48, 4, 4],
    bottom: [56, 48, 4, 4],
  },
}

const slimAtlas = {
  ...atlas,
  rightArm: {
    front: [44, 20, 3, 12],
    back: [51, 20, 3, 12],
    right: [40, 20, 4, 12],
    left: [47, 20, 4, 12],
    top: [44, 16, 3, 4],
    bottom: [47, 16, 3, 4],
  },
  leftArm: {
    front: [36, 52, 3, 12],
    back: [43, 52, 3, 12],
    right: [32, 52, 4, 12],
    left: [39, 52, 4, 12],
    top: [36, 48, 3, 4],
    bottom: [39, 48, 3, 4],
  },
  rightArmOverlay: {
    front: [44, 36, 3, 12],
    back: [51, 36, 3, 12],
    right: [40, 36, 4, 12],
    left: [47, 36, 4, 12],
    top: [44, 32, 3, 4],
    bottom: [47, 32, 3, 4],
  },
  leftArmOverlay: {
    front: [52, 52, 3, 12],
    back: [59, 52, 3, 12],
    right: [48, 52, 4, 12],
    left: [55, 52, 4, 12],
    top: [52, 48, 3, 4],
    bottom: [55, 48, 3, 4],
  },
}

const parts = computed(() => {
  const armWidth = slim.value ? 3 : 4
  return [
    { id: 'head', x: 4, y: 0, width: 8, height: 8, depth: 8 },
    { id: 'head', texture: 'headOverlay', x: 3.75, y: -0.25, width: 8.5, height: 8.5, depth: 8.5, overlay: true },
    { id: 'body', x: 4, y: 8, width: 8, height: 12, depth: 4 },
    { id: 'body', texture: 'bodyOverlay', x: 3.75, y: 7.75, width: 8.5, height: 12.5, depth: 4.5, overlay: true },
    { id: 'rightArm', x: 4 - armWidth, y: 8, width: armWidth, height: 12, depth: 4 },
    { id: 'rightArm', texture: 'rightArmOverlay', x: 3.75 - armWidth, y: 7.75, width: armWidth + 0.5, height: 12.5, depth: 4.5, overlay: true },
    { id: 'leftArm', x: 12, y: 8, width: armWidth, height: 12, depth: 4 },
    { id: 'leftArm', texture: 'leftArmOverlay', x: 11.75, y: 7.75, width: armWidth + 0.5, height: 12.5, depth: 4.5, overlay: true },
    { id: 'rightLeg', x: 4, y: 20, width: 4, height: 12, depth: 4 },
    { id: 'rightLeg', texture: 'rightLegOverlay', x: 3.75, y: 19.75, width: 4.5, height: 12.5, depth: 4.5, overlay: true },
    { id: 'leftLeg', x: 8, y: 20, width: 4, height: 12, depth: 4 },
    { id: 'leftLeg', texture: 'leftLegOverlay', x: 7.75, y: 19.75, width: 4.5, height: 12.5, depth: 4.5, overlay: true },
  ]
})

const visibleFaces = ['front', 'back', 'right', 'left', 'top', 'bottom']
const modelTransform = computed(
  () => `rotateX(${rotationX.value}deg) rotateY(${rotationY.value}deg)`,
)
const modelReady = computed(() => Boolean(skinUrl.value) && imageState.value === 'loaded')
const modelLabel = computed(() => (slim.value ? 'Slim · 3 像素手臂' : 'Classic · 4 像素手臂'))
const profileFaceStyle = computed(() =>
  skinUrl.value
    ? {
        backgroundImage: `url("${skinUrl.value}")`,
        backgroundPosition: '-56px -56px',
        backgroundSize: '448px 448px',
      }
    : null,
)

watch(skinUrl, () => {
  if (!skinUrl.value) {
    imageState.value = 'error'
    return
  }
  imageState.value = 'loading'
  rotationX.value = -7
  rotationY.value = 24
})

function partStyle(part) {
  return {
    left: `${part.x * UNIT}px`,
    top: `${part.y * UNIT}px`,
    width: `${part.width * UNIT}px`,
    height: `${part.height * UNIT}px`,
    '--part-depth': `${part.depth * UNIT}px`,
  }
}

function faceStyle(part, face) {
  const source = (slim.value ? slimAtlas : atlas)[part.texture || part.id]?.[face]
  if (!source) return {}
  const [x, y, width, height] = source
  const partWidth = part.width * UNIT
  const partHeight = part.height * UNIT
  const depth = part.depth * UNIT
  const transforms = {
    front: `translateZ(${depth / 2}px)`,
    back: `rotateY(180deg) translateZ(${depth / 2}px)`,
    right: `rotateY(90deg) translateZ(${partWidth / 2}px)`,
    left: `rotateY(-90deg) translateZ(${partWidth / 2}px)`,
    top: `rotateX(90deg) translateZ(${partHeight / 2}px)`,
    bottom: `rotateX(-90deg) translateZ(${partHeight / 2}px)`,
  }
  const placement = {
    front: { left: 0, top: 0 },
    back: { left: 0, top: 0 },
    right: { left: (partWidth - depth) / 2, top: 0 },
    left: { left: (partWidth - depth) / 2, top: 0 },
    top: { left: 0, top: (partHeight - depth) / 2 },
    bottom: { left: 0, top: (partHeight - depth) / 2 },
  }[face]
  return {
    left: `${placement.left}px`,
    top: `${placement.top}px`,
    width: `${width * UNIT}px`,
    height: `${height * UNIT}px`,
    backgroundImage: `url("${skinUrl.value}")`,
    backgroundPosition: `-${x * UNIT}px -${y * UNIT}px`,
    backgroundSize: `${64 * UNIT}px ${64 * UNIT}px`,
    transform: transforms[face],
  }
}

function startDrag(event) {
  if (!modelReady.value) return
  dragging.value = true
  pointerStart = {
    x: event.clientX,
    y: event.clientY,
    rotationX: rotationX.value,
    rotationY: rotationY.value,
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function dragModel(event) {
  if (!dragging.value || !pointerStart) return
  rotationY.value = pointerStart.rotationY + (event.clientX - pointerStart.x) * 0.52
  rotationX.value = Math.max(-24, Math.min(18, pointerStart.rotationX - (event.clientY - pointerStart.y) * 0.24))
}

function stopDrag(event) {
  dragging.value = false
  pointerStart = null
  if (event?.currentTarget?.hasPointerCapture?.(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
}

function setAngle(angle) {
  rotationX.value = -7
  rotationY.value = angle
}

async function refresh() {
  if (refreshing.value || !account.value) return
  refreshing.value = true
  try {
    await refreshSkinPreview(account.value, false)
    toast('已从 Mojang 刷新皮肤资料', 'ok')
  } catch (error) {
    toast(error.message, 'error', 6000)
  } finally {
    refreshing.value = false
  }
}

onBeforeUnmount(stopDrag)
</script>

<template>
  <BaseModal
    title="皮肤预览"
    :subtitle="account?.name ? `${account.name} · Microsoft 正版` : 'Microsoft 正版皮肤'"
    wide
    @close="closeModal()"
  >
    <div class="skin-preview-layout">
      <section class="skin-preview-stage">
        <span class="skin-preview-glow" aria-hidden="true"></span>
        <img
          v-if="skinUrl"
          :src="skinUrl"
          class="skin-preview-probe"
          alt=""
          @load="imageState = 'loaded'"
          @error="imageState = 'error'"
        />
        <div
          v-if="modelReady"
          class="skin-stage-drag"
          :class="{ dragging }"
          role="img"
          :aria-label="`${account?.name || '玩家'}的 Minecraft 皮肤，可拖动旋转`"
          @pointerdown="startDrag"
          @pointermove="dragModel"
          @pointerup="stopDrag"
          @pointercancel="stopDrag"
        >
          <div class="skin-model" :style="{ transform: modelTransform }">
            <div
              v-for="part in parts"
              :key="`${part.id}-${part.texture || 'base'}`"
              class="skin-part"
              :class="`skin-part--${part.id}`"
              :style="partStyle(part)"
            >
              <span
                v-for="face in visibleFaces"
                :key="face"
                class="skin-face"
                :class="[`skin-face--${face}`, { 'skin-face--overlay': part.overlay }]"
                :style="faceStyle(part, face)"
              ></span>
            </div>
          </div>
          <span class="skin-model-shadow" aria-hidden="true"></span>
        </div>
        <div v-else class="skin-preview-placeholder">
          <span class="skin-preview-spinner" v-if="imageState === 'loading'"></span>
          <strong>{{ imageState === 'loading' ? '正在载入皮肤' : '皮肤贴图暂不可用' }}</strong>
          <small>{{ imageState === 'loading' ? '正在读取 Mojang 纹理…' : '请检查网络后重试' }}</small>
        </div>
        <span class="skin-preview-hint">按住拖动 · 旋转查看</span>
      </section>

      <aside class="skin-preview-side">
        <div class="skin-profile-card">
          <span
            class="skin-profile-face"
            :style="profileFaceStyle"
          ></span>
          <div>
            <small>MICROSOFT ACCOUNT</small>
            <strong>{{ account?.name || '玩家' }}</strong>
            <span>{{ modelLabel }}</span>
          </div>
        </div>

        <div class="skin-preview-tags">
          <span><i></i> 正版账户</span>
          <span>{{ slim ? 'Slim' : 'Classic' }}</span>
          <span v-if="account?.cape">披风已配置</span>
        </div>

        <div class="skin-angle-controls" aria-label="皮肤视角">
          <button @click="setAngle(0)">正面</button>
          <button @click="setAngle(-42)">侧面</button>
          <button @click="setAngle(172)">背面</button>
        </div>

        <p class="skin-preview-note">
          皮肤纹理直接来自 Mojang 账户资料。若在游戏中更换了皮肤，点击刷新即可获取最新样式。
        </p>

        <button class="baka-button skin-refresh-button" :disabled="refreshing" @click="refresh">
          {{ refreshing ? '正在刷新…' : '从 Mojang 刷新皮肤' }}
        </button>
      </aside>
    </div>
  </BaseModal>
</template>
