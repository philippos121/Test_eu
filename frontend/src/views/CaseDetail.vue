<template>
  <div class="page">
    <div class="container">
      <div v-if="!caseStore.currentCase" class="text-center mt-3">
        <p class="loading-dots text-secondary">Fall wird geladen</p>
      </div>

      <template v-else>
        <!-- Case Header -->
        <div class="case-header fade-in">
          <div class="case-header-left">
            <router-link to="/" class="back-link">&larr; Zurück</router-link>
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
              <h3 class="sidebar-title">Fortschritt</h3>
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
              <h3 class="sidebar-title">Falldaten (Formblatt A)</h3>
              <dl class="detail-list">
                <template v-if="caseStore.currentCase.court_name">
                  <dt>Gericht (Sek. 1)</dt>
                  <dd>{{ caseStore.currentCase.court_name }}</dd>
                </template>
                <template v-if="caseStore.currentCase.claimant_name">
                  <dt>Kläger (Sek. 2)</dt>
                  <dd>{{ caseStore.currentCase.claimant_name }}</dd>
                </template>
                <template v-if="caseStore.currentCase.claimant_country">
                  <dt>Kläger-Land</dt>
                  <dd>{{ caseStore.currentCase.claimant_country }}</dd>
                </template>
                <template v-if="caseStore.currentCase.defendant_name">
                  <dt>Beklagter (Sek. 3)</dt>
                  <dd>{{ caseStore.currentCase.defendant_name }}</dd>
                </template>
                <template v-if="caseStore.currentCase.defendant_country">
                  <dt>Beklagter-Land</dt>
                  <dd>{{ caseStore.currentCase.defendant_country }}</dd>
                </template>
                <template v-if="caseStore.currentCase.jurisdiction_basis">
                  <dt>Zuständigkeit (Sek. 4)</dt>
                  <dd>{{ caseStore.currentCase.jurisdiction_basis }}</dd>
                </template>
                <template v-if="caseStore.currentCase.is_cross_border != null">
                  <dt>Grenzüberschr. (Sek. 5)</dt>
                  <dd>{{ caseStore.currentCase.is_cross_border ? 'Ja' : 'Nein' }}</dd>
                </template>
                <template v-if="caseStore.currentCase.claim_amount">
                  <dt>Streitwert (Sek. 7)</dt>
                  <dd>{{ caseStore.currentCase.claim_amount.toFixed(2) }} {{ caseStore.currentCase.claim_currency || 'EUR' }}</dd>
                </template>
                <template v-if="caseStore.currentCase.applicable_law">
                  <dt>Anwendb. Recht</dt>
                  <dd>{{ caseStore.currentCase.applicable_law }}</dd>
                </template>
                <template v-if="caseStore.currentCase.success_probability != null">
                  <dt>Erfolgsaussicht</dt>
                  <dd>
                    <span :class="probabilityClass(caseStore.currentCase.success_probability)">
                      {{ (caseStore.currentCase.success_probability * 100).toFixed(0) }}%
                    </span>
                  </dd>
                </template>
                <template v-if="caseStore.currentCase.applicability_result">
                  <dt>Anwendbarkeit</dt>
                  <dd>{{ caseStore.currentCase.applicability_result }}</dd>
                </template>
              </dl>
            </div>

            <!-- Documents -->
            <div class="card">
              <h3 class="sidebar-title">Dokumente</h3>
              <div v-if="caseStore.documents.length === 0" class="text-secondary" style="font-size:0.85rem;">
                Noch keine Dokumente vorhanden.
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
                  Download
                </a>
              </div>
              <button
                v-if="canGenerateForm"
                class="btn btn-accent btn-block mt-2"
                :disabled="generatingForm"
                @click="handleGenerateForm"
              >
                {{ generatingForm ? 'Wird erstellt...' : 'Formblatt A erstellen' }}
              </button>
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
                  <img v-else src="/images/logo.jpg" alt="AI" class="avatar-logo" />
                </div>
                <div class="message-body">
                  <div class="message-meta">
                    <span class="message-sender">
                      {{ msg.role === 'user' ? 'Sie' : 'KI-Assistent' }}
                    </span>
                    <span class="message-time text-secondary">{{ formatTime(msg.created_at) }}</span>
                  </div>
                  <div class="message-content" v-html="renderMarkdown(msg.content)"></div>
                </div>
              </div>

              <div v-if="caseStore.loading" class="message message-assistant">
                <div class="message-avatar"><img src="/images/logo.jpg" alt="AI" class="avatar-logo" /></div>
                <div class="message-body">
                  <div class="message-meta">
                    <span class="message-sender">KI-Assistent</span>
                  </div>
                  <div class="message-content">
                    <span class="loading-dots">Analysiert</span>
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
                  placeholder="Schreiben Sie hier Ihre Nachricht..."
                  @keydown.enter.exact.prevent="handleSend"
                  :disabled="caseStore.loading"
                ></textarea>
                <button
                  type="submit"
                  class="btn btn-primary send-btn"
                  :disabled="!messageText.trim() || caseStore.loading"
                >
                  Senden &rarr;
                </button>
              </form>
            </div>
            <div v-else class="chat-closed">
              <p>Dieser Fall ist <strong>{{ statusLabel(caseStore.currentCase.status) }}</strong>.</p>
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
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const route = useRoute()
const caseStore = useCaseStore()

const messageText = ref('')
const chatContainer = ref(null)
const generatingForm = ref(false)

const caseId = computed(() => route.params.id)

const isCaseClosed = computed(() =>
  ['completed', 'rejected'].includes(caseStore.currentCase?.status)
)

const canGenerateForm = computed(() =>
  caseStore.currentCase?.status === 'form_generation' ||
  caseStore.currentCase?.status === 'completed'
)

const steps = [
  { key: 'intake', label: 'Aufnahme' },
  { key: 'applicability_check', label: 'Anwendbarkeit' },
  { key: 'case_assessment', label: 'Fallprüfung' },
  { key: 'evidence_collection', label: 'Beweisaufnahme' },
  { key: 'form_generation', label: 'Formular' },
  { key: 'completed', label: 'Abgeschlossen' },
]

const stepOrder = Object.fromEntries(steps.map((s, i) => [s.key, i]))

function isStepActive(key) {
  return caseStore.currentCase?.status === key
}

function isStepDone(key) {
  const current = stepOrder[caseStore.currentCase?.status] ?? -1
  return stepOrder[key] < current
}

onMounted(async () => {
  await caseStore.fetchCase(caseId.value)
  await Promise.all([
    caseStore.fetchMessages(caseId.value),
    caseStore.fetchDocuments(caseId.value),
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
  // Optimistic UI: add user message immediately
  caseStore.messages.push({
    id: 'temp-' + Date.now(),
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  })
  nextTick(scrollToBottom)
  await caseStore.sendMessage(caseId.value, text)
  // Refresh documents in case status changed to form_generation
  await caseStore.fetchDocuments(caseId.value)
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

function probabilityClass(p) {
  if (p >= 0.6) return 'prob-high'
  if (p >= 0.3) return 'prob-medium'
  return 'prob-low'
}
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
  filter: brightness(0) invert(1);
  border-radius: 0;
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
</style>
