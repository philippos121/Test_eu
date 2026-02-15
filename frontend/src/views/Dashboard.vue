<template>
  <div class="page">
    <div class="container">
      <!-- Welcome Section -->
      <section class="welcome-section fade-in">
        <div class="welcome-content">
          <h1>Willkommen, {{ auth.user?.full_name || 'Nutzer' }}</h1>
          <p>
            Verwalten Sie Ihre EU-Bagatellverfahren und lassen Sie sich von
            unserem KI-Assistenten durch das Verfahren leiten.
          </p>
        </div>
        <button class="btn btn-accent btn-lg" @click="showNewCaseDialog = true">
          + Neuen Fall anlegen
        </button>
      </section>

      <!-- Process Overview -->
      <section class="process-overview card fade-in mt-3">
        <h2 class="mb-2">So funktioniert es</h2>
        <div class="process-steps">
          <div class="step">
            <div class="step-number">1</div>
            <h3>Anwendbarkeit prüfen</h3>
            <p>Der KI-Assistent prüft, ob Ihr Fall für das EU-Bagatellverfahren geeignet ist.</p>
          </div>
          <div class="step">
            <div class="step-number">2</div>
            <h3>Sachverhalt schildern</h3>
            <p>Schildern Sie den Sachverhalt detailliert und geben Sie Ihre Beweismittel an.</p>
          </div>
          <div class="step">
            <div class="step-number">3</div>
            <h3>Prozessaussichten</h3>
            <p>Erhalten Sie eine Einschätzung Ihrer Erfolgsaussichten basierend auf der Rechtslage.</p>
          </div>
          <div class="step">
            <div class="step-number">4</div>
            <h3>Formular erstellen</h3>
            <p>Bei positiver Prognose wird das Klageformblatt A automatisch für Sie ausgefüllt.</p>
          </div>
        </div>
      </section>

      <!-- Cases List -->
      <section class="cases-section mt-3 fade-in">
        <div class="card-header">
          <h2>Meine Fälle</h2>
          <span class="text-secondary" v-if="caseStore.cases.length">
            {{ caseStore.cases.length }} {{ caseStore.cases.length === 1 ? 'Fall' : 'Fälle' }}
          </span>
        </div>

        <div v-if="caseStore.loading" class="text-center mt-3">
          <p class="loading-dots text-secondary">Laden</p>
        </div>

        <div v-else-if="caseStore.cases.length === 0" class="empty-state">
          <div class="empty-icon">&#128221;</div>
          <h3>Noch keine Fälle</h3>
          <p class="text-secondary">
            Legen Sie Ihren ersten Fall an, um mit dem EU-Bagatellverfahren zu beginnen.
          </p>
          <button class="btn btn-primary mt-2" @click="showNewCaseDialog = true">
            Ersten Fall anlegen
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
                <strong>Streitwert:</strong> {{ c.claim_amount.toFixed(2) }} {{ c.claim_currency || 'EUR' }}
              </p>
              <p v-if="c.defendant_name">
                <strong>Beklagter:</strong> {{ c.defendant_name }}
              </p>
              <p v-if="c.success_probability != null">
                <strong>Erfolgswahrscheinlichkeit:</strong>
                <span :class="probabilityClass(c.success_probability)">
                  {{ (c.success_probability * 100).toFixed(0) }}%
                </span>
              </p>
            </div>
            <div class="case-card-footer text-secondary">
              Erstellt am {{ formatDate(c.created_at) }}
            </div>
          </div>
        </div>
      </section>

      <!-- New Case Modal -->
      <div v-if="showNewCaseDialog" class="modal-overlay" @click.self="showNewCaseDialog = false">
        <div class="modal-content card fade-in">
          <h2>Neuen Fall anlegen</h2>
          <p class="text-secondary mb-2">
            Geben Sie eine kurze Bezeichnung für Ihren Fall an.
          </p>
          <form @submit.prevent="handleCreateCase">
            <div class="form-group">
              <label for="caseTitle">Fallbezeichnung</label>
              <input
                id="caseTitle"
                v-model="newCaseTitle"
                type="text"
                class="form-control"
                placeholder="z.B. Forderung gegen Firma XY - Unbezahlte Rechnung"
                required
                autofocus
              />
            </div>
            <div class="flex gap-1" style="justify-content: flex-end;">
              <button type="button" class="btn btn-outline" @click="showNewCaseDialog = false">
                Abbrechen
              </button>
              <button type="submit" class="btn btn-primary" :disabled="creatingCase">
                {{ creatingCase ? 'Wird erstellt...' : 'Fall anlegen' }}
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

const auth = useAuthStore()
const caseStore = useCaseStore()
const router = useRouter()

const showNewCaseDialog = ref(false)
const newCaseTitle = ref('')
const creatingCase = ref(false)

onMounted(() => {
  caseStore.fetchCases()
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

const STATUS_LABELS = {
  intake: 'Aufnahme',
  applicability_check: 'Anwendbarkeitsprüfung',
  case_assessment: 'Fallprüfung',
  evidence_collection: 'Beweisaufnahme',
  form_generation: 'Formularerstellung',
  completed: 'Abgeschlossen',
  rejected: 'Abgelehnt',
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status
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
