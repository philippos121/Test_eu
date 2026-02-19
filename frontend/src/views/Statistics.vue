<template>
  <div class="page">
    <div class="container">
      <h1 class="mb-2">{{ t('stats.title') }}</h1>

      <!-- Overview Cards -->
      <div class="stats-grid fade-in">
        <div class="stat-card card">
          <div class="stat-value">{{ stats.total_cases ?? '...' }}</div>
          <div class="stat-label">{{ t('stats.totalCases') }}</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value">{{ stats.completed_cases ?? '...' }}</div>
          <div class="stat-label">{{ t('stats.completed') }}</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value success">{{ stats.success_rate != null ? (stats.success_rate * 100).toFixed(0) + '%' : '...' }}</div>
          <div class="stat-label">{{ t('stats.successRate') }}</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value">{{ stats.avg_recovery != null ? stats.avg_recovery.toFixed(0) + ' EUR' : '...' }}</div>
          <div class="stat-label">{{ t('stats.avgRecovery') }}</div>
        </div>
      </div>

      <!-- Bayesian Posteriors -->
      <section class="card fade-in mt-3">
        <h2>{{ t('stats.bayesianLearning') }}</h2>
        <p class="text-secondary mb-2">{{ t('stats.currentPosteriors') }}</p>

        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('stats.rate') }}</th>
              <th>{{ t('stats.prior') }} (&alpha;, &beta;)</th>
              <th>{{ t('stats.observations') }}</th>
              <th>{{ t('stats.posterior') }} (&alpha;', &beta;')</th>
              <th>{{ t('stats.mean') }}</th>
              <th>{{ t('stats.ci') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rate in posteriors" :key="rate.name">
              <td><strong>{{ rate.label }}</strong></td>
              <td>(&alpha;={{ rate.prior_alpha }}, &beta;={{ rate.prior_beta }})</td>
              <td>{{ rate.successes }} / {{ rate.trials }}</td>
              <td>(&alpha;'={{ rate.post_alpha.toFixed(1) }}, &beta;'={{ rate.post_beta.toFixed(1) }})</td>
              <td>
                <div class="prob-bar-container">
                  <div class="prob-bar" :style="{ width: (rate.mean * 100) + '%' }"></div>
                  <span class="prob-bar-label">{{ (rate.mean * 100).toFixed(1) }}%</span>
                </div>
              </td>
              <td class="text-secondary">{{ (rate.ci_low * 100).toFixed(0) }}% - {{ (rate.ci_high * 100).toFixed(0) }}%</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Recent Completed Cases -->
      <section class="card fade-in mt-2">
        <h2>{{ t('stats.recentCases') }}</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('dashboard.caseCount') }}</th>
              <th>{{ t('case.amount') }}</th>
              <th>{{ t('stats.outcome') }}</th>
              <th>p<sub>cash</sub></th>
              <th>{{ t('ev.netExpectedValue') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in completedCases" :key="c.id">
              <td>{{ c.title }}</td>
              <td>{{ c.claim_amount?.toFixed(2) }} {{ c.claim_currency || 'EUR' }}</td>
              <td>
                <span :class="['badge', c.outcome_success ? 'badge-completed' : 'badge-rejected']">
                  {{ c.outcome_success ? t('stats.successful') : t('stats.unsuccessful') }}
                </span>
              </td>
              <td>{{ c.p_cash_success != null ? (c.p_cash_success * 100).toFixed(0) + '%' : '-' }}</td>
              <td :class="c.net_ev >= 0 ? 'success' : 'danger'">
                {{ c.net_ev != null ? c.net_ev.toFixed(0) + ' EUR' : '-' }}
              </td>
            </tr>
            <tr v-if="!completedCases.length">
              <td colspan="5" class="text-center text-secondary">{{ t('stats.noCompleted') }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Seed Button (Admin) -->
      <section class="card fade-in mt-2 mb-3" v-if="auth.user?.is_admin">
        <h2>Admin: Seed-Daten</h2>
        <p class="text-secondary mb-1">Generiert 5 fiktive abgeschlossene Fälle und 100 historische Beobachtungen für Bayes-Statistik und NN-Training.</p>
        <div class="flex gap-1">
          <button class="btn btn-primary" @click="seedData(false)" :disabled="seeding">
            {{ seeding ? 'Wird generiert...' : 'Seed-Daten generieren' }}
          </button>
          <button class="btn btn-outline" @click="seedData(true)" :disabled="seeding" title="Löscht bestehende [HIST]-Fälle und erstellt sie neu mit aktuellen Features">
            Historische Daten neu generieren
          </button>
          <button class="btn btn-accent" @click="updatePriors" :disabled="updatingPriors">
            {{ updatingPriors ? 'Wird aktualisiert...' : 'Priors aktualisieren' }}
          </button>
        </div>
        <p v-if="seedMsg" class="mt-1 text-secondary">{{ seedMsg }}</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useI18nStore } from '../stores/i18n'
import api from '../services/api'

const auth = useAuthStore()
const { t } = useI18nStore()

const stats = ref({})
const posteriors = ref([])
const completedCases = ref([])
const seeding = ref(false)
const updatingPriors = ref(false)
const seedMsg = ref('')

async function loadStats() {
  try {
    const { data } = await api.get('/statistics/overview')
    stats.value = data
    posteriors.value = data.posteriors || []
    completedCases.value = data.completed_cases_detail || []
  } catch {
    // Stats endpoint may not exist yet
  }
}

async function seedData(force = false) {
  seeding.value = true
  seedMsg.value = ''
  try {
    const url = force ? '/statistics/seed?force=true' : '/statistics/seed'
    const { data } = await api.post(url)
    seedMsg.value = data.message || 'Seed-Daten generiert!'
    await loadStats()
  } catch (e) {
    seedMsg.value = 'Fehler: ' + (e.response?.data?.detail || e.message)
  } finally {
    seeding.value = false
  }
}

async function updatePriors() {
  updatingPriors.value = true
  seedMsg.value = ''
  try {
    const { data } = await api.post('/statistics/update-priors')
    seedMsg.value = data.message || 'Priors aktualisiert!'
    await loadStats()
  } catch (e) {
    seedMsg.value = 'Fehler: ' + (e.response?.data?.detail || e.message)
  } finally {
    updatingPriors.value = false
  }
}

onMounted(loadStats)
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.stat-card {
  text-align: center;
  padding: 24px 16px;
}

.stat-value {
  font-size: 2rem;
  font-weight: 800;
  color: var(--primary);
}

.stat-value.success { color: var(--success); }

.stat-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-top: 4px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  font-size: 0.88rem;
}

.data-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.prob-bar-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.prob-bar {
  height: 8px;
  background: var(--primary);
  border-radius: 4px;
  min-width: 4px;
  max-width: 120px;
  transition: width 0.3s;
}

.prob-bar-label {
  font-weight: 600;
  font-size: 0.85rem;
  white-space: nowrap;
}

.success { color: var(--success); font-weight: 600; }
.danger { color: var(--danger); font-weight: 600; }
</style>
