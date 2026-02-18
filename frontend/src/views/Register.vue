<template>
  <div class="auth-page">
    <div class="auth-container fade-in">
      <div class="auth-header">
        <img :src="logoUrl" alt="EU-Recht" class="auth-logo" />
        <h1>EU-Bagatellverfahren Portal</h1>
        <p class="text-secondary">Konto erstellen</p>
      </div>

      <form @submit.prevent="handleRegister" class="auth-form">
        <h2>Registrierung</h2>

        <div class="form-group">
          <label for="fullName">Vollständiger Name</label>
          <input
            id="fullName"
            v-model="fullName"
            type="text"
            class="form-control"
            placeholder="Max Mustermann"
            required
            autofocus
          />
        </div>

        <div class="form-group">
          <label for="email">E-Mail-Adresse</label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="form-control"
            placeholder="ihre@email.de"
            required
          />
        </div>

        <div class="form-group">
          <label for="password">Passwort</label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="form-control"
            placeholder="Mindestens 8 Zeichen"
            minlength="8"
            required
          />
        </div>

        <div class="form-group">
          <label for="passwordConfirm">Passwort bestätigen</label>
          <input
            id="passwordConfirm"
            v-model="passwordConfirm"
            type="password"
            class="form-control"
            placeholder="Passwort wiederholen"
            required
          />
        </div>

        <div class="form-group">
          <label for="language">Bevorzugte Sprache</label>
          <select id="language" v-model="language" class="form-control">
            <option value="de">Deutsch</option>
            <option value="en">English</option>
            <option value="fr">Français</option>
            <option value="it">Italiano</option>
            <option value="es">Español</option>
          </select>
        </div>

        <div v-if="error" class="error-text mb-2">{{ error }}</div>

        <button type="submit" class="btn btn-primary btn-block btn-lg" :disabled="loading">
          {{ loading ? 'Registrierung...' : 'Konto erstellen' }}
        </button>

        <p class="auth-switch mt-2 text-center">
          Bereits registriert?
          <router-link to="/login">Anmelden</router-link>
        </p>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import logoUrl from '../assets/images/logo.svg'

const auth = useAuthStore()
const router = useRouter()

const fullName = ref('')
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const language = ref('de')
const error = ref('')
const loading = ref(false)

async function handleRegister() {
  error.value = ''
  if (password.value !== passwordConfirm.value) {
    error.value = 'Die Passwörter stimmen nicht überein.'
    return
  }
  loading.value = true
  try {
    await auth.register(email.value, password.value, fullName.value, language.value)
    router.push('/')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Registrierung fehlgeschlagen.'
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
</style>
