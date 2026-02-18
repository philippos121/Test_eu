<template>
  <div class="lang-selector" ref="selectorRef">
    <button class="lang-btn" @click="open = !open" :title="i18n.currentLanguage.name">
      <span class="lang-flag">{{ i18n.currentLanguage.flag }}</span>
      <span class="lang-code">{{ i18n.currentLanguage.code.toUpperCase() }}</span>
      <span class="lang-arrow">&#9662;</span>
    </button>
    <div v-if="open" class="lang-dropdown">
      <button
        v-for="lang in i18n.languages"
        :key="lang.code"
        class="lang-option"
        :class="{ active: lang.code === i18n.locale }"
        @click="selectLanguage(lang.code)"
      >
        <span class="lang-flag">{{ lang.flag }}</span>
        <span class="lang-name">{{ lang.name }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()
const open = ref(false)
const selectorRef = ref(null)

function selectLanguage(code) {
  i18n.setLocale(code)
  open.value = false
}

function handleClickOutside(e) {
  if (selectorRef.value && !selectorRef.value.contains(e.target)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onUnmounted(() => document.removeEventListener('click', handleClickOutside))
</script>

<style scoped>
.lang-selector {
  position: relative;
}

.lang-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  padding: 4px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.82rem;
  transition: all 0.2s;
}

.lang-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.lang-flag {
  font-size: 1.1rem;
  line-height: 1;
}

.lang-code {
  font-weight: 600;
}

.lang-arrow {
  font-size: 0.7rem;
  opacity: 0.7;
}

.lang-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: white;
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 200px;
  max-height: 360px;
  overflow-y: auto;
  z-index: 300;
}

.lang-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text);
  transition: background 0.15s;
  text-align: left;
}

.lang-option:hover {
  background: var(--bg);
}

.lang-option.active {
  background: var(--primary);
  color: white;
  font-weight: 600;
}

.lang-name {
  flex: 1;
}
</style>
