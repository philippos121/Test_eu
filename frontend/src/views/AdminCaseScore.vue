<template>
  <div class="page">
    <div class="container">
      <div v-if="!store.currentCase" class="text-center mt-3">
        <p class="loading-dots text-secondary">Laden</p>
      </div>

      <template v-else>
        <div class="page-header fade-in">
          <div>
            <router-link to="/admin" class="back-link">&larr; Admin Dashboard</router-link>
            <h1>{{ store.currentCase.title }}</h1>
            <span :class="['badge', `badge-${store.currentCase.status}`]">{{ statusLabel(store.currentCase.status) }}</span>
          </div>
          <div class="header-actions">
            <button class="btn btn-primary" :disabled="computing" @click="recompute">
              {{ computing ? 'Berechne...' : 'Score (neu) berechnen' }}
            </button>
            <button class="btn btn-outline" @click="showEventModal = true">+ Event</button>
          </div>
        </div>

        <!-- No score yet -->
        <div v-if="!score" class="card fade-in text-center mt-2">
          <p class="text-secondary mb-2">Noch kein Prozesschancen-Score berechnet.</p>
          <button class="btn btn-accent" @click="recompute" :disabled="computing">Score berechnen</button>
        </div>

        <!-- Score dashboard -->
        <template v-if="score">
          <!-- Big number: p_cash_success -->
          <div class="score-hero card fade-in">
            <div class="hero-main">
              <div class="hero-value" :class="probClass(score.p_cash_success)">
                {{ (score.p_cash_success * 100).toFixed(1) }}%
              </div>
              <div class="hero-label">p(cash_success) — Gesamtwahrscheinlichkeit "am Ende bezahlt"</div>
            </div>
            <div class="hero-meta">
              <span class="text-secondary">Modell: {{ score.model_version }}</span>
              <span class="text-secondary">{{ formatDateTime(score.created_at) }}</span>
            </div>
          </div>

          <!-- 3 v3-Säulen -->
          <div class="card fade-in mt-2">
            <h3 class="section-title">Drei Bewertungssäulen (v3)</h3>
            <div class="prob-bars">
              <div v-for="p in probItems" :key="p.key" class="prob-row">
                <div class="prob-label">{{ p.label }}</div>
                <div class="prob-bar-container">
                  <div class="prob-bar" :style="{ width: (p.value * 100) + '%' }" :class="probClass(p.value)"></div>
                </div>
                <div class="prob-value" :class="probClass(p.value)">{{ (p.value * 100).toFixed(1) }}%</div>
              </div>
            </div>
            <p class="formula-note">p(cash) = p(Anspruch gültig) × p(Anspruch beweisbar) × p(Zahlung)</p>
          </div>

          <!-- Rechtsgültigkeit-Breakdown (v3) -->
          <div v-if="score.legal_validity_json" class="card fade-in mt-2">
            <h3 class="section-title">Rechtliche Gültigkeitsprüfung (LLM + Statistik)</h3>
            <div class="breakdown-list">
              <div class="breakdown-item">
                <span>Anspruch entstanden</span>
                <span :class="['breakdown-val', probClass(score.legal_validity_json.p_entstanden)]">
                  {{ ((score.legal_validity_json.p_entstanden || 0) * 100).toFixed(0) }}%
                </span>
              </div>
              <div class="breakdown-item">
                <span>Anspruch nicht erloschen</span>
                <span :class="['breakdown-val', probClass(score.legal_validity_json.p_not_untergegangen)]">
                  {{ ((score.legal_validity_json.p_not_untergegangen || 0) * 100).toFixed(0) }}%
                </span>
              </div>
              <div class="breakdown-item">
                <span>Anspruch durchsetzbar</span>
                <span :class="['breakdown-val', probClass(score.legal_validity_json.p_durchsetzbar)]">
                  {{ ((score.legal_validity_json.p_durchsetzbar || 0) * 100).toFixed(0) }}%
                </span>
              </div>
              <div v-if="score.legal_validity_json.applicable_law" class="breakdown-item">
                <span>Anwendbares Recht</span>
                <span class="breakdown-val text-secondary" style="font-size:0.78rem">{{ score.legal_validity_json.applicable_law }}</span>
              </div>
            </div>
            <div v-if="score.legal_validity_json.key_legal_issues?.length" class="missing-list mt-1">
              <strong>Rechtliche Kernfragen:</strong>
              <span v-for="issue in score.legal_validity_json.key_legal_issues" :key="issue" class="missing-tag" style="background:#fff3e0;color:#e65100">{{ issue }}</span>
            </div>
            <div v-if="score.legal_validity_json.searches_performed?.length" class="trace-meta text-secondary mt-1">
              Web-Suchen: {{ score.legal_validity_json.searches_performed.join(' · ') }}
            </div>
          </div>

          <!-- Beweis-Score + Zahlungsfähigkeit + Zahlungswilligkeit -->
          <div class="score-grid mt-2">
            <div class="card fade-in">
              <h3 class="section-title">Beweis-Score</h3>
              <div class="big-score" :class="scoreClass(score.evidence_score)">{{ score.evidence_score.toFixed(0) }}<span class="score-max">/100</span></div>
              <div class="breakdown-list">
                <div class="breakdown-item" v-for="(val, key) in evidenceBreakdown" :key="key">
                  <span>{{ evidenceLabels[key] || key }}</span>
                  <span class="breakdown-val">{{ val }}</span>
                </div>
              </div>
              <div v-if="score.evidence_breakdown.missing?.length" class="missing-list mt-1">
                <strong>Fehlend:</strong>
                <span v-for="m in score.evidence_breakdown.missing" :key="m" class="missing-tag">{{ m }}</span>
              </div>
            </div>

            <div class="card fade-in">
              <h3 class="section-title">Zahlungsfähigkeit (LLM)</h3>
              <div class="big-score" :class="scoreClass(abilityScore)">{{ abilityScore.toFixed(0) }}<span class="score-max">/100</span></div>
              <div class="breakdown-list">
                <div v-if="paymentJson.insolvency_risk" class="breakdown-item">
                  <span>Insolvenzrisiko</span>
                  <span :class="['breakdown-val', insolvencyClass(paymentJson.insolvency_risk)]">{{ paymentJson.insolvency_risk }}</span>
                </div>
                <div v-if="paymentJson.ability_searches?.length" class="breakdown-item">
                  <span>Web-Suchen</span>
                  <span class="breakdown-val text-secondary" style="font-size:0.75rem">{{ paymentJson.ability_searches.length }} Abfrage(n)</span>
                </div>
              </div>
              <div v-if="paymentJson.ability_reasoning" class="trace-meta text-secondary mt-1">{{ paymentJson.ability_reasoning }}</div>
            </div>

            <div class="card fade-in">
              <h3 class="section-title">Zahlungswilligkeit (Verhalten)</h3>
              <div class="big-score" :class="scoreClass(willingnessScore)">{{ willingnessScore.toFixed(0) }}<span class="score-max">/100</span></div>
              <div class="breakdown-list">
                <div class="breakdown-item" v-for="(val, key) in willingnessItems" :key="key">
                  <span>{{ willingnessLabels[key] || key }}</span>
                  <span :class="['breakdown-val', flagClass(key, val)]">{{ formatFlag(val) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Bayes-Karte -->
          <div class="card fade-in mt-2">
            <h3 class="section-title">Bayes-Update: Prior &rarr; Beobachtungen &rarr; Posterior</h3>
            <table class="bayes-table">
              <thead>
                <tr>
                  <th>Rate</th>
                  <th>&alpha; (Prior)</th>
                  <th>&beta; (Prior)</th>
                  <th>s / n</th>
                  <th>&alpha;' (Post)</th>
                  <th>&beta;' (Post)</th>
                  <th>p&#770; (Posterior)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="rate in bayesRates" :key="rate">
                  <td class="rate-name">{{ rateLabels[rate] || rate }}</td>
                  <td>{{ priors(rate).alpha }}</td>
                  <td>{{ priors(rate).beta }}</td>
                  <td>{{ obs(rate).successes }} / {{ obs(rate).trials }}</td>
                  <td>{{ posteriors(rate).alpha }}</td>
                  <td>{{ posteriors(rate).beta }}</td>
                  <td :class="probClass(posteriors(rate).mean)">{{ (posteriors(rate).mean * 100).toFixed(1) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- NN Prediction -->
          <div class="card fade-in mt-2" v-if="score.p_nn_prediction != null">
            <h3 class="section-title">Neuronales Netz — Vorhersage</h3>
            <div class="model-meta">
              <div class="meta-item">
                <span class="meta-label">NN-Vorhersage (roh)</span>
                <span :class="['meta-val', probClass(score.p_nn_prediction)]">{{ (score.p_nn_prediction * 100).toFixed(1) }}%</span>
              </div>
              <div class="meta-item" v-if="score.nn_prediction_json?.nn_weight != null">
                <span class="meta-label">Mischgewicht</span>
                <span class="meta-val">{{ (score.nn_prediction_json.nn_weight * 100).toFixed(0) }}%</span>
              </div>
              <div class="meta-item" v-if="score.nn_prediction_json?.n_train_cases != null">
                <span class="meta-label">Trainingsfälle</span>
                <span class="meta-val">{{ score.nn_prediction_json.n_train_cases }}</span>
              </div>
              <div class="meta-item" v-if="score.nn_prediction_json?.val_accuracy != null">
                <span class="meta-label">Modell Val-Acc</span>
                <span :class="['meta-val', accClass(score.nn_prediction_json.val_accuracy)]">{{ (score.nn_prediction_json.val_accuracy * 100).toFixed(1) }}%</span>
              </div>
              <div class="meta-item" v-if="score.nn_prediction_json?.model_version != null">
                <span class="meta-label">Modell-Version</span>
                <span class="meta-val">v{{ score.nn_prediction_json.model_version }}</span>
              </div>
            </div>
            <p class="formula-note">p(cash) = {{ (score.nn_prediction_json?.nn_weight ?? 0) > 0 ? `(1 - ${(score.nn_prediction_json.nn_weight*100).toFixed(0)}%) × p_pillar + ${(score.nn_prediction_json.nn_weight*100).toFixed(0)}% × p_nn` : 'Pillar-Produkt (kein NN-Gewicht aktiv)' }}</p>
          </div>

          <!-- Drivers -->
          <div class="card fade-in mt-2" v-if="score.drivers_json?.length">
            <h3 class="section-title">Top-Einflussfaktoren</h3>
            <div class="drivers-list">
              <div v-for="(d, i) in score.drivers_json" :key="i" :class="['driver', `driver-${d.direction}`]">
                <span class="driver-icon">{{ d.direction === 'positive' ? '+' : '-' }}</span>
                <div>
                  <div class="driver-factor">{{ d.factor }}</div>
                  <div class="driver-detail text-secondary">{{ d.detail }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- LLM Trace -->
          <div class="card fade-in mt-2">
            <h3 class="section-title">LLM-Trace (Fragen / Antworten / Facts)</h3>
            <div v-if="!store.traces.length" class="text-secondary">Keine Traces vorhanden.</div>
            <div class="trace-list">
              <div v-for="t in store.traces" :key="t.id" class="trace-item">
                <div class="trace-q"><strong>Q:</strong> {{ t.question }}</div>
                <div class="trace-a"><strong>A:</strong> {{ truncate(t.answer, 300) }}</div>
                <div v-if="Object.keys(t.extracted_facts || {}).length" class="trace-facts">
                  <span class="fact-tag" v-for="(v, k) in t.extracted_facts" :key="k">{{ k }}: {{ v }}</span>
                </div>
                <div class="trace-meta text-secondary">{{ t.step }} &middot; {{ formatDateTime(t.created_at) }}</div>
              </div>
            </div>
          </div>

          <!-- Events -->
          <div class="card fade-in mt-2 mb-3">
            <h3 class="section-title">Case Events</h3>
            <div v-if="!store.events.length" class="text-secondary">Keine Events vorhanden.</div>
            <div class="event-list">
              <div v-for="ev in store.events" :key="ev.id" class="event-item">
                <span class="event-type badge badge-intake">{{ ev.event_type }}</span>
                <span class="text-secondary">{{ formatDateTime(ev.created_at) }}</span>
                <span v-if="Object.keys(ev.payload || {}).length" class="text-secondary">{{ JSON.stringify(ev.payload) }}</span>
              </div>
            </div>
          </div>
        </template>

        <!-- Add Event Modal -->
        <div v-if="showEventModal" class="modal-overlay" @click.self="showEventModal = false">
          <div class="modal-box card">
            <h3>Event hinzufügen</h3>
            <div class="form-group">
              <label>Event-Typ</label>
              <select v-model="newEventType" class="form-control">
                <option v-for="t in eventTypes" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="form-actions">
              <button class="btn btn-outline" @click="showEventModal = false">Abbrechen</button>
              <button class="btn btn-primary" @click="submitEvent">Hinzufügen</button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAdminStore } from '../stores/admin'

const route = useRoute()
const store = useAdminStore()
const caseId = computed(() => route.params.id)

const computing = ref(false)
const showEventModal = ref(false)
const newEventType = ref('FILED')

const eventTypes = [
  'FILED', 'SERVICE_OK', 'SERVICE_FAIL', 'DEFENDANT_RESPONDED',
  'DEFAULT', 'SETTLED', 'JUDGMENT_WIN', 'JUDGMENT_LOSS', 'PAYMENT_RECEIVED',
]

const score = computed(() => store.currentScore)

const STATUS_LABELS = {
  intake: 'Aufnahme', applicability_check: 'Anwendbarkeit',
  case_assessment: 'Fallprüfung', evidence_collection: 'Beweisaufnahme',
  form_generation: 'Formular', completed: 'Abgeschlossen', rejected: 'Abgelehnt',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }

// v3 three-pillar probabilities
const probItems = computed(() => {
  if (!score.value) return []
  return [
    { key: 'p_claim_valid',    label: 'Anspruch rechtlich gültig',  value: score.value.p_claim_valid    ?? 0 },
    { key: 'p_claim_provable', label: 'Anspruch beweisbar',         value: score.value.p_claim_provable ?? 0 },
    { key: 'p_payment',        label: 'Zahlung tatsächlich erfolgt', value: score.value.p_payment        ?? 0 },
  ]
})

const evidenceLabels = { contract: 'Vertrag/Auftrag', delivery: 'Liefernachweis', invoice: 'Rechnung/Fälligkeit', dunning: 'Mahnung' }
const evidenceBreakdown = computed(() => {
  if (!score.value) return {}
  const { missing, ...rest } = score.value.evidence_breakdown || {}
  return rest
})

// Payment analysis (v3) — falls back to legacy ability_components
const paymentJson = computed(() => score.value?.payment_analysis_json || {})
const abilityScore = computed(() => paymentJson.value.ability_score ?? score.value?.ability_score ?? 50)
const willingnessScore = computed(() => {
  const p = paymentJson.value.p_willingness
  return p != null ? Math.round(p * 100) : (score.value?.willingness_score ?? 50)
})

const willingnessLabels = { responded_to_reminder: 'Auf Mahnung reagiert', partial_payment: 'Teilzahlung', settlement_offered: 'Vergleich angeboten', repeat_defendant: 'Wiederholungstäter' }
const willingnessItems = computed(() => score.value?.willingness_components || {})

const bayesRates = ['valid', 'provable', 'payment']
const rateLabels = { valid: 'Anspruchs-Gültigkeit', provable: 'Beweisbarkeit', payment: 'Zahlung' }

function insolvencyClass(risk) {
  if (risk === 'high') return 'prob-low'
  if (risk === 'low') return 'prob-high'
  return 'prob-medium'
}
function accClass(a) {
  if (a == null) return ''
  if (a >= 0.75) return 'prob-high'
  if (a >= 0.60) return 'prob-medium'
  return 'prob-low'
}

function priors(rate) { return score.value?.priors_json?.[rate] || { alpha: 0, beta: 0 } }
function obs(rate) { return score.value?.observations_json?.[rate] || { successes: 0, trials: 0 } }
function posteriors(rate) { return score.value?.posteriors_json?.[rate] || { alpha: 0, beta: 0, mean: 0 } }

function probClass(p) {
  if (p >= 0.5) return 'prob-high'
  if (p >= 0.25) return 'prob-medium'
  return 'prob-low'
}
function scoreClass(s) {
  if (s >= 60) return 'prob-high'
  if (s >= 35) return 'prob-medium'
  return 'prob-low'
}
function flagClass(key, val) {
  // For boolean flags, show green/red
  if (typeof val === 'boolean') {
    if (key === 'insolvency_flag' || key === 'repeat_defendant') return val ? 'prob-low' : 'prob-high'
    return val ? 'prob-high' : 'prob-low'
  }
  return ''
}
function formatFlag(val) {
  if (val === true) return 'Ja'
  if (val === false) return 'Nein'
  if (val === null || val === undefined) return '—'
  return val
}
function formatDateTime(d) {
  return new Date(d).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function truncate(s, max) {
  if (!s) return ''
  return s.length > max ? s.slice(0, max) + '...' : s
}

async function recompute() {
  computing.value = true
  try {
    await store.computeScore(caseId.value)
  } finally {
    computing.value = false
  }
}

async function submitEvent() {
  await store.addEvent(caseId.value, newEventType.value)
  showEventModal.value = false
  // Recompute score after event
  await recompute()
}

onMounted(async () => {
  await store.fetchCase(caseId.value)
  await Promise.all([
    store.fetchScore(caseId.value),
    store.fetchEvents(caseId.value),
    store.fetchTraces(caseId.value),
  ])
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header h1 { font-size: 1.3rem; margin: 4px 0; }
.back-link { font-size: 0.85rem; color: var(--text-secondary); }
.back-link:hover { color: var(--primary); text-decoration: none; }
.header-actions { display: flex; gap: 8px; }

/* Hero */
.score-hero { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.hero-value { font-size: 3rem; font-weight: 800; line-height: 1; }
.hero-label { font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px; }
.hero-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; font-size: 0.78rem; }

.formula-note { font-size: 0.78rem; color: var(--text-secondary); margin-top: 12px; font-style: italic; text-align: center; }
.model-meta { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 8px; }
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
.meta-val { font-size: 1rem; font-weight: 700; }

/* Prob bars */
.prob-bars { display: flex; flex-direction: column; gap: 10px; }
.prob-row { display: flex; align-items: center; gap: 12px; }
.prob-label { width: 260px; font-size: 0.85rem; flex-shrink: 0; }
.prob-bar-container { flex: 1; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; }
.prob-bar { height: 100%; border-radius: 10px; transition: width 0.5s ease; min-width: 2px; }
.prob-bar.prob-high { background: var(--success); }
.prob-bar.prob-medium { background: var(--warning); }
.prob-bar.prob-low { background: var(--danger); }
.prob-value { width: 55px; text-align: right; font-weight: 600; font-size: 0.85rem; }

/* Score grid */
.score-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
@media (max-width: 900px) { .score-grid { grid-template-columns: 1fr; } }
.section-title { font-size: 0.95rem; font-weight: 600; color: var(--primary); margin-bottom: 14px; }
.big-score { font-size: 2.5rem; font-weight: 800; line-height: 1; margin-bottom: 12px; }
.score-max { font-size: 1rem; font-weight: 400; color: var(--text-light); }

.breakdown-list { display: flex; flex-direction: column; gap: 6px; }
.breakdown-item { display: flex; justify-content: space-between; font-size: 0.82rem; padding: 4px 0; border-bottom: 1px solid var(--border); }
.breakdown-val { font-weight: 600; }

.missing-list { font-size: 0.8rem; }
.missing-tag { display: inline-block; background: #ffebee; color: var(--danger); padding: 2px 8px; border-radius: 12px; margin: 2px 4px; font-size: 0.75rem; }

/* Bayes */
.bayes-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.bayes-table th { text-align: left; padding: 8px 12px; border-bottom: 2px solid var(--border); font-weight: 600; color: var(--text-secondary); font-size: 0.78rem; }
.bayes-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
.rate-name { font-weight: 600; }

/* Drivers */
.drivers-list { display: flex; flex-direction: column; gap: 8px; }
.driver { display: flex; gap: 10px; padding: 10px 14px; border-radius: var(--radius); font-size: 0.85rem; }
.driver-positive { background: #e8f5e9; }
.driver-negative { background: #ffebee; }
.driver-icon { font-size: 1.2rem; font-weight: 800; width: 24px; text-align: center; flex-shrink: 0; }
.driver-positive .driver-icon { color: var(--success); }
.driver-negative .driver-icon { color: var(--danger); }
.driver-factor { font-weight: 600; }
.driver-detail { font-size: 0.78rem; }

/* Traces */
.trace-list { display: flex; flex-direction: column; gap: 12px; max-height: 500px; overflow-y: auto; }
.trace-item { padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 0.82rem; }
.trace-q { margin-bottom: 4px; }
.trace-a { margin-bottom: 4px; color: var(--text-secondary); }
.trace-facts { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px; }
.fact-tag { background: #e3f2fd; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; }
.trace-meta { font-size: 0.72rem; margin-top: 4px; }

/* Events */
.event-list { display: flex; flex-direction: column; gap: 6px; }
.event-item { display: flex; align-items: center; gap: 12px; font-size: 0.82rem; padding: 6px 0; border-bottom: 1px solid var(--border); }
.event-type { font-family: monospace; }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.modal-box { width: 400px; max-width: 90vw; }
.modal-box h3 { margin-bottom: 16px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

.prob-high { color: var(--success); font-weight: 600; }
.prob-medium { color: var(--warning); font-weight: 600; }
.prob-low { color: var(--danger); font-weight: 600; }
</style>
