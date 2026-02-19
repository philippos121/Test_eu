<template>
  <div class="page">
    <div class="container">

      <div class="page-header fade-in">
        <div>
          <router-link to="/admin" class="back-link">&larr; Admin Dashboard</router-link>
          <h1>Neuronales Netz — Training & Analyse</h1>
          <p class="text-secondary" style="font-size:0.85rem">
            Feedforward-NN (20 Features → 16 → 8 → 1, Sigmoid) · Adam-Optimierer · Binary Cross-Entropy
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
          <div class="stat-value success">{{ dataSummary.n_success ?? '—' }}</div>
          <div class="stat-label">Erfolgreich</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value danger">{{ dataSummary.n_failure ?? '—' }}</div>
          <div class="stat-label">Nicht erfolgreich</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value">{{ dataSummary.n_features ?? 20 }}</div>
          <div class="stat-label">Input-Features</div>
        </div>
        <div class="stat-card card">
          <div class="stat-value">{{ dataSummary.blend_weight != null ? (dataSummary.blend_weight * 100).toFixed(0) + '%' : '—' }}</div>
          <div class="stat-label">Aktuelles NN-Gewicht</div>
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
            <span class="meta-label">Epochs</span>
            <span class="meta-val">{{ model.hyperparams?.epochs ?? '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">LR</span>
            <span class="meta-val">{{ model.hyperparams?.lr ?? '—' }}</span>
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
        <h3 class="section-title">Training starten</h3>
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
            {{ training ? 'Training läuft…' : 'Jetzt trainieren' }}
          </button>
        </div>
        <p v-if="trainMsg" class="train-msg mt-1" :class="trainError ? 'text-danger' : 'text-secondary'">{{ trainMsg }}</p>
        <!-- live loss bar while training -->
        <div v-if="training" class="progress-bar mt-1">
          <div class="progress-fill" :style="{ width: trainProgress + '%' }"></div>
        </div>
      </div>

      <!-- Training history (loss curve) -->
      <div class="card fade-in mt-2" v-if="model?.training_history?.length">
        <h3 class="section-title">Trainings-Verlauf (Loss)</h3>
        <div class="loss-chart">
          <div
            v-for="(h, i) in model.training_history"
            :key="i"
            class="loss-bar-group"
            :title="`Epoche ${h.epoch} | Train-Loss: ${h.train_loss} | Val-Loss: ${h.val_loss} | Val-Acc: ${(h.val_acc*100).toFixed(0)}%`"
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
        </div>
      </div>

      <!-- Feature importance -->
      <div class="card fade-in mt-2" v-if="model?.feature_importance?.length">
        <h3 class="section-title">Feature-Wichtigkeit (Ø |W₀| pro Input-Feature)</h3>
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

      <!-- Per-case predictions -->
      <div class="card fade-in mt-2 mb-3" v-if="predictions.length">
        <h3 class="section-title">NN-Vorhersagen auf Trainingsdaten</h3>
        <p class="text-secondary" style="font-size:0.82rem;margin-bottom:12px">
          Schwellwert ≥ 50% = Erfolg. Grün = korrekte Vorhersage, Rot = falsch.
        </p>
        <table class="pred-table">
          <thead>
            <tr>
              <th>Fall</th>
              <th>NN-Vorhersage</th>
              <th>Tatsächliches Ergebnis</th>
              <th>Korrekt?</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in predictions" :key="p.case_id" :class="p.correct ? 'row-correct' : 'row-wrong'">
              <td class="cell-title">{{ p.case_title }}</td>
              <td :class="p.p_nn >= 0.5 ? 'prob-high' : 'prob-low'">{{ (p.p_nn * 100).toFixed(1) }}%</td>
              <td>
                <span :class="['badge', p.actual_outcome >= 0.5 ? 'badge-completed' : 'badge-rejected']">
                  {{ p.actual_outcome >= 0.5 ? 'Erfolg' : 'Misserfolg' }}
                  {{ p.actual_outcome > 0 && p.actual_outcome < 1 ? ' (teilw.)' : '' }}
                </span>
              </td>
              <td>{{ p.correct ? '✓' : '✗' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="text-secondary mt-1" style="font-size:0.8rem">
          Korrekt: {{ predictions.filter(p => p.correct).length }} / {{ predictions.length }}
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

const model       = ref(null)
const dataSummary = ref({})
const predictions = ref([])

const trainReq = ref({ epochs: 300, lr: 0.005, l2: 0.0001, batch_size: 16 })

const lastHistory = computed(() => {
  const h = model.value?.training_history
  return h?.length ? h[h.length - 1] : null
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

const FEATURE_LABELS = {
  log_claim_amount:    'log(Forderungsbetrag)',
  is_cross_border:     'Grenzüberschreitend',
  claimant_is_legal:   'Kläger: jur. Person',
  defendant_is_legal:  'Beklagter: jur. Person',
  has_contract:        'Beweismittel: Vertrag',
  has_delivery:        'Beweismittel: Liefernachweis',
  has_invoice:         'Beweismittel: Rechnung',
  has_dunning:         'Beweismittel: Mahnung',
  evidence_count:      'Beweismittel-Anzahl',
  def_country_de:      'Beklagter: Deutschland',
  def_country_fr:      'Beklagter: Frankreich',
  def_country_it:      'Beklagter: Italien',
  def_country_ee_pl_cz: 'Beklagter: Osteuropa',
  def_country_other_eu: 'Beklagter: Sonstiges EU',
  claim_lt_2000:       'Forderung < 2.000 EUR',
  claim_2k_5k:         'Forderung 2–5 T EUR',
  claim_gt_5k:         'Forderung > 5.000 EUR',
  has_quality_dispute: 'Qualitätsstreit',
  has_insolvency:      'Insolvenz-Hinweis',
  is_services:         'Dienstleistungsvertrag',
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
  training.value   = true
  trainMsg.value   = ''
  trainError.value = false
  trainProgress.value = 0

  // Animate progress bar during training
  const tick = setInterval(() => {
    if (trainProgress.value < 90) trainProgress.value += 2
  }, 300)

  try {
    const { data } = await api.post('/nn/train', trainReq.value)
    trainProgress.value = 100
    if (data.success) {
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
.stat-value.danger  { color: var(--danger); }

/* Model meta */
.model-meta { display: flex; flex-wrap: wrap; gap: 20px; }
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
.meta-val { font-size: 1rem; font-weight: 700; }

/* Train controls */
.train-controls { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 16px; }
.ctrl-group { display: flex; flex-direction: column; gap: 4px; font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.train-btn { align-self: flex-end; min-width: 150px; }
.train-msg { font-size: 0.82rem; }
.text-danger { color: var(--danger); }

/* Progress bar */
.progress-bar { height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--primary); border-radius: 3px; transition: width 0.3s ease; }

/* Loss chart */
.loss-chart {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 90px;
  padding: 8px 0;
  overflow-x: auto;
  background: #fafafa;
  border-radius: 6px;
  padding: 8px;
}
.loss-bar-group { display: flex; gap: 1px; align-items: flex-end; cursor: pointer; }
.loss-bar { width: 6px; border-radius: 2px 2px 0 0; transition: height 0.3s; }
.train-bar { background: var(--primary); opacity: 0.85; }
.val-bar   { background: var(--warning); opacity: 0.85; }
.chart-legend { display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--text-secondary); margin-top: 8px; }
.legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.acc-summary { font-size: 0.82rem; color: var(--text-secondary); }

/* Feature importance */
.importance-list { display: flex; flex-direction: column; gap: 6px; }
.importance-row { display: flex; align-items: center; gap: 10px; font-size: 0.82rem; }
.importance-rank { width: 24px; text-align: right; font-size: 0.72rem; }
.importance-name { width: 200px; flex-shrink: 0; }
.importance-bar-wrap { flex: 1; height: 14px; background: #f0f0f0; border-radius: 7px; overflow: hidden; }
.importance-bar { height: 100%; border-radius: 7px; transition: width 0.5s ease; }
.bar-top    { background: var(--primary); }
.bar-normal { background: #90caf9; }
.importance-val { width: 60px; text-align: right; font-size: 0.72rem; }

/* Predictions table */
.pred-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.pred-table th {
  text-align: left; padding: 8px 12px;
  border-bottom: 2px solid var(--border);
  font-weight: 600; color: var(--text-secondary);
  font-size: 0.78rem; text-transform: uppercase;
}
.pred-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
.row-correct { background: #f1f8e9; }
.row-wrong   { background: #fce4ec; }
.cell-title { font-weight: 500; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.section-title { font-size: 0.95rem; font-weight: 600; color: var(--primary); margin-bottom: 14px; }

.prob-high { color: var(--success); font-weight: 600; }
.prob-medium { color: var(--warning); font-weight: 600; }
.prob-low { color: var(--danger); font-weight: 600; }
</style>
