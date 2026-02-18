<template>
  <div class="page">
    <div class="container">
      <div v-if="!caseStore.currentCase" class="text-center mt-3">
        <p class="loading-dots text-secondary">{{ t('dashboard.loading') }}</p>
      </div>

      <template v-else>
        <!-- Case Header -->
        <div class="case-header fade-in">
          <div class="case-header-left">
            <router-link to="/" class="back-link">&larr; {{ t('case.back') }}</router-link>
            <h1>{{ caseStore.currentCase.title }}</h1>
          </div>
          <span :class="['badge', `badge-${caseStore.currentCase.status}`]">
            {{ statusLabel(caseStore.currentCase.status) }}
          </span>
        </div>

        <div class="case-layout">
          <!-- Sidebar: Case Info & Documents -->
          <aside class="case-sidebar fade-in">
            <!-- Progress Stepper -->
            <div class="card mb-2">
              <h3 class="sidebar-title">{{ t('case.progress') }}</h3>
              <div class="stepper">
                <div
                  v-for="(step, i) in steps"
                  :key="step.key"
                  :class="['stepper-item', { active: isStepActive(step.key), done: isStepDone(step.key) }]"
                >
                  <div class="stepper-dot">
                    <span v-if="isStepDone(step.key)">&#10003;</span>
                    <span v-else>{{ i + 1 }}</span>
                  </div>
                  <span class="stepper-label">{{ step.label }}</span>
                </div>
              </div>
            </div>

            <!-- Case Details -->
            <div class="card mb-2">
              <h3 class="sidebar-title">{{ t('case.formAData') }}</h3>
              <dl class="detail-list">
                <template v-if="caseStore.currentCase.court_name">
                  <dt>{{ t('case.court') }}</dt>
                  <dd>{{ caseStore.currentCase.court_name }}</dd>
                </template>
                <template v-if="caseStore.currentCase.claimant_name">
                  <dt>{{ t('case.claimant') }}</dt>
                  <dd>{{ caseStore.currentCase.claimant_name }}</dd>
                </template>
                <template v-if="caseStore.currentCase.claimant_country">
                  <dt>{{ t('case.claimantCountry') }}</dt>
                  <dd>{{ caseStore.currentCase.claimant_country }}</dd>
                </template>
                <template v-if="caseStore.currentCase.defendant_name">
                  <dt>{{ t('case.defendant') }}</dt>
                  <dd>{{ caseStore.currentCase.defendant_name }}</dd>
                </template>
                <template v-if="caseStore.currentCase.defendant_country">
                  <dt>{{ t('case.defendantCountry') }}</dt>
                  <dd>{{ caseStore.currentCase.defendant_country }}</dd>
                </template>
                <template v-if="caseStore.currentCase.jurisdiction_basis">
                  <dt>{{ t('case.jurisdiction') }}</dt>
                  <dd>{{ caseStore.currentCase.jurisdiction_basis }}</dd>
                </template>
                <template v-if="caseStore.currentCase.is_cross_border != null">
                  <dt>{{ t('case.crossBorder') }}</dt>
                  <dd>{{ caseStore.currentCase.is_cross_border ? t('case.yes') : t('case.no') }}</dd>
                </template>
                <template v-if="caseStore.currentCase.claim_amount">
                  <dt>{{ t('case.amount') }}</dt>
                  <dd>{{ caseStore.currentCase.claim_amount.toFixed(2) }} {{ caseStore.currentCase.claim_currency || 'EUR' }}</dd>
                </template>
                <template v-if="caseStore.currentCase.applicable_law">
                  <dt>{{ t('case.applicableLaw') }}</dt>
                  <dd>{{ caseStore.currentCase.applicable_law }}</dd>
                </template>
                <template v-if="displayProbability != null">
                  <dt>{{ t('case.successProspect') }}</dt>
                  <dd>
                    <a href="#score-panel" class="score-link" @click.prevent="toggleScorePanel">
                      <span :class="probabilityClass(displayProbability)">
                        {{ (displayProbability * 100).toFixed(0) }}%
                      </span>
                      <span class="score-link-detail">{{ t('case.details') }} &#9662;</span>
                    </a>
                  </dd>
                </template>
                <template v-if="caseStore.currentCase.applicability_result">
                  <dt>{{ t('case.applicability') }}</dt>
                  <dd>{{ caseStore.currentCase.applicability_result }}</dd>
                </template>
              </dl>
            </div>

            <!-- Erfolgswahrscheinlichkeit Panel -->
            <div v-if="showScorePanel" id="score-panel" class="card mb-2 score-panel fade-in">
              <h3 class="sidebar-title">{{ t('case.successProspect') }}</h3>

              <div v-if="!score" class="text-secondary" style="font-size:0.82rem;">
                {{ t('case.noDetailedCalc') }}
              </div>

              <template v-else>
                <!-- Gesamtwahrscheinlichkeit -->
                <div class="score-hero-mini">
                  <div class="score-hero-val" :class="pcashClass(score.p_cash_success)">
                    {{ (score.p_cash_success * 100).toFixed(1) }}%
                  </div>
                  <div class="score-hero-label">{{ t('case.totalProbability') }}</div>
                </div>

                <!-- 5 Teilwahrscheinlichkeiten -->
                <div class="score-section">
                  <div class="score-section-title">{{ t('case.subProbabilities') }}</div>
                  <div v-for="p in probItems" :key="p.key" class="mini-prob-row">
                    <span class="mini-prob-label">{{ p.label }}</span>
                    <div class="mini-prob-bar-wrap">
                      <div class="mini-prob-bar" :style="{ width: (p.value * 100) + '%' }" :class="pcashClass(p.value)"></div>
                    </div>
                    <span class="mini-prob-val" :class="pcashClass(p.value)">{{ (p.value * 100).toFixed(0) }}%</span>
                  </div>
                </div>

                <!-- Scores -->
                <div class="score-section">
                  <div class="score-section-title">{{ t('case.scores') }}</div>
                  <div class="score-row">
                    <span>{{ t('case.evidenceScore') }}</span>
                    <span :class="scoreColor(score.evidence_score)">{{ score.evidence_score.toFixed(0) }}/100</span>
                  </div>
                  <div v-if="score.evidence_breakdown.missing?.length" class="score-missing">
                    {{ t('case.missingLabel') }}: {{ score.evidence_breakdown.missing.join(', ') }}
                  </div>
                  <div class="score-row">
                    <span>{{ t('case.abilityScore') }}</span>
                    <span :class="scoreColor(score.ability_score)">{{ score.ability_score.toFixed(0) }}/100</span>
                  </div>
                  <div class="score-row">
                    <span>{{ t('case.willingnessScore') }}</span>
                    <span :class="scoreColor(score.willingness_score)">{{ score.willingness_score.toFixed(0) }}/100</span>
                  </div>
                </div>

                <!-- Wie kam der Score zustande? -->
                <div v-if="score.drivers_json?.length" class="score-section">
                  <div class="score-section-title">{{ t('case.driversTitle') }}</div>
                  <div v-for="(d, i) in score.drivers_json" :key="i" :class="['score-driver', `score-driver-${d.direction}`]">
                    <span class="score-driver-icon">{{ d.direction === 'positive' ? '+' : '&minus;' }}</span>
                    <div>
                      <div class="score-driver-title">{{ d.factor }}</div>
                      <div class="score-driver-desc">{{ d.detail }}</div>
                    </div>
                  </div>
                </div>

                <!-- Expected Value -->
                <div v-if="caseStore.currentCase.claim_amount && score.p_cash_success" class="score-section">
                  <div class="score-section-title">{{ t('case.expectedValue') }}</div>
                  <div class="ev-mini">
                    <div class="ev-row">
                      <span>{{ t('case.evClaimAmount') }}</span>
                      <span>{{ caseStore.currentCase.claim_amount.toFixed(2) }} EUR</span>
                    </div>
                    <div class="ev-row">
                      <span>{{ t('case.evSuccessProb') }}</span>
                      <span>{{ (score.p_cash_success * 100).toFixed(1) }}%</span>
                    </div>
                    <div class="ev-row">
                      <span>{{ t('case.evExpectedPayment') }}</span>
                      <span>{{ expectedPayment.toFixed(2) }} EUR</span>
                    </div>
                    <div class="ev-row ev-cost">
                      <span>{{ t('case.evCourtFees') }}</span>
                      <span class="danger">-{{ courtFees.toFixed(2) }} EUR</span>
                    </div>
                    <div class="ev-row ev-cost">
                      <span>{{ t('case.evServiceCosts') }}</span>
                      <span class="danger">-75.00 EUR</span>
                    </div>
                    <div class="ev-row ev-cost">
                      <span>{{ t('case.evCommission') }}</span>
                      <span class="danger">-{{ commission.toFixed(2) }} EUR</span>
                    </div>
                    <div class="ev-row ev-total">
                      <span><strong>{{ t('case.evNetExpected') }}</strong></span>
                      <span :class="netEv >= 0 ? 'success' : 'danger'"><strong>{{ netEv.toFixed(2) }} EUR</strong></span>
                    </div>
                    <div class="ev-row ev-note">
                      <span>{{ t('case.evIfLoss') }}</span>
                      <span class="success">{{ t('case.evPortalCovers') }}</span>
                    </div>
                  </div>
                </div>

                <!-- Bayes-Update -->
                <div class="score-section">
                  <div class="score-section-title">{{ t('case.bayesUpdate') }}</div>
                  <table class="bayes-mini">
                    <thead>
                      <tr>
                        <th>{{ t('case.rate') }}</th>
                        <th>{{ t('case.alphaBeta') }}</th>
                        <th>{{ t('case.successTrials') }}</th>
                        <th>{{ t('case.estimate') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="rate in bayesRates" :key="rate">
                        <td>{{ rateLabels[rate] }}</td>
                        <td>{{ priors(rate).alpha }}/{{ priors(rate).beta }}</td>
                        <td>{{ obs(rate).successes }}/{{ obs(rate).trials }}</td>
                        <td :class="pcashClass(posteriors(rate).mean)">{{ (posteriors(rate).mean * 100).toFixed(0) }}%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div class="score-meta text-secondary">
                  {{ t('case.model') }} {{ score.model_version }} &middot; {{ formatDate(score.created_at) }}
                </div>
              </template>
            </div>

            <!-- Documents -->
            <div class="card mb-2">
              <h3 class="sidebar-title">{{ t('case.documents') }}</h3>
              <div v-if="caseStore.documents.length === 0" class="text-secondary" style="font-size:0.85rem;">
                {{ t('case.noDocuments') }}
              </div>
              <div v-for="doc in caseStore.documents" :key="doc.id" class="doc-item">
                <span class="doc-icon">&#128196;</span>
                <div class="doc-info">
                  <span class="doc-name">{{ doc.filename }}</span>
                  <span class="doc-date text-secondary">{{ formatDate(doc.created_at) }}</span>
                </div>
                <a
                  :href="caseStore.getDownloadUrl(caseStore.currentCase.id, doc.id)"
                  class="btn btn-sm btn-outline"
                  target="_blank"
                >
                  {{ t('case.download') }}
                </a>
              </div>
              <button
                v-if="canGenerateForm"
                class="btn btn-accent btn-block mt-2"
                :disabled="generatingForm"
                @click="handleGenerateForm"
              >
                {{ generatingForm ? t('case.generating') : t('case.generateFormA') }}
              </button>
            </div>

            <!-- Court Document Upload -->
            <div class="card" v-if="caseStore.currentCase.status === 'form_generation' || caseStore.currentCase.status === 'completed'">
              <h3 class="sidebar-title">{{ t('case.courtDocTitle') }}</h3>
              <p class="text-secondary" style="font-size:0.82rem;margin-bottom:12px;">
                {{ t('case.courtDocDesc') }}
              </p>
              <div class="court-upload-area">
                <input
                  type="file"
                  ref="courtDocInput"
                  @change="handleCourtDocUpload"
                  accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                  style="display:none;"
                />
                <button
                  class="btn btn-primary btn-block"
                  @click="$refs.courtDocInput.click()"
                  :disabled="uploadingCourtDoc"
                >
                  {{ uploadingCourtDoc ? t('case.uploading') : t('case.uploadBtn') }}
                </button>
              </div>
            </div>
          </aside>

          <!-- Chat Area -->
          <main class="chat-area card fade-in">
            <div class="chat-messages" ref="chatContainer">
              <div
                v-for="msg in caseStore.messages"
                :key="msg.id"
                :class="['message', `message-${msg.role}`]"
              >
                <div class="message-avatar">
                  <template v-if="msg.role === 'user'">&#128100;</template>
                  <img v-else :src="logoUrl" alt="AI" class="avatar-logo" />
                </div>
                <div class="message-body">
                  <div class="message-meta">
                    <span class="message-sender">
                      {{ msg.role === 'user' ? t('case.you') : t('case.aiAssistant') }}
                    </span>
                    <span class="message-time text-secondary">{{ formatTime(msg.created_at) }}</span>
                  </div>
                  <div class="message-content" v-html="renderMarkdown(msg.content)"></div>
                </div>
              </div>

              <div v-if="caseStore.loading" class="message message-assistant">
                <div class="message-avatar"><img :src="logoUrl" alt="AI" class="avatar-logo" /></div>
                <div class="message-body">
                  <div class="message-meta">
                    <span class="message-sender">{{ t('case.aiAssistant') }}</span>
                  </div>
                  <div class="message-content">
                    <span class="loading-dots">{{ t('case.analyzing') }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Input -->
            <div class="chat-input-area" v-if="!isCaseClosed">
              <form @submit.prevent="handleSend" class="chat-form">
                <textarea
                  v-model="messageText"
                  class="chat-input"
                  rows="3"
                  :placeholder="t('case.writeMessage')"
                  @keydown.enter.exact.prevent="handleSend"
                  :disabled="caseStore.loading"
                ></textarea>
                <button
                  type="submit"
                  class="btn btn-primary send-btn"
                  :disabled="!messageText.trim() || caseStore.loading"
                >
                  {{ t('case.send') }} &rarr;
                </button>
              </form>
            </div>
            <div v-else class="chat-closed">
              <p>{{ t('case.caseClosed') }} <strong>{{ statusLabel(caseStore.currentCase.status) }}</strong>.</p>
            </div>
          </main>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useCaseStore } from '../stores/case'
import { useI18nStore } from '../stores/i18n'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import logoUrl from '../assets/images/logo.svg'

const route = useRoute()
const caseStore = useCaseStore()
const { t } = useI18nStore()

const messageText = ref('')
const chatContainer = ref(null)
const generatingForm = ref(false)
const showScorePanel = ref(false)
const uploadingCourtDoc = ref(false)
const courtDocInput = ref(null)

const caseId = computed(() => route.params.id)

const isCaseClosed = computed(() =>
  ['completed', 'rejected'].includes(caseStore.currentCase?.status)
)

const canGenerateForm = computed(() =>
  caseStore.currentCase?.status === 'form_generation' ||
  caseStore.currentCase?.status === 'completed'
)

const steps = computed(() => [
  { key: 'intake', label: t('status.intake') },
  { key: 'applicability_check', label: t('status.applicability_check') },
  { key: 'case_assessment', label: t('status.case_assessment') },
  { key: 'evidence_collection', label: t('status.evidence_collection') },
  { key: 'form_generation', label: t('status.form_generation') },
  { key: 'completed', label: t('status.completed') },
])

const stepOrder = computed(() =>
  Object.fromEntries(steps.value.map((s, i) => [s.key, i]))
)

function isStepActive(key) {
  return caseStore.currentCase?.status === key
}

function isStepDone(key) {
  const current = stepOrder.value[caseStore.currentCase?.status] ?? -1
  return stepOrder.value[key] < current
}

onMounted(async () => {
  await caseStore.fetchCase(caseId.value)
  await Promise.all([
    caseStore.fetchMessages(caseId.value),
    caseStore.fetchDocuments(caseId.value),
    caseStore.fetchScore(caseId.value),
  ])
  scrollToBottom()
})

watch(() => caseStore.messages.length, () => {
  nextTick(scrollToBottom)
})

async function handleSend() {
  const text = messageText.value.trim()
  if (!text) return
  messageText.value = ''
  caseStore.messages.push({
    id: 'temp-' + Date.now(),
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  })
  nextTick(scrollToBottom)
  await caseStore.sendMessage(caseId.value, text)
  await Promise.all([
    caseStore.fetchDocuments(caseId.value),
    caseStore.fetchScore(caseId.value),
  ])
}

async function handleGenerateForm() {
  generatingForm.value = true
  try {
    await caseStore.generateFormA(caseId.value)
    await caseStore.fetchMessages(caseId.value)
    await caseStore.fetchCase(caseId.value)
  } finally {
    generatingForm.value = false
  }
}

async function handleCourtDocUpload(event) {
  const file = event.target.files[0]
  if (!file) return
  uploadingCourtDoc.value = true
  try {
    await caseStore.uploadDocument(caseId.value, file, 'court_document')
    await caseStore.fetchDocuments(caseId.value)
  } finally {
    uploadingCourtDoc.value = false
    if (courtDocInput.value) courtDocInput.value.value = ''
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text || ''))
}

function formatTime(dateStr) {
  return new Date(dateStr).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDate(dateStr) {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function statusLabel(status) {
  return t(`status.${status}`) || status
}

function probabilityClass(p) {
  if (p >= 0.6) return 'prob-high'
  if (p >= 0.3) return 'prob-medium'
  return 'prob-low'
}

// --- Score panel ---
const score = computed(() => caseStore.processScore)

const displayProbability = computed(() => {
  if (score.value?.p_cash_success != null) return score.value.p_cash_success
  return caseStore.currentCase?.success_probability ?? null
})

async function toggleScorePanel() {
  showScorePanel.value = !showScorePanel.value
  if (showScorePanel.value && !score.value) {
    await caseStore.fetchScore(caseId.value)
  }
}

const probItems = computed(() => {
  if (!score.value) return []
  return [
    { key: 'served', label: t('case.served'), value: score.value.p_served },
    { key: 'default', label: t('case.defaultRate'), value: score.value.p_default },
    { key: 'win', label: t('case.winContested'), value: score.value.p_win_contested },
    { key: 'settle', label: t('case.settle'), value: score.value.p_settle },
    { key: 'collect', label: t('case.collect'), value: score.value.p_collect },
  ]
})

const bayesRates = ['served', 'default', 'settle', 'collect']
const rateLabels = computed(() => ({
  served: t('case.served'),
  default: t('case.defaultRate'),
  settle: t('case.settle'),
  collect: t('case.collect'),
}))

function priors(rate) { return score.value?.priors_json?.[rate] || { alpha: 0, beta: 0 } }
function obs(rate) { return score.value?.observations_json?.[rate] || { successes: 0, trials: 0 } }
function posteriors(rate) { return score.value?.posteriors_json?.[rate] || { alpha: 0, beta: 0, mean: 0 } }

function pcashClass(p) {
  if (p >= 0.5) return 'prob-high'
  if (p >= 0.25) return 'prob-medium'
  return 'prob-low'
}

function scoreColor(s) {
  if (s >= 60) return 'prob-high'
  if (s >= 35) return 'prob-medium'
  return 'prob-low'
}

// --- Expected Value ---
const expectedPayment = computed(() => {
  if (!score.value || !caseStore.currentCase?.claim_amount) return 0
  return caseStore.currentCase.claim_amount * score.value.p_cash_success
})

const courtFees = computed(() => {
  const amount = caseStore.currentCase?.claim_amount || 0
  return Math.max(35, amount * 0.035)
})

const commission = computed(() => expectedPayment.value * 0.3)

const netEv = computed(() =>
  expectedPayment.value - courtFees.value - 75 - commission.value
)
</script>

<style scoped>
/* Case Header */
.case-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.case-header-left {
  flex: 1;
}

.back-link {
  font-size: 0.85rem;
  color: var(--text-secondary);
  text-decoration: none;
  display: inline-block;
  margin-bottom: 6px;
}

.back-link:hover {
  color: var(--primary);
}

.case-header h1 {
  font-size: 1.4rem;
  font-weight: 700;
}

/* Layout */
.case-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 900px) {
  .case-layout {
    grid-template-columns: 1fr;
  }
}

/* Sidebar */
.sidebar-title {
  font-size: 0.9rem;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--primary);
}

/* Stepper */
.stepper {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stepper-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: 0.82rem;
  color: var(--text-light);
}

.stepper-item.active {
  color: var(--primary);
  font-weight: 600;
}

.stepper-item.done {
  color: var(--success);
}

.stepper-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  flex-shrink: 0;
  background: var(--border);
  color: var(--text-light);
}

.stepper-item.active .stepper-dot {
  background: var(--primary);
  color: white;
}

.stepper-item.done .stepper-dot {
  background: var(--success);
  color: white;
}

/* Detail List */
.detail-list {
  font-size: 0.85rem;
}

.detail-list dt {
  font-weight: 600;
  color: var(--text-secondary);
  margin-top: 8px;
}

.detail-list dd {
  margin: 2px 0 0 0;
}

/* Documents */
.doc-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.doc-item:last-of-type {
  border-bottom: none;
}

.doc-icon {
  font-size: 1.3rem;
}

.doc-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.doc-name {
  font-size: 0.82rem;
  font-weight: 500;
  word-break: break-all;
}

.doc-date {
  font-size: 0.72rem;
}

/* Chat Area */
.chat-area {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-height) - 120px);
  min-height: 500px;
  padding: 0;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
}

.message-user .message-avatar {
  background: #e3f2fd;
}

.message-assistant .message-avatar {
  background: var(--primary);
  color: white;
  font-size: 0.9rem;
}

.avatar-logo {
  width: 24px;
  height: 24px;
  object-fit: contain;
}

.message-body {
  flex: 1;
  min-width: 0;
}

.message-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}

.message-sender {
  font-size: 0.82rem;
  font-weight: 600;
}

.message-time {
  font-size: 0.72rem;
}

.message-content {
  font-size: 0.92rem;
  line-height: 1.6;
}

.message-content :deep(p) {
  margin-bottom: 8px;
}

.message-content :deep(p:last-child) {
  margin-bottom: 0;
}

.message-content :deep(ul),
.message-content :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.message-content :deep(strong) {
  font-weight: 600;
}

.message-content :deep(code) {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.85em;
}

/* Chat Input */
.chat-input-area {
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  background: #fafafa;
}

.chat-form {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.chat-input {
  flex: 1;
  padding: 10px 14px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  font-family: inherit;
  font-size: 0.92rem;
  resize: none;
  line-height: 1.5;
}

.chat-input:focus {
  outline: none;
  border-color: var(--primary-light);
  box-shadow: 0 0 0 3px rgba(57, 73, 171, 0.1);
}

.send-btn {
  padding: 10px 24px;
  height: fit-content;
}

.chat-closed {
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  text-align: center;
  color: var(--text-secondary);
  font-size: 0.9rem;
  background: #fafafa;
}

/* Probability */
.prob-high { color: var(--success); font-weight: 600; }
.prob-medium { color: var(--warning); font-weight: 600; }
.prob-low { color: var(--danger); font-weight: 600; }

/* Score Link */
.score-link {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
}
.score-link:hover { text-decoration: none; }
.score-link-detail {
  font-size: 0.72rem;
  color: var(--primary-light);
  font-weight: 400;
}
.score-link:hover .score-link-detail { text-decoration: underline; }

/* Score Panel */
.score-panel {
  border-left: 3px solid var(--primary);
}

.score-hero-mini {
  text-align: center;
  padding: 12px 0;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.score-hero-val { font-size: 2rem; font-weight: 800; line-height: 1; }
.score-hero-label { font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px; }

.score-section { margin-bottom: 14px; }
.score-section-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

/* Mini probability bars */
.mini-prob-row { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.mini-prob-label { font-size: 0.75rem; width: 100px; flex-shrink: 0; color: var(--text-secondary); }
.mini-prob-bar-wrap { flex: 1; height: 10px; background: #f0f0f0; border-radius: 5px; overflow: hidden; }
.mini-prob-bar { height: 100%; border-radius: 5px; transition: width 0.4s ease; min-width: 2px; }
.mini-prob-bar.prob-high { background: var(--success); }
.mini-prob-bar.prob-medium { background: var(--warning); }
.mini-prob-bar.prob-low { background: var(--danger); }
.mini-prob-val { font-size: 0.75rem; width: 32px; text-align: right; }

/* Score rows */
.score-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.82rem;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
}
.score-missing {
  font-size: 0.72rem;
  color: var(--danger);
  padding: 2px 0 6px;
}

/* Score drivers */
.score-driver {
  display: flex;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  margin-bottom: 4px;
  font-size: 0.78rem;
}
.score-driver-positive { background: #e8f5e9; }
.score-driver-negative { background: #ffebee; }
.score-driver-icon { font-weight: 800; font-size: 0.9rem; width: 16px; text-align: center; flex-shrink: 0; }
.score-driver-positive .score-driver-icon { color: var(--success); }
.score-driver-negative .score-driver-icon { color: var(--danger); }
.score-driver-title { font-weight: 600; }
.score-driver-desc { color: var(--text-secondary); font-size: 0.72rem; }

/* Bayes mini table */
.bayes-mini { width: 100%; border-collapse: collapse; font-size: 0.75rem; }
.bayes-mini th {
  text-align: left;
  padding: 4px 6px;
  border-bottom: 1.5px solid var(--border);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.7rem;
}
.bayes-mini td {
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
}

.score-meta { font-size: 0.7rem; text-align: right; margin-top: 8px; }

/* Expected Value mini */
.ev-mini {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 12px;
}
.ev-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.82rem;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
}
.ev-row.ev-cost { font-size: 0.78rem; }
.ev-row.ev-total {
  border-top: 2px solid var(--primary);
  border-bottom: none;
  padding-top: 8px;
  font-size: 0.9rem;
}
.ev-row.ev-note {
  border-bottom: none;
  font-size: 0.75rem;
  color: var(--text-secondary);
  padding-top: 8px;
}
.success { color: var(--success); font-weight: 600; }
.danger { color: var(--danger); font-weight: 600; }

/* Court doc upload */
.court-upload-area {
  padding: 8px 0;
}
</style>
