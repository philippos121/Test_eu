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

      <!-- Learning Insights -->
      <section class="card fade-in mt-3" v-if="learningInsights.length">
        <h2>{{ t('stats.learningTitle') }}</h2>
        <p class="text-secondary mb-2">{{ t('stats.learningDesc') }}</p>
        <div class="insights-list">
          <div v-for="insight in learningInsights" :key="insight.rate_name" class="insight-card">
            <div class="insight-header">
              <strong>{{ insight.label }}</strong>
              <div class="insight-delta" :class="insight.posterior_mean >= insight.prior_mean ? 'delta-up' : 'delta-down'">
                {{ (insight.prior_mean * 100).toFixed(0) }}%
                &rarr;
                {{ (insight.posterior_mean * 100).toFixed(0) }}%
              </div>
            </div>
            <div class="insight-bar-row">
              <div class="insight-bar-bg">
                <div class="insight-bar-prior" :style="{ width: (insight.prior_mean * 100) + '%' }"></div>
                <div class="insight-bar-post" :style="{ width: (insight.posterior_mean * 100) + '%' }"></div>
              </div>
            </div>
            <div class="insight-stats text-secondary">
              {{ insight.successes + insight.failures }} Beobachtungen
              ({{ insight.successes }} Erfolge, {{ insight.failures }} Misserfolge)
            </div>
            <p class="insight-text">{{ insight.interpretation }}</p>
          </div>
        </div>
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
        <p class="text-secondary mb-1">Generiert 5 fiktive abgeschlossene Beispielfälle und 100 historische Beobachtungen für die Statistik.</p>
        <div class="flex gap-1">
          <button class="btn btn-primary" @click="seedData" :disabled="seeding">
            {{ seeding ? 'Wird generiert...' : 'Seed-Daten generieren' }}
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
const learningInsights = ref([])
const seeding = ref(false)
const updatingPriors = ref(false)
const seedMsg = ref('')

async function loadStats() {
  try {
    const { data } = await api.get('/statistics/overview')
    stats.value = data
    posteriors.value = data.posteriors || []
    completedCases.value = data.completed_cases_detail || []
    learningInsights.value = data.learning_insights || []
  } catch {
    // Stats endpoint may not exist yet
  }
}

async function seedData() {
  seeding.value = true
  seedMsg.value = ''
  try {
    const { data } = await api.post('/statistics/seed')
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

/* Learning Insights */
.insights-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.insight-card {
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-secondary, #fafafa);
}

.insight-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.insight-delta {
  font-weight: 700;
  font-size: 0.95rem;
}

.delta-up { color: var(--success); }
.delta-down { color: var(--danger); }

.insight-bar-row {
  margin-bottom: 8px;
}

.insight-bar-bg {
  position: relative;
  height: 12px;
  background: #e0e0e0;
  border-radius: 6px;
  overflow: hidden;
}

.insight-bar-prior {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: rgba(var(--primary-rgb, 25, 118, 210), 0.25);
  border-radius: 6px;
}

.insight-bar-post {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: var(--primary);
  border-radius: 6px;
  opacity: 0.8;
}

.insight-stats {
  font-size: 0.82rem;
  margin-bottom: 6px;
}

.insight-text {
  font-size: 0.85rem;
  color: var(--text-primary);
  margin: 0;
}
</style>
