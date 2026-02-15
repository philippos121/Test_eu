<template>
  <div class="page">
    <div class="container">
      <div class="page-header fade-in">
        <div>
          <router-link to="/admin" class="back-link">&larr; Admin Dashboard</router-link>
          <h1>Priors Konfiguration</h1>
          <p class="text-secondary">Beta-Verteilung (&alpha;, &beta;) pro Rate, Claim-Subtype und Land</p>
        </div>
        <button class="btn btn-primary" @click="openCreate">+ Neuer Prior</button>
      </div>

      <!-- Defaults info -->
      <div class="card fade-in mb-2">
        <h3 class="section-title">Standard-Priors (Fallback)</h3>
        <p class="text-secondary" style="font-size:0.82rem;margin-bottom:12px">
          Diese Werte gelten, wenn kein spezifischer Prior konfiguriert ist:
        </p>
        <table class="priors-table">
          <thead>
            <tr>
              <th>Rate</th>
              <th>&alpha;</th>
              <th>&beta;</th>
              <th>E[p] = &alpha;/(&alpha;+&beta;)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in defaults" :key="d.name">
              <td class="rate-name">{{ d.name }}</td>
              <td>{{ d.alpha }}</td>
              <td>{{ d.beta }}</td>
              <td class="prob-val">{{ ((d.alpha / (d.alpha + d.beta)) * 100).toFixed(0) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Configured priors -->
      <div class="card fade-in">
        <h3 class="section-title">Konfigurierte Priors</h3>
        <div v-if="!store.priors.length" class="text-secondary">
          Keine individuellen Priors konfiguriert. Es gelten die Standardwerte.
        </div>
        <table v-else class="priors-table">
          <thead>
            <tr>
              <th>Rate</th>
              <th>Subtype</th>
              <th>Land</th>
              <th>&alpha;</th>
              <th>&beta;</th>
              <th>E[p]</th>
              <th>Aktionen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in store.priors" :key="p.id">
              <td class="rate-name">{{ p.rate_name }}</td>
              <td>{{ p.claim_subtype }}</td>
              <td>{{ p.country }}</td>
              <td>{{ p.alpha }}</td>
              <td>{{ p.beta }}</td>
              <td class="prob-val">{{ ((p.alpha / (p.alpha + p.beta)) * 100).toFixed(1) }}%</td>
              <td>
                <button class="btn btn-sm btn-outline" @click="openEdit(p)">Bearbeiten</button>
                <button class="btn btn-sm btn-danger" @click="handleDelete(p.id)">X</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Create/Edit Modal -->
      <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
        <div class="modal-box card">
          <h3>{{ editing ? 'Prior bearbeiten' : 'Neuer Prior' }}</h3>
          <div class="form-group">
            <label>Rate</label>
            <select v-model="form.rate_name" class="form-control" :disabled="editing">
              <option value="served">served (Zustellung)</option>
              <option value="default">default (Versäumnis)</option>
              <option value="settle">settle (Vergleich)</option>
              <option value="collect">collect (Inkasso)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Claim Subtype</label>
            <input v-model="form.claim_subtype" class="form-control" placeholder="general" />
          </div>
          <div class="form-group">
            <label>Land (ISO 2, oder * für alle)</label>
            <input v-model="form.country" class="form-control" maxlength="2" placeholder="*" />
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>&alpha;</label>
              <input v-model.number="form.alpha" type="number" step="0.1" min="0.1" class="form-control" />
            </div>
            <div class="form-group">
              <label>&beta;</label>
              <input v-model.number="form.beta" type="number" step="0.1" min="0.1" class="form-control" />
            </div>
          </div>
          <div class="preview-line text-secondary">
            Erwartungswert: {{ form.alpha && form.beta ? ((form.alpha / (form.alpha + form.beta)) * 100).toFixed(1) : '—' }}%
          </div>
          <div v-if="formError" class="error-text mb-1">{{ formError }}</div>
          <div class="form-actions">
            <button class="btn btn-outline" @click="showModal = false">Abbrechen</button>
            <button class="btn btn-primary" @click="handleSave">Speichern</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAdminStore } from '../stores/admin'

const store = useAdminStore()

const showModal = ref(false)
const editing = ref(null) // prior id or null
const formError = ref('')
const form = ref({ rate_name: 'served', claim_subtype: 'general', country: '*', alpha: 2.0, beta: 2.0 })

const defaults = [
  { name: 'served', alpha: 8, beta: 2 },
  { name: 'default', alpha: 5, beta: 5 },
  { name: 'settle', alpha: 2, beta: 8 },
  { name: 'collect', alpha: 6, beta: 4 },
]

function openCreate() {
  editing.value = null
  form.value = { rate_name: 'served', claim_subtype: 'general', country: '*', alpha: 2.0, beta: 2.0 }
  formError.value = ''
  showModal.value = true
}

function openEdit(p) {
  editing.value = p.id
  form.value = { rate_name: p.rate_name, claim_subtype: p.claim_subtype, country: p.country, alpha: p.alpha, beta: p.beta }
  formError.value = ''
  showModal.value = true
}

async function handleSave() {
  formError.value = ''
  if (form.value.alpha <= 0 || form.value.beta <= 0) {
    formError.value = 'Alpha und Beta müssen > 0 sein.'
    return
  }
  try {
    if (editing.value) {
      await store.updatePrior(editing.value, { alpha: form.value.alpha, beta: form.value.beta, claim_subtype: form.value.claim_subtype, country: form.value.country })
    } else {
      await store.createPrior(form.value)
    }
    showModal.value = false
  } catch (err) {
    formError.value = err.response?.data?.detail || 'Fehler beim Speichern.'
  }
}

async function handleDelete(id) {
  if (!confirm('Prior wirklich löschen?')) return
  await store.deletePrior(id)
}

onMounted(() => store.fetchPriors())
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
.section-title { font-size: 0.95rem; font-weight: 600; color: var(--primary); margin-bottom: 12px; }

.priors-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.priors-table th { text-align: left; padding: 8px 12px; border-bottom: 2px solid var(--border); font-weight: 600; color: var(--text-secondary); font-size: 0.78rem; text-transform: uppercase; }
.priors-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
.rate-name { font-weight: 600; }
.prob-val { font-weight: 600; color: var(--primary); }

.form-row { display: flex; gap: 16px; }
.form-row .form-group { flex: 1; }
.preview-line { font-size: 0.82rem; margin-bottom: 12px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.modal-box { width: 480px; max-width: 90vw; }
.modal-box h3 { margin-bottom: 16px; }
</style>
