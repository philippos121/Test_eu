import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { languages, translations } from '../i18n/index.js'

export const useI18nStore = defineStore('i18n', () => {
  const locale = ref(localStorage.getItem('locale') || 'de')

  const currentLanguage = computed(() =>
    languages.find(l => l.code === locale.value) || languages[0]
  )

  function setLocale(code) {
    locale.value = code
    localStorage.setItem('locale', code)
  }

  function t(key) {
    const lang = translations[locale.value] || translations.de
    const keys = key.split('.')
    let val = lang
    for (const k of keys) {
      if (val && typeof val === 'object' && k in val) {
        val = val[k]
      } else {
        // Fallback to German
        let fallback = translations.de
        for (const fk of keys) {
          if (fallback && typeof fallback === 'object' && fk in fallback) {
            fallback = fallback[fk]
          } else {
            return key // key not found at all
          }
        }
        return fallback
      }
    }
    return val
  }

  return { locale, currentLanguage, languages, setLocale, t }
})
