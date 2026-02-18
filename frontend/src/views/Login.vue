<template>
  <div class="auth-page">
    <div class="auth-container fade-in">
      <div class="auth-header">
        <img :src="logoUrl" alt="EU-Recht" class="auth-logo" />
        <h1>{{ t('auth.portalTitle') }}</h1>
        <p class="text-secondary">{{ t('auth.portalSubtitle') }}</p>
      </div>

      <form @submit.prevent="handleLogin" class="auth-form">
        <h2>{{ t('auth.login') }}</h2>

        <div class="form-group">
          <label for="email">{{ t('auth.email') }}</label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="form-control"
            :placeholder="t('auth.emailPlaceholder')"
            required
            autofocus
          />
        </div>

        <div class="form-group">
          <label for="password">{{ t('auth.password') }}</label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="form-control"
            :placeholder="t('auth.passwordPlaceholder')"
            required
          />
        </div>

        <div v-if="error" class="error-text mb-2">{{ error }}</div>

        <button type="submit" class="btn btn-primary btn-block btn-lg" :disabled="loading">
          {{ loading ? t('auth.loginLoading') : t('auth.loginButton') }}
        </button>

        <p class="auth-switch mt-2 text-center">
          {{ t('auth.noAccount') }}
          <router-link to="/register">{{ t('auth.register') }}</router-link>
        </p>
      </form>

      <div class="auth-info">
        <p>{{ t('auth.info') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useI18nStore } from '../stores/i18n'
import logoUrl from '../assets/images/logo.svg'

const auth = useAuthStore()
const { t } = useI18nStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch (err) {
    error.value = err.response?.data?.detail || t('auth.loginFailed')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 50%, var(--primary-light) 100%);
  padding: 20px;
}

.auth-container {
  width: 100%;
  max-width: 440px;
}

.auth-header {
  text-align: center;
  color: white;
  margin-bottom: 32px;
}

.auth-logo {
  height: 48px;
  width: auto;
  object-fit: contain;
  margin-bottom: 12px;
}

.auth-header h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 6px;
}

.auth-header .text-secondary {
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.9rem;
}

.auth-form {
  background: white;
  padding: 32px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.auth-form h2 {
  font-size: 1.2rem;
  margin-bottom: 20px;
  color: var(--primary);
}

.auth-switch {
  font-size: 0.88rem;
  color: var(--text-secondary);
}

.auth-info {
  margin-top: 24px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: var(--radius);
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.82rem;
  line-height: 1.5;
  text-align: center;
}
</style>
