<template>
  <div class="page">
    <div class="container">
      <!-- Welcome Section -->
      <section class="welcome-section fade-in">
        <div class="welcome-content">
          <h1>{{ t('dashboard.welcome') }}, {{ auth.user?.full_name || 'Nutzer' }}</h1>
          <p>{{ t('dashboard.welcomeText') }}</p>
        </div>
        <div class="welcome-actions">
          <button class="btn btn-accent btn-lg" @click="showNewCaseDialog = true">
            {{ t('dashboard.newCase') }}
          </button>
          <router-link to="/project" class="btn btn-outline btn-lg" style="color:white;border-color:rgba(255,255,255,0.5);">
            {{ t('dashboard.projectDescription') }}
          </router-link>
        </div>
      </section>

      <!-- Process Overview -->
      <section class="process-overview card fade-in mt-3">
        <h2 class="mb-2">{{ t('dashboard.howItWorks') }}</h2>
        <div class="process-steps">
          <div class="step">
            <div class="step-number">1</div>
            <h3>{{ t('dashboard.step1Title') }}</h3>
            <p>{{ t('dashboard.step1Desc') }}</p>
          </div>
          <div class="step">
            <div class="step-number">2</div>
            <h3>{{ t('dashboard.step2Title') }}</h3>
            <p>{{ t('dashboard.step2Desc') }}</p>
          </div>
          <div class="step">
            <div class="step-number">3</div>
            <h3>{{ t('dashboard.step3Title') }}</h3>
            <p>{{ t('dashboard.step3Desc') }}</p>
          </div>
          <div class="step">
            <div class="step-number">4</div>
            <h3>{{ t('dashboard.step4Title') }}</h3>
            <p>{{ t('dashboard.step4Desc') }}</p>
          </div>
        </div>
      </section>

      <!-- Example Completed Cases -->
      <section class="card fade-in mt-3" v-if="exampleCases.length">
        <div class="card-header">
          <h2>{{ t('dashboard.exampleCases') }}</h2>
          <router-link to="/statistics" class="btn btn-outline btn-sm">
            {{ t('dashboard.viewStatistics') }}
          </router-link>
        </div>
        <p class="text-secondary mb-2">{{ t('dashboard.exampleCasesDesc') }}</p>
        <table class="example-table">
          <thead>
            <tr>
              <th>{{ t('dashboard.caseLabel') }}</th>
              <th>{{ t('dashboard.claimAmount') }}</th>
              <th>{{ t('dashboard.outcome') }}</th>
              <th>{{ t('dashboard.pCash') }}</th>
              <th>{{ t('dashboard.netEv') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in exampleCases" :key="c.id">
              <td>{{ c.title }}</td>
              <td>{{ c.claim_amount?.toFixed(2) }} {{ c.claim_currency || 'EUR' }}</td>
              <td>
                <span :class="['badge', c.outcome_success ? 'badge-completed' : 'badge-rejected']">
                  {{ c.outcome_success ? t('dashboard.successful') : t('dashboard.unsuccessful') }}
                </span>
              </td>
              <td>{{ c.p_cash_success != null ? (c.p_cash_success * 100).toFixed(0) + '%' : '-' }}</td>
              <td :class="c.net_ev >= 0 ? 'ev-positive' : 'ev-negative'">
                {{ c.net_ev != null ? c.net_ev.toFixed(0) + ' EUR' : '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Cases List -->
      <section class="cases-section mt-3 fade-in">
        <div class="card-header">
          <h2>{{ t('dashboard.myCases') }}</h2>
          <span class="text-secondary" v-if="caseStore.cases.length">
            {{ caseStore.cases.length }} {{ caseStore.cases.length === 1 ? t('dashboard.caseCount') : t('dashboard.casesCount') }}
          </span>
        </div>

        <div v-if="caseStore.loading" class="text-center mt-3">
          <p class="loading-dots text-secondary">{{ t('dashboard.loading') }}</p>
        </div>

        <div v-else-if="caseStore.cases.length === 0" class="empty-state">
          <div class="empty-icon">&#128221;</div>
          <h3>{{ t('dashboard.noCases') }}</h3>
          <p class="text-secondary">{{ t('dashboard.noCasesText') }}</p>
          <button class="btn btn-primary mt-2" @click="showNewCaseDialog = true">
            {{ t('dashboard.createFirst') }}
          </button>
        </div>

        <div v-else class="cases-grid">
          <div
            v-for="c in caseStore.cases"
            :key="c.id"
            class="case-card card"
            @click="$router.push(`/cases/${c.id}`)"
          >
            <div class="case-card-top">
              <h3>{{ c.title }}</h3>
              <span :class="['badge', `badge-${c.status}`]">{{ statusLabel(c.status) }}</span>
            </div>
            <div class="case-card-details">
              <p v-if="c.claim_amount">
                <strong>{{ t('dashboard.claimAmount') }}:</strong> {{ c.claim_amount.toFixed(2) }} {{ c.claim_currency || 'EUR' }}
              </p>
              <p v-if="c.defendant_name">
                <strong>{{ t('dashboard.defendant') }}:</strong> {{ c.defendant_name }}
              </p>
              <p v-if="c.success_probability != null">
                <strong>{{ t('dashboard.successProbability') }}:</strong>
                <span :class="probabilityClass(c.success_probability)">
                  {{ (c.success_probability * 100).toFixed(0) }}%
                </span>
              </p>
            </div>
            <div class="case-card-footer text-secondary">
              {{ t('dashboard.createdOn') }} {{ formatDate(c.created_at) }}
            </div>
          </div>
        </div>
      </section>

      <!-- New Case Modal -->
      <div v-if="showNewCaseDialog" class="modal-overlay" @click.self="showNewCaseDialog = false">
        <div class="modal-content card fade-in">
          <h2>{{ t('dashboard.createCaseTitle') }}</h2>
          <p class="text-secondary mb-2">{{ t('dashboard.createCaseText') }}</p>
          <form @submit.prevent="handleCreateCase">
            <div class="form-group">
              <label for="caseTitle">{{ t('dashboard.caseLabel') }}</label>
              <input
                id="caseTitle"
                v-model="newCaseTitle"
                type="text"
                class="form-control"
                :placeholder="t('dashboard.casePlaceholder')"
                required
                autofocus
              />
            </div>
            <div class="flex gap-1" style="justify-content: flex-end;">
              <button type="button" class="btn btn-outline" @click="showNewCaseDialog = false">
                {{ t('dashboard.cancel') }}
              </button>
              <button type="submit" class="btn btn-primary" :disabled="creatingCase">
                {{ creatingCase ? t('dashboard.creating') : t('dashboard.createCase') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useCaseStore } from '../stores/case'
import { useI18nStore } from '../stores/i18n'
import api from '../services/api'

const auth = useAuthStore()
const caseStore = useCaseStore()
const { t } = useI18nStore()
const router = useRouter()

const showNewCaseDialog = ref(false)
const newCaseTitle = ref('')
const creatingCase = ref(false)
const exampleCases = ref([])

async function loadExampleCases() {
  try {
    const { data } = await api.get('/statistics/overview')
    const allCompleted = data.completed_cases_detail || []
    exampleCases.value = allCompleted.filter(c => !c.title.startsWith('[HIST]')).slice(0, 5)
  } catch {
    // Statistics may not be available yet
  }
}

onMounted(() => {
  caseStore.fetchCases()
  loadExampleCases()
})

async function handleCreateCase() {
  creatingCase.value = true
  try {
    const newCase = await caseStore.createCase(newCaseTitle.value)
    showNewCaseDialog.value = false
    newCaseTitle.value = ''
    router.push(`/cases/${newCase.id}`)
  } finally {
    creatingCase.value = false
  }
}

function statusLabel(status) {
  return t(`status.${status}`) || status
}

function formatDate(dateStr) {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function probabilityClass(p) {
  if (p >= 0.6) return 'prob-high'
  if (p >= 0.3) return 'prob-medium'
  return 'prob-low'
}
</script>

<style scoped>
.welcome-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
  color: white;
  padding: 32px;
  border-radius: var(--radius-lg);
  gap: 24px;
  flex-wrap: wrap;
}

.welcome-content h1 {
  font-size: 1.5rem;
  margin-bottom: 6px;
}

.welcome-content p {
  opacity: 0.85;
  font-size: 0.95rem;
  max-width: 500px;
}

.welcome-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* Process Steps */
.process-steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
}

.step {
  text-align: center;
  padding: 16px;
}

.step-number {
  width: 40px;
  height: 40px;
  background: var(--primary);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  margin: 0 auto 12px;
}

.step h3 {
  font-size: 0.95rem;
  margin-bottom: 6px;
}

.step p {
  font-size: 0.82rem;
  color: var(--text-secondary);
}

/* Cases Grid */
.cases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.case-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.case-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.case-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.case-card-top h3 {
  font-size: 1rem;
  line-height: 1.3;
}

.case-card-details {
  font-size: 0.88rem;
}

.case-card-details p {
  margin-bottom: 4px;
}

.case-card-footer {
  margin-top: 12px;
  font-size: 0.78rem;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 48px 20px;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 12px;
}

.empty-state h3 {
  margin-bottom: 6px;
}

/* Probability */
.prob-high { color: var(--success); font-weight: 600; }
.prob-medium { color: var(--warning); font-weight: 600; }
.prob-low { color: var(--danger); font-weight: 600; }

/* Example Cases Table */
.example-table {
  width: 100%;
  border-collapse: collapse;
}

.example-table th,
.example-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  font-size: 0.88rem;
}

.example-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ev-positive { color: var(--success); font-weight: 600; }
.ev-negative { color: var(--danger); font-weight: 600; }

.btn-sm {
  padding: 4px 12px;
  font-size: 0.82rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 20px;
}

.modal-content {
  width: 100%;
  max-width: 480px;
}

.modal-content h2 {
  margin-bottom: 8px;
}
</style>
