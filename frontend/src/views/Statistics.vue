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

      <!-- Pipeline v3 Aggregates -->
      <section class="card fade-in mt-3" v-if="pipelineAgg">
        <h2>Pipeline v3 — Dreistufiges Wahrscheinlichkeitsmodell</h2>
        <p class="text-secondary mb-2">Durchschnittswerte aus {{ pipelineAgg.total_evaluated }} bewerteten Fällen.</p>

        <div class="pipeline-flow">
          <div class="pipeline-tier">
            <div class="tier-label">Stufe 1: Rechtslage</div>
            <div class="tier-box tier-recht">
              <span class="tier-value">{{ (pipelineAgg.avg_p_recht * 100).toFixed(1) }}%</span>
              <span class="tier-name">p<sub>recht</sub></span>
            </div>
          </div>
          <div class="pipeline-arrow">&times;</div>
          <div class="pipeline-tier">
            <div class="tier-label">Stufe 2: Beweislage</div>
            <div class="tier-box tier-beweis">
              <span class="tier-value">{{ (pipelineAgg.avg_p_beweis * 100).toFixed(1) }}%</span>
              <span class="tier-name">p<sub>beweis</sub></span>
            </div>
          </div>
          <div class="pipeline-arrow">=</div>
          <div class="pipeline-tier">
            <div class="tier-label">Obsiegen</div>
            <div class="tier-box tier-obsiegen">
              <span class="tier-value">{{ (pipelineAgg.avg_p_obsiegen * 100).toFixed(1) }}%</span>
              <span class="tier-name">p<sub>obsiegen</sub></span>
            </div>
          </div>
          <div class="pipeline-arrow">&times;</div>
          <div class="pipeline-tier">
            <div class="tier-label">Stufe 3: Eintreibung</div>
            <div class="tier-box tier-eintreib">
              <span class="tier-value">{{ pipelineAgg.avg_p_eintreibung != null ? (pipelineAgg.avg_p_eintreibung * 100).toFixed(1) + '%' : '—' }}</span>
              <span class="tier-name">p<sub>eintreibung</sub></span>
            </div>
          </div>
          <div class="pipeline-arrow">=</div>
          <div class="pipeline-tier">
            <div class="tier-label">Gesamt</div>
            <div class="tier-box tier-gesamt">
              <span class="tier-value">{{ pipelineAgg.avg_p_gesamt != null ? (pipelineAgg.avg_p_gesamt * 100).toFixed(1) + '%' : '—' }}</span>
              <span class="tier-name">p<sub>gesamt</sub></span>
            </div>
          </div>
        </div>

        <div class="pipeline-ev-row mt-2">
          <div class="ev-card">
            <span class="ev-label">Ø EV<sub>Betreiber</sub></span>
            <span class="ev-value" :class="pipelineAgg.avg_ev >= 0 ? 'success' : 'danger'">
              {{ pipelineAgg.avg_ev?.toFixed(0) ?? '—' }} EUR
            </span>
          </div>
          <div class="ev-card">
            <span class="ev-label">Annahmequote (p &ge; 80%)</span>
            <span class="ev-value">{{ (pipelineAgg.take_case_rate * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </section>

      <!-- Bayesian Posteriors (existing 3-rate model) -->
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

      <!-- Bayes Learning Progression -->
      <section class="card fade-in mt-3" v-if="bayesSteps.length">
        <h2>Bayes-Update: Lernprogression</h2>
        <p class="text-secondary mb-2">
          Evolution der Beta-Prior-Parameter für Beweisführungselemente über {{ pipelineAgg?.total_evaluated || 0 }} Fälle.
          Zeigt, wie die Plattform aus abgeschlossenen Fällen lernt.
        </p>

        <div class="learning-chart">
          <div class="chart-header">
            <span class="chart-legend">
              <span class="legend-dot legend-cb"></span> contract_basis
              <span class="legend-dot legend-pf"></span> performance
            </span>
          </div>
          <div class="chart-area">
            <div class="chart-y-axis">
              <span>100%</span>
              <span>75%</span>
              <span>50%</span>
              <span>25%</span>
              <span>0%</span>
            </div>
            <div class="chart-bars">
              <div v-for="step in contractBasisSteps" :key="'cb-' + step.step" class="chart-bar-group"
                   :style="{ left: ((step.step - 1) / maxStep * 100) + '%' }">
                <div class="chart-bar bar-cb" :style="{ height: (step.mean * 100) + '%' }"
                     :title="'Schritt ' + step.step + ': ' + (step.mean * 100).toFixed(1) + '%'">
                </div>
              </div>
              <div v-for="step in performanceSteps" :key="'pf-' + step.step" class="chart-bar-group"
                   :style="{ left: ((step.step - 1) / maxStep * 100 + 1.5) + '%' }">
                <div class="chart-bar bar-pf" :style="{ height: (step.mean * 100) + '%' }"
                     :title="'Schritt ' + step.step + ': ' + (step.mean * 100).toFixed(1) + '%'">
                </div>
              </div>
            </div>
          </div>
          <div class="chart-x-label">Fallnummer (chronologisch)</div>
        </div>

        <table class="data-table mt-2">
          <thead>
            <tr>
              <th>Schritt</th>
              <th>Element</th>
              <th>&alpha;</th>
              <th>&beta;</th>
              <th>Posterior &mu;</th>
              <th>Ausgang</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="step in bayesSteps.slice(0, 20)" :key="step.step + step.element">
              <td>{{ step.step }}</td>
              <td><code>{{ step.element }}</code></td>
              <td>{{ step.alpha.toFixed(2) }}</td>
              <td>{{ step.beta.toFixed(2) }}</td>
              <td>
                <div class="prob-bar-container">
                  <div class="prob-bar" :style="{ width: (step.mean * 100) + '%' }"></div>
                  <span class="prob-bar-label">{{ (step.mean * 100).toFixed(1) }}%</span>
                </div>
              </td>
              <td>
                <span :class="['badge', step.case_outcome === 'success' ? 'badge-completed' : 'badge-rejected']">
                  {{ step.case_outcome === 'success' ? 'Erfolg' : 'Misserfolg' }}
                </span>
              </td>
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

      <!-- 5 Example Cases with Pipeline Breakdown -->
      <section class="card fade-in mt-2" v-if="exampleCases.length">
        <h2>5 Beispielfälle — Pipeline v3 Analyse</h2>
        <p class="text-secondary mb-2">Repräsentative Fälle mit vollständiger dreistufiger Wahrscheinlichkeitsanalyse.</p>
        <div class="example-cases-grid">
          <div v-for="c in exampleCases" :key="c.id" class="example-case-card">
            <div class="ec-header">
              <span class="ec-title">{{ c.title }}</span>
              <span :class="['badge', c.outcome_success ? 'badge-completed' : 'badge-rejected']">
                {{ c.outcome_success ? t('stats.successful') : t('stats.unsuccessful') }}
              </span>
            </div>
            <div class="ec-amount">{{ c.claim_amount?.toFixed(0) }} {{ c.claim_currency || 'EUR' }}</div>
            <div class="ec-pipeline" v-if="c.pipeline">
              <div class="ec-prob-row">
                <span class="ec-prob-label">p<sub>recht</sub></span>
                <div class="ec-prob-bar-bg">
                  <div class="ec-prob-bar tier-recht-bg" :style="{ width: (c.pipeline.p_recht * 100) + '%' }"></div>
                </div>
                <span class="ec-prob-val">{{ (c.pipeline.p_recht * 100).toFixed(0) }}%</span>
              </div>
              <div class="ec-prob-row">
                <span class="ec-prob-label">p<sub>beweis</sub></span>
                <div class="ec-prob-bar-bg">
                  <div class="ec-prob-bar tier-beweis-bg" :style="{ width: (c.pipeline.p_beweis * 100) + '%' }"></div>
                </div>
                <span class="ec-prob-val">{{ (c.pipeline.p_beweis * 100).toFixed(0) }}%</span>
              </div>
              <div class="ec-prob-row">
                <span class="ec-prob-label">p<sub>obsiegen</sub></span>
                <div class="ec-prob-bar-bg">
                  <div class="ec-prob-bar tier-obsiegen-bg" :style="{ width: (c.pipeline.p_obsiegen * 100) + '%' }"></div>
                </div>
                <span class="ec-prob-val">{{ (c.pipeline.p_obsiegen * 100).toFixed(0) }}%</span>
              </div>
              <div class="ec-prob-row" v-if="c.pipeline.p_eintreibung != null">
                <span class="ec-prob-label">p<sub>eintreib.</sub></span>
                <div class="ec-prob-bar-bg">
                  <div class="ec-prob-bar tier-eintreib-bg" :style="{ width: (c.pipeline.p_eintreibung * 100) + '%' }"></div>
                </div>
                <span class="ec-prob-val">{{ (c.pipeline.p_eintreibung * 100).toFixed(0) }}%</span>
              </div>
              <div class="ec-prob-row" v-if="c.pipeline.p_gesamt != null">
                <span class="ec-prob-label"><strong>p<sub>gesamt</sub></strong></span>
                <div class="ec-prob-bar-bg">
                  <div class="ec-prob-bar tier-gesamt-bg" :style="{ width: (c.pipeline.p_gesamt * 100) + '%' }"></div>
                </div>
                <span class="ec-prob-val"><strong>{{ (c.pipeline.p_gesamt * 100).toFixed(0) }}%</strong></span>
              </div>
              <div class="ec-ev-row">
                <span>EV<sub>Betreiber</sub>:</span>
                <span :class="c.pipeline.ev_betreiber >= 0 ? 'success' : 'danger'">
                  {{ c.pipeline.ev_betreiber?.toFixed(0) ?? '—' }} EUR
                </span>
                <span v-if="c.pipeline.take_case != null" :class="['badge', c.pipeline.take_case ? 'badge-completed' : 'badge-rejected']" style="margin-left: 8px;">
                  {{ c.pipeline.take_case ? 'Annahme' : 'Ablehnung' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Historical Cases Summary -->
      <section class="card fade-in mt-2" v-if="histCases.length">
        <h2>{{ t('stats.recentCases') }} ({{ histCases.length }} historische Fälle)</h2>
        <p class="text-secondary mb-2">Zusammenfassung der historischen Fälle mit Pipeline v3 Scores.</p>
        <div class="hist-summary">
          <div class="hist-stat">
            <span class="hist-number">{{ histCases.length }}</span>
            <span class="hist-label">Fälle gesamt</span>
          </div>
          <div class="hist-stat">
            <span class="hist-number success">{{ histCases.filter(c => c.outcome_success).length }}</span>
            <span class="hist-label">Erfolgreich</span>
          </div>
          <div class="hist-stat">
            <span class="hist-number danger">{{ histCases.filter(c => !c.outcome_success).length }}</span>
            <span class="hist-label">Nicht erfolgreich</span>
          </div>
          <div class="hist-stat">
            <span class="hist-number">{{ histCases.length > 0 ? (histCases.filter(c => c.outcome_success).length / histCases.length * 100).toFixed(0) + '%' : '-' }}</span>
            <span class="hist-label">Erfolgsrate</span>
          </div>
        </div>

        <!-- Pipeline distribution for historical cases -->
        <div class="hist-pipeline-dist mt-2" v-if="histPipelineCases.length">
          <h3>Pipeline-Verteilung (historisch)</h3>
          <table class="data-table">
            <thead>
              <tr>
                <th>Metrik</th>
                <th>Min</th>
                <th>Ø Mittelwert</th>
                <th>Max</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>p<sub>recht</sub></td>
                <td>{{ histPipelineMin('p_recht') }}%</td>
                <td><strong>{{ histPipelineAvg('p_recht') }}%</strong></td>
                <td>{{ histPipelineMax('p_recht') }}%</td>
              </tr>
              <tr>
                <td>p<sub>beweis</sub></td>
                <td>{{ histPipelineMin('p_beweis') }}%</td>
                <td><strong>{{ histPipelineAvg('p_beweis') }}%</strong></td>
                <td>{{ histPipelineMax('p_beweis') }}%</td>
              </tr>
              <tr>
                <td>p<sub>obsiegen</sub></td>
                <td>{{ histPipelineMin('p_obsiegen') }}%</td>
                <td><strong>{{ histPipelineAvg('p_obsiegen') }}%</strong></td>
                <td>{{ histPipelineMax('p_obsiegen') }}%</td>
              </tr>
              <tr>
                <td>p<sub>eintreibung</sub></td>
                <td>{{ histPipelineMin('p_eintreibung') }}%</td>
                <td><strong>{{ histPipelineAvg('p_eintreibung') }}%</strong></td>
                <td>{{ histPipelineMax('p_eintreibung') }}%</td>
              </tr>
              <tr>
                <td>EV<sub>Betreiber</sub></td>
                <td>{{ histEvMin() }} EUR</td>
                <td><strong>{{ histEvAvg() }} EUR</strong></td>
                <td>{{ histEvMax() }} EUR</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Fallback if no data -->
      <section class="card fade-in mt-2" v-if="!exampleCases.length && !histCases.length">
        <h2>{{ t('stats.recentCases') }}</h2>
        <table class="data-table">
          <tbody>
            <tr>
              <td colspan="5" class="text-center text-secondary">{{ t('stats.noCompleted') }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Seed Button (Admin) -->
      <section class="card fade-in mt-2 mb-3" v-if="auth.user?.is_admin">
        <h2>Admin: Seed-Daten</h2>
        <p class="text-secondary mb-1">Generiert 5 fiktive Beispielfälle + 100 historische Fälle mit Pipeline v3 Scores.</p>
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
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useI18nStore } from '../stores/i18n'
import api from '../services/api'

const auth = useAuthStore()
const { t } = useI18nStore()

const stats = ref({})
const posteriors = ref([])
const exampleCases = ref([])
const histCases = ref([])
const learningInsights = ref([])
const pipelineAgg = ref(null)
const bayesSteps = ref([])
const seeding = ref(false)
const updatingPriors = ref(false)
const seedMsg = ref('')

const contractBasisSteps = computed(() => bayesSteps.value.filter(s => s.element === 'contract_basis'))
const performanceSteps = computed(() => bayesSteps.value.filter(s => s.element === 'performance'))
const maxStep = computed(() => {
  if (!bayesSteps.value.length) return 1
  return Math.max(...bayesSteps.value.map(s => s.step))
})

const histPipelineCases = computed(() => histCases.value.filter(c => c.pipeline))

function histPipelineMin(field) {
  const vals = histPipelineCases.value.map(c => c.pipeline[field]).filter(v => v != null)
  return vals.length ? (Math.min(...vals) * 100).toFixed(1) : '—'
}
function histPipelineMax(field) {
  const vals = histPipelineCases.value.map(c => c.pipeline[field]).filter(v => v != null)
  return vals.length ? (Math.max(...vals) * 100).toFixed(1) : '—'
}
function histPipelineAvg(field) {
  const vals = histPipelineCases.value.map(c => c.pipeline[field]).filter(v => v != null)
  return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length * 100).toFixed(1) : '—'
}
function histEvMin() {
  const vals = histPipelineCases.value.map(c => c.pipeline.ev_betreiber).filter(v => v != null)
  return vals.length ? Math.min(...vals).toFixed(0) : '—'
}
function histEvMax() {
  const vals = histPipelineCases.value.map(c => c.pipeline.ev_betreiber).filter(v => v != null)
  return vals.length ? Math.max(...vals).toFixed(0) : '—'
}
function histEvAvg() {
  const vals = histPipelineCases.value.map(c => c.pipeline.ev_betreiber).filter(v => v != null)
  return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(0) : '—'
}

async function loadStats() {
  try {
    const { data } = await api.get('/statistics/overview')
    stats.value = data
    posteriors.value = data.posteriors || []
    learningInsights.value = data.learning_insights || []
    pipelineAgg.value = data.pipeline_aggregates || null
    bayesSteps.value = data.bayes_learning_progression || []
    const all = data.completed_cases_detail || []
    exampleCases.value = all.filter(c => !c.title.startsWith('[HIST]'))
    histCases.value = all.filter(c => c.title.startsWith('[HIST]'))
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

/* Pipeline v3 Flow */
.pipeline-flow {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 20px 0;
}

.pipeline-tier {
  text-align: center;
}

.tier-label {
  font-size: 0.72rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.tier-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 20px;
  border-radius: 12px;
  min-width: 100px;
}

.tier-value {
  font-size: 1.5rem;
  font-weight: 800;
  color: #fff;
}

.tier-name {
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.85);
  margin-top: 2px;
}

.tier-recht { background: linear-gradient(135deg, #1976d2, #1565c0); }
.tier-beweis { background: linear-gradient(135deg, #388e3c, #2e7d32); }
.tier-obsiegen { background: linear-gradient(135deg, #f57c00, #e65100); }
.tier-eintreib { background: linear-gradient(135deg, #7b1fa2, #6a1b9a); }
.tier-gesamt { background: linear-gradient(135deg, #c62828, #b71c1c); }

.pipeline-arrow {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-secondary);
  padding: 0 4px;
}

.pipeline-ev-row {
  display: flex;
  justify-content: center;
  gap: 32px;
}

.ev-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 24px;
  background: var(--bg-secondary, #fafafa);
  border-radius: var(--radius);
}

.ev-label {
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.ev-value {
  font-size: 1.3rem;
  font-weight: 700;
}

/* Data Table */
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

/* Bayes Learning Chart */
.learning-chart {
  padding: 16px 0;
}

.chart-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.chart-legend {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.legend-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  margin-right: 4px;
}

.legend-cb { background: #1976d2; }
.legend-pf { background: #388e3c; }

.chart-area {
  display: flex;
  height: 200px;
  border-left: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  position: relative;
}

.chart-y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding-right: 8px;
  font-size: 0.72rem;
  color: var(--text-secondary);
  width: 36px;
  text-align: right;
}

.chart-bars {
  position: relative;
  flex: 1;
  overflow: hidden;
}

.chart-bar-group {
  position: absolute;
  bottom: 0;
}

.chart-bar {
  width: 6px;
  border-radius: 3px 3px 0 0;
  transition: height 0.3s;
}

.bar-cb { background: #1976d2; }
.bar-pf { background: #388e3c; }

.chart-x-label {
  text-align: center;
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-top: 8px;
}

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

/* Example Cases Grid */
.example-cases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.example-case-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  background: var(--bg-secondary, #fafafa);
}

.ec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

.ec-title {
  font-size: 0.85rem;
  font-weight: 600;
  line-height: 1.3;
}

.ec-amount {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--primary);
  margin-bottom: 12px;
}

.ec-pipeline {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ec-prob-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ec-prob-label {
  font-size: 0.78rem;
  color: var(--text-secondary);
  min-width: 70px;
  text-align: right;
}

.ec-prob-bar-bg {
  flex: 1;
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.ec-prob-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s;
}

.tier-recht-bg { background: #1976d2; }
.tier-beweis-bg { background: #388e3c; }
.tier-obsiegen-bg { background: #f57c00; }
.tier-eintreib-bg { background: #7b1fa2; }
.tier-gesamt-bg { background: #c62828; }

.ec-prob-val {
  font-size: 0.82rem;
  font-weight: 600;
  min-width: 40px;
}

.ec-ev-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  margin-top: 4px;
  font-size: 0.85rem;
}

/* Historical Summary */
.hist-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
}

.hist-stat {
  text-align: center;
  padding: 16px;
  background: var(--bg-secondary, #fafafa);
  border-radius: var(--radius);
}

.hist-number {
  display: block;
  font-size: 1.8rem;
  font-weight: 800;
  color: var(--primary);
}

.hist-number.success { color: var(--success); }
.hist-number.danger { color: var(--danger); }

.hist-label {
  display: block;
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-top: 4px;
}

.hist-pipeline-dist h3 {
  font-size: 1rem;
  margin-bottom: 8px;
}

/* Badges */
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}

.badge-completed {
  background: rgba(56, 142, 60, 0.12);
  color: #2e7d32;
}

.badge-rejected {
  background: rgba(198, 40, 40, 0.12);
  color: #c62828;
}
</style>
