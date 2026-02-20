<template>
  <div class="page">
    <div class="container">

      <div class="page-header fade-in">
        <div>
          <router-link to="/admin" class="back-link">&larr; Admin Dashboard</router-link>
          <h1>Neuronales Netz — Training & Analyse</h1>
          <p class="text-secondary" style="font-size:0.85rem">
            Feedforward-NN (40 Features → 32 → 16 → 3, Softmax) · Adam (β₁=0.9, β₂=0.999) · Kategorische Kreuzentropie (CCE)
          </p>
          <p class="server-badge">
            &#x2699;&#xFE0F; Training läuft <strong>serverseitig</strong> in Python/NumPy — nicht im Browser
          </p>
        </div>
      </div>

      <!-- Data Summary -->
      <div class="stats-row fade-in">
        <div class="stat-card card">
          <div class="stat-value">{{ dataSummary.n_labeled_cases ?? '—' }}</div>
          <div class="stat-label">Gelabelte Fälle</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value success">{{ dataSummary.n_class0 ?? '—' }}</div>
          <div class="stat-label">Klasse 0: Vollerfolg</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value warning">{{ dataSummary.n_class1 ?? '—' }}</div>
          <div class="stat-label">Klasse 1: Teilerfolg</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value danger">{{ dataSummary.n_class2 ?? '—' }}</div>
          <div class="stat-label">Klasse 2: Misserfolg</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value">{{ dataSummary.n_features ?? 40 }}</div>
          <div class="stat-label">Input-Features</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value">{{ dataSummary.blend_weight != null ? (dataSummary.blend_weight * 100).toFixed(0) + '%' : '—' }}</div>
          <div class="stat-label">NN-Blend-Gewicht (max 30%)</div>
        </div>
      </div>

      <!-- Model Status -->
      <div class="card fade-in mt-2" v-if="model">
        <h3 class="section-title">Aktives Modell — v{{ model.version }}</h3>
        <div class="model-meta">
          <div class="meta-item">
            <span class="meta-label">Train-Accuracy</span>
            <span :class="['meta-val', accClass(model.train_accuracy)]">{{ pct(model.train_accuracy) }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Val-Accuracy</span>
            <span :class="['meta-val', accClass(model.val_accuracy)]">{{ pct(model.val_accuracy) }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Train-Fälle</span>
            <span class="meta-val">{{ model.n_train_cases }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Val-Fälle</span>
            <span class="meta-val">{{ model.n_val_cases }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Epochen</span>
            <span class="meta-val">{{ model.hyperparams?.epochs ?? '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Lernrate</span>
            <span class="meta-val">{{ model.hyperparams?.lr ?? '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Architektur</span>
            <span class="meta-val" style="font-size:0.8rem">40→32→16→3 Softmax</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Trainiert</span>
            <span class="meta-val text-secondary" style="font-size:0.78rem">{{ fmtDate(model.created_at) }}</span>
          </div>
        </div>
      </div>
      <div class="card fade-in mt-2" v-else-if="!loading">
        <p class="text-secondary text-center">Noch kein Modell trainiert. Führe das erste Training durch.</p>
      </div>

      <!-- Training controls -->
      <div class="card fade-in mt-2">
        <h3 class="section-title">Training starten (Serverseitig · Python/NumPy)</h3>
        <p class="text-secondary" style="font-size:0.82rem;margin-bottom:12px">
          Adam-Optimizer aktualisiert Gewichte W₁(40×32), b₁(32), W₂(32×16), b₂(16), W₃(16×3), b₃(3) per Mini-Batch.
          Gradient: dZ = (ŷ − y_true) / m. L2-Regularisierung schützt vor Overfitting.
        </p>
        <div class="train-controls">
          <div class="ctrl-group">
            <label>Epochen</label>
            <input v-model.number="trainReq.epochs" type="number" min="50" max="2000" step="50" class="form-control" style="width:100px" />
          </div>
          <div class="ctrl-group">
            <label>Lernrate</label>
            <select v-model.number="trainReq.lr" class="form-control" style="width:110px">
              <option :value="0.01">0.010</option>
              <option :value="0.005">0.005</option>
              <option :value="0.002">0.002</option>
              <option :value="0.001">0.001</option>
            </select>
          </div>
          <div class="ctrl-group">
            <label>Batch-Größe</label>
            <select v-model.number="trainReq.batch_size" class="form-control" style="width:90px">
              <option :value="8">8</option>
              <option :value="16">16</option>
              <option :value="32">32</option>
            </select>
          </div>
          <div class="ctrl-group">
            <label>L2-Reg.</label>
            <select v-model.number="trainReq.l2" class="form-control" style="width:110px">
              <option :value="0.0001">0.0001</option>
              <option :value="0.001">0.001</option>
              <option :value="0.01">0.010</option>
            </select>
          </div>
          <button class="btn btn-primary train-btn" :disabled="training" @click="startTraining">
            {{ training ? 'Training läuft auf Server…' : 'Jetzt trainieren' }}
          </button>
        </div>
        <p v-if="trainMsg" class="train-msg mt-1" :class="trainError ? 'text-danger' : 'text-secondary'">{{ trainMsg }}</p>
        <!-- Progress bar during training -->
        <div v-if="training" class="progress-bar mt-1">
          <div class="progress-fill" :style="{ width: trainProgress + '%' }"></div>
        </div>
        <!-- Last training detail (epoch log) -->
        <div v-if="lastTrainResult" class="train-detail mt-2">
          <div class="train-detail-header">Letztes Training — Serverergebnis</div>
          <div class="train-detail-grid">
            <div><span class="tl">Version</span><span class="tv">v{{ lastTrainResult.version }}</span></div>
            <div><span class="tl">Trainingsfälle</span><span class="tv">{{ lastTrainResult.n_train_cases }}</span></div>
            <div><span class="tl">Validierungsfälle</span><span class="tv">{{ lastTrainResult.n_val_cases }}</span></div>
            <div><span class="tl">Train-Accuracy</span><span :class="['tv', accClass(lastTrainResult.train_accuracy)]">{{ pct(lastTrainResult.train_accuracy) }}</span></div>
            <div><span class="tl">Val-Accuracy</span><span :class="['tv', accClass(lastTrainResult.val_accuracy)]">{{ pct(lastTrainResult.val_accuracy) }}</span></div>
          </div>
        </div>
      </div>

      <!-- Training history (loss curve) -->
      <div class="card fade-in mt-2" v-if="model?.training_history?.length">
        <h3 class="section-title">Loss-Verlauf über Epochen (CCE, 3 Klassen)</h3>
        <p class="text-secondary" style="font-size:0.78rem;margin-bottom:8px">
          Jeder Balken = 20 Epochen. Blau = Train-Loss, Orange = Val-Loss. Adam aktualisiert 6 Gewichtsmatrizen/Vektoren je Epoche.
        </p>
        <div class="loss-chart">
          <div
            v-for="(h, i) in model.training_history"
            :key="i"
            class="loss-bar-group"
            :title="`Epoche ${h.epoch} | Train-Loss: ${h.train_loss} | Val-Loss: ${h.val_loss} | Train-Acc: ${(h.train_acc*100).toFixed(0)}% | Val-Acc: ${(h.val_acc*100).toFixed(0)}%`"
          >
            <div class="loss-bar train-bar" :style="{ height: lossToHeight(h.train_loss) + 'px' }"></div>
            <div class="loss-bar val-bar"   :style="{ height: lossToHeight(h.val_loss)   + 'px' }"></div>
          </div>
        </div>
        <div class="chart-legend">
          <span class="legend-dot" style="background:var(--primary)"></span> Train-Loss &nbsp;
          <span class="legend-dot" style="background:var(--warning)"></span> Val-Loss
        </div>
        <div class="acc-summary mt-1">
          Finale Val-Accuracy:
          <strong :class="accClass(lastHistory?.val_acc)">{{ pct(lastHistory?.val_acc) }}</strong>
          &nbsp;·&nbsp; Train-Accuracy:
          <strong :class="accClass(lastHistory?.train_acc)">{{ pct(lastHistory?.train_acc) }}</strong>
          &nbsp;·&nbsp; Startloss (Epoche 1):
          <strong class="text-secondary">{{ model.training_history[0]?.train_loss?.toFixed(3) }}</strong>
          &nbsp;→&nbsp; Endloss:
          <strong class="text-secondary">{{ lastHistory?.train_loss?.toFixed(3) }}</strong>
        </div>
        <!-- Epoch table (first 5 + last 3) -->
        <div class="epoch-table-wrap mt-2">
          <table class="epoch-table">
            <thead>
              <tr>
                <th>Epoche</th>
                <th>Train-Loss</th>
                <th>Val-Loss</th>
                <th>Train-Acc</th>
                <th>Val-Acc</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="h in epochTableRows" :key="h.epoch">
                <td>{{ h.epoch }}</td>
                <td>{{ h.train_loss.toFixed(4) }}</td>
                <td>{{ h.val_loss.toFixed(4) }}</td>
                <td :class="accClass(h.train_acc)">{{ pct(h.train_acc) }}</td>
                <td :class="accClass(h.val_acc)">{{ pct(h.val_acc) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Feature importance -->
      <div class="card fade-in mt-2" v-if="model?.feature_importance?.length">
        <h3 class="section-title">Feature-Wichtigkeit (Ø |W₁| pro Input-Feature)</h3>
        <p class="text-secondary" style="font-size:0.78rem;margin-bottom:8px">
          Gemittelte absolute Gewichte der ersten Layer-Matrix W₁ (40×32). Hohe Werte = starker Einfluss auf Vorhersage.
        </p>
        <div class="importance-list">
          <div
            v-for="(f, i) in model.feature_importance"
            :key="f.name"
            class="importance-row"
          >
            <div class="importance-rank text-secondary">{{ i + 1 }}</div>
            <div class="importance-name">{{ featureLabel(f.name) }}</div>
            <div class="importance-bar-wrap">
              <div
                class="importance-bar"
                :style="{ width: importanceWidth(f.importance) + '%' }"
                :class="i < 3 ? 'bar-top' : 'bar-normal'"
              ></div>
            </div>
            <div class="importance-val text-secondary">{{ f.importance.toFixed(4) }}</div>
          </div>
        </div>
      </div>

      <!-- Per-case predictions (3-class) -->
      <div class="card fade-in mt-2 mb-3" v-if="predictions.length">
        <h3 class="section-title">NN-Vorhersagen auf Trainingsdaten (3-Klassen)</h3>
        <p class="text-secondary" style="font-size:0.82rem;margin-bottom:12px">
          Klassen: 0 = Vollerfolg · 1 = Teilerfolg · 2 = Misserfolg. Grün = korrekte Klasse vorhergesagt.
          p_NN = P[0] + 0.5 × P[1] (gewichtete Erholungswahrscheinlichkeit).
        </p>
        <table class="pred-table">
          <thead>
            <tr>
              <th>Fall</th>
              <th>p_NN</th>
              <th>P[Voll]</th>
              <th>P[Teil]</th>
              <th>P[Miss]</th>
              <th>Vorhergesagt</th>
              <th>Tatsächlich</th>
              <th>✓?</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in predictions" :key="p.case_id" :class="p.correct ? 'row-correct' : 'row-wrong'">
              <td class="cell-title">{{ p.case_title }}</td>
              <td :class="p.p_nn >= 0.5 ? 'prob-high' : 'prob-low'">{{ (p.p_nn * 100).toFixed(1) }}%</td>
              <td class="prob-high">{{ (p.p_full * 100).toFixed(0) }}%</td>
              <td class="prob-medium">{{ (p.p_partial * 100).toFixed(0) }}%</td>
              <td class="prob-low">{{ (p.p_failure * 100).toFixed(0) }}%</td>
              <td>
                <span :class="['badge', classColor(p.predicted_class)]">{{ p.predicted_label }}</span>
              </td>
              <td>
                <span :class="['badge', classColor(p.actual_class)]">{{ p.actual_label }}</span>
              </td>
              <td>{{ p.correct ? '✓' : '✗' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="text-secondary mt-1" style="font-size:0.8rem">
          Korrekt: {{ predictions.filter(p => p.correct).length }} / {{ predictions.length }}
          ({{ predictions.length ? (predictions.filter(p => p.correct).length / predictions.length * 100).toFixed(0) : 0 }}%)
        </p>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../services/api'

const loading     = ref(false)
const training    = ref(false)
const trainMsg    = ref('')
const trainError  = ref(false)
const trainProgress = ref(0)

const model          = ref(null)
const dataSummary    = ref({})
const predictions    = ref([])
const lastTrainResult = ref(null)

const trainReq = ref({ epochs: 300, lr: 0.005, l2: 0.0001, batch_size: 16 })

const lastHistory = computed(() => {
  const h = model.value?.training_history
  return h?.length ? h[h.length - 1] : null
})

const epochTableRows = computed(() => {
  const h = model.value?.training_history
  if (!h?.length) return []
  const first = h.slice(0, 5)
  const last  = h.slice(-3).filter(r => !first.some(f => f.epoch === r.epoch))
  return [...first, ...last]
})

const maxImportance = computed(() => {
  if (!model.value?.feature_importance?.length) return 1
  return Math.max(...model.value.feature_importance.map(f => f.importance))
})

function importanceWidth(val) {
  return maxImportance.value > 0 ? (val / maxImportance.value) * 100 : 0
}

const maxLoss = computed(() => {
  if (!model.value?.training_history?.length) return 1
  return Math.max(...model.value.training_history.flatMap(h => [h.train_loss, h.val_loss]))
})

function lossToHeight(val) {
  const max = maxLoss.value || 1
  return Math.max(2, Math.round((val / max) * 80))
}

function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '—' }
function fmtDate(d) {
  return new Date(d).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function accClass(a) {
  if (a == null) return ''
  if (a >= 0.75) return 'prob-high'
  if (a >= 0.60) return 'prob-medium'
  return 'prob-low'
}
function classColor(cls) {
  if (cls === 0) return 'badge-completed'
  if (cls === 1) return 'badge-partial'
  return 'badge-rejected'
}

const FEATURE_LABELS = {
  log_claim_amount:         'log(Forderungsbetrag)',
  claim_type_zahlung:       'Anspruchstyp: Zahlung',
  claim_type_herausgabe:    'Anspruchstyp: Herausgabe',
  claim_type_schadenersatz: 'Anspruchstyp: Schadensersatz',
  rechtsgrund_vertrag:      'Rechtsgrund: Vertrag',
  rechtsgrund_delikt:       'Rechtsgrund: Delikt',
  claimant_is_legal:        'Kläger: jur. Person',
  defendant_is_legal:       'Beklagter: jur. Person',
  is_b2b:                   'B2B (beide jur. Personen)',
  is_b2c:                   'B2C (Kläger jur., Bekl. nat.)',
  is_cross_border:          'Grenzüberschreitend',
  claimant_dach:            'Kläger: DACH',
  claimant_fr_be_lu:        'Kläger: FR/BE/LU',
  claimant_it_es_pt:        'Kläger: IT/ES/PT',
  claimant_eastern_eu:      'Kläger: Osteuropa',
  defendant_de_at:          'Beklagter: DE/AT',
  defendant_fr_be:          'Beklagter: FR/BE',
  defendant_it_es_pt:       'Beklagter: IT/ES/PT',
  defendant_eastern_eu:     'Beklagter: Osteuropa',
  defendant_other_eu:       'Beklagter: Sonstiges EU',
  year_norm:                'Jahr (normalisiert)',
  quarter_h1:               'Quartal H1 (Q1/Q2)',
  quarter_q4:               'Quartal Q4',
  has_contract:             'Beweismittel: Vertrag',
  has_delivery_proof:       'Beweismittel: Liefernachweis',
  has_invoice:              'Beweismittel: Rechnung',
  has_dunning:              'Beweismittel: Mahnung',
  has_jurisdiction_agr:     'Gerichtsstandsvereinbarung',
  has_insolvency:           'Insolvenzrisiko',
  has_quality_dispute:      'Qualitätsstreit / Mängel',
  defense_no_contract:      'Einw.: kein Vertrag',
  defense_not_fulfilled:    'Einw.: nicht erfüllt',
  defense_defective:        'Einw.: mangelhaft',
  defense_irrtum:           'Einw.: Irrtum',
  defense_no_damage:        'Einw.: kein Schaden',
  defense_no_causation:     'Einw.: keine Kausalität',
  defense_no_fault:         'Einw.: kein Verschulden',
  defense_verjährung:       'Einw.: Verjährung',
  defense_set_off:          'Einw.: Aufrechnung',
  is_services:              'Dienstleistungsvertrag',
}
function featureLabel(name) { return FEATURE_LABELS[name] || name }

async function load() {
  loading.value = true
  try {
    const [statusRes, summaryRes, predRes] = await Promise.all([
      api.get('/nn/status').catch(() => ({ data: null })),
      api.get('/nn/data-summary').catch(() => ({ data: {} })),
      api.get('/nn/predictions').catch(() => ({ data: [] })),
    ])
    model.value       = statusRes.data
    dataSummary.value = summaryRes.data
    predictions.value = predRes.data
  } finally {
    loading.value = false
  }
}

async function startTraining() {
  training.value    = true
  trainMsg.value    = ''
  trainError.value  = false
  trainProgress.value = 0
  lastTrainResult.value = null

  // Animate progress bar: simulates epoch progress during server-side training
  const tick = setInterval(() => {
    if (trainProgress.value < 90) trainProgress.value += 2
  }, 300)

  try {
    const { data } = await api.post('/nn/train', trainReq.value)
    trainProgress.value = 100
    if (data.success) {
      lastTrainResult.value = data
      trainMsg.value = `✓ ${data.message} | Train-Acc: ${(data.train_accuracy * 100).toFixed(1)}% | Val-Acc: ${(data.val_accuracy * 100).toFixed(1)}%`
    } else {
      trainMsg.value = data.message
      trainError.value = true
    }
    await load()
  } catch (e) {
    trainMsg.value = 'Fehler: ' + (e.response?.data?.detail || e.message)
    trainError.value = true
  } finally {
    clearInterval(tick)
    training.value = false
    setTimeout(() => { trainProgress.value = 0 }, 1000)
  }
}

onMounted(load)
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
.page-header h1 { font-size: 1.3rem; margin: 4px 0; }
.back-link { font-size: 0.85rem; color: var(--text-secondary); }
.back-link:hover { color: var(--primary); text-decoration: none; }

.server-badge {
  display: inline-block;
  margin-top: 6px;
  font-size: 0.8rem;
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
  color: #2e7d32;
  border-radius: 4px;
  padding: 3px 10px;
}

/* Stats row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 0;
}
.stat-card { text-align: center; padding: 16px 12px; }
.stat-value { font-size: 1.8rem; font-weight: 800; color: var(--primary); }
.stat-label { font-size: 0.78rem; color: var(--text-secondary); margin-top: 4px; }
.stat-value.success { color: var(--success); }
.stat-value.warning { color: var(--warning, #f59e0b); }
.stat-value.danger  { color: var(--danger); }

/* Model meta */
.model-meta { display: flex; flex-wrap: wrap; gap: 20px; }
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
.meta-val { font-size: 1rem; font-weight: 700; }

/* Train controls */
.train-controls { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 16px; }
.ctrl-group { display: flex; flex-direction: column; gap: 4px; font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.train-btn { align-self: flex-end; min-width: 180px; }
.train-msg { font-size: 0.82rem; }
.text-danger { color: var(--danger); }

/* Progress bar */
.progress-bar { height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--primary); border-radius: 3px; transition: width 0.3s ease; }

/* Train detail */
.train-detail { background: #f8f9fa; border-radius: 6px; padding: 12px 16px; }
.train-detail-header { font-size: 0.8rem; font-weight: 600; color: var(--primary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.train-detail-grid { display: flex; flex-wrap: wrap; gap: 16px; }
.train-detail-grid > div { display: flex; flex-direction: column; gap: 2px; }
.tl { font-size: 0.7rem; color: var(--text-secondary); }
.tv { font-size: 0.95rem; font-weight: 700; }

/* Loss chart */
.loss-chart {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 90px;
  overflow-x: auto;
  background: #fafafa;
  border-radius: 6px;
  padding: 8px;
}
.loss-bar-group { display: flex; gap: 1px; align-items: flex-end; cursor: pointer; }
.loss-bar { width: 6px; border-radius: 2px 2px 0 0; transition: height 0.3s; }
.train-bar { background: var(--primary); opacity: 0.85; }
.val-bar   { background: var(--warning, #f59e0b); opacity: 0.85; }
.chart-legend { display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--text-secondary); margin-top: 8px; }
.legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.acc-summary { font-size: 0.82rem; color: var(--text-secondary); }

/* Epoch table */
.epoch-table-wrap { overflow-x: auto; }
.epoch-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.epoch-table th {
  text-align: left; padding: 6px 10px;
  border-bottom: 2px solid var(--border);
  font-weight: 600; color: var(--text-secondary); font-size: 0.72rem; text-transform: uppercase;
}
.epoch-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); }

/* Feature importance */
.importance-list { display: flex; flex-direction: column; gap: 6px; }
.importance-row { display: flex; align-items: center; gap: 10px; font-size: 0.82rem; }
.importance-rank { width: 24px; text-align: right; font-size: 0.72rem; }
.importance-name { width: 220px; flex-shrink: 0; }
.importance-bar-wrap { flex: 1; height: 14px; background: #f0f0f0; border-radius: 7px; overflow: hidden; }
.importance-bar { height: 100%; border-radius: 7px; transition: width 0.5s ease; }
.bar-top    { background: var(--primary); }
.bar-normal { background: #90caf9; }
.importance-val { width: 60px; text-align: right; font-size: 0.72rem; }

/* Predictions table */
.pred-table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
.pred-table th {
  text-align: left; padding: 8px 10px;
  border-bottom: 2px solid var(--border);
  font-weight: 600; color: var(--text-secondary);
  font-size: 0.75rem; text-transform: uppercase;
}
.pred-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
.row-correct { background: #f1f8e9; }
.row-wrong   { background: #fce4ec; }
.cell-title { font-weight: 500; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.badge-partial { background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; }

.section-title { font-size: 0.95rem; font-weight: 600; color: var(--primary); margin-bottom: 14px; }

.prob-high   { color: var(--success); font-weight: 600; }
.prob-medium { color: var(--warning, #f59e0b); font-weight: 600; }
.prob-low    { color: var(--danger); font-weight: 600; }
</style>
