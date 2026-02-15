<template>
  <div class="auth-page">
    <div class="auth-container fade-in">
      <div class="auth-header">
        <img :src="logoUrl" alt="AI:ssociate" class="auth-logo" />
        <h1>EU-Bagatellverfahren Portal</h1>
        <p class="text-secondary">
          Europäisches Verfahren für geringfügige Forderungen
        </p>
      </div>

      <form @submit.prevent="handleLogin" class="auth-form">
        <h2>Anmelden</h2>

        <div class="form-group">
          <label for="email">E-Mail-Adresse</label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="form-control"
            placeholder="ihre@email.de"
            required
            autofocus
          />
        </div>

        <div class="form-group">
          <label for="password">Passwort</label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="form-control"
            placeholder="Ihr Passwort"
            required
          />
        </div>

        <div v-if="error" class="error-text mb-2">{{ error }}</div>

        <button type="submit" class="btn btn-primary btn-block btn-lg" :disabled="loading">
          {{ loading ? 'Anmeldung...' : 'Anmelden' }}
        </button>

        <p class="auth-switch mt-2 text-center">
          Noch kein Konto?
          <router-link to="/register">Jetzt registrieren</router-link>
        </p>
      </form>

      <div class="auth-info">
        <p>
          Dieses Portal unterstützt Sie bei der Durchsetzung Ihrer Forderungen
          innerhalb der EU im Rahmen des Europäischen Bagatellverfahrens
          (Verordnung (EG) Nr. 861/2007) für Streitwerte bis 5.000 EUR.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import logoUrl from '../assets/images/logo.jpg'

const auth = useAuthStore()
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
    error.value = err.response?.data?.detail || 'Anmeldung fehlgeschlagen.'
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
  filter: brightness(0) invert(1);
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
