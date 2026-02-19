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

      <!-- Bayes Learning Visualization -->
      <section class="card fade-in mt-3" v-if="bayesSteps.length > 0">
        <h2>Bayesian Learning — Lernverlauf</h2>
        <p class="text-secondary mb-2">Wie sich die Wahrscheinlichkeitsschätzung mit jedem Fall ändert.</p>

        <div class="bayes-chart">
          <div class="bayes-chart-header">
            <span class="chart-legend-item"><span class="dot dot-cb"></span> Vertragsbasis</span>
            <span class="chart-legend-item"><span class="dot dot-pf"></span> Leistungserbringung</span>
          </div>
          <div class="bayes-bars">
            <div class="bayes-bar-group" v-for="step in contractBasisSteps" :key="'cb-' + step.step">
              <div class="bar-label">Fall {{ step.step }}</div>
              <div class="bar-container">
                <div class="bar bar-cb" :style="{ width: (step.mean * 100) + '%' }"
                     :title="'Mean: ' + (step.mean * 100).toFixed(1) + '%'">
                  {{ (step.mean * 100).toFixed(0) }}%
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

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
            <tr v-for="p in stats.posteriors" :key="p.name">
              <td class="font-semibold">{{ p.label }}</td>
              <td>{{ p.prior_alpha.toFixed(1) }}, {{ p.prior_beta.toFixed(1) }}</td>
              <td>{{ p.successes }} / {{ p.trials }}</td>
              <td>{{ p.post_alpha.toFixed(1) }}, {{ p.post_beta.toFixed(1) }}</td>
              <td class="font-semibold">{{ (p.mean * 100).toFixed(1) }}%</td>
              <td>{{ (p.ci_low * 100).toFixed(0) }}% – {{ (p.ci_high * 100).toFixed(0) }}%</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Filter + Search for Cases Table -->
      <section class="card fade-in mt-3">
        <div class="section-header">
          <h2>Alle Fälle ({{ filteredCases.length }})</h2>
          <div class="filter-row">
            <input type="text" v-model="searchTerm" placeholder="Suche..." class="search-input" />
            <select v-model="outcomeFilter" class="filter-select">
              <option value="">Alle Ergebnisse</option>
              <option value="won">Gewonnen</option>
              <option value="lost">Verloren</option>
              <option value="settled">Verglichen</option>
              <option value="withdrawn">Zurückgezogen</option>
            </select>
            <select v-model="sortField" class="filter-select">
              <option value="title">Nach Titel</option>
              <option value="p_obsiegen">Nach p_obsiegen</option>
              <option value="p_recht">Nach p_recht</option>
              <option value="p_beweis">Nach p_beweis</option>
              <option value="amount">Nach Betrag</option>
              <option value="ev">Nach EV</option>
            </select>
          </div>
        </div>

        <!-- Cases Table -->
        <div class="cases-table-wrap">
          <table class="data-table cases-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Fall</th>
                <th>Land</th>
                <th>Betrag</th>
                <th>p<sub>recht</sub></th>
                <th>p<sub>beweis</sub></th>
                <th>p<sub>obsiegen</sub></th>
                <th>EV</th>
                <th>Ergebnis</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(c, idx) in paginatedCases" :key="c.id"
                  class="case-row clickable"
                  :class="{ 'row-success': c.outcome_success, 'row-fail': !c.outcome_success, 'row-test': c.is_test, 'row-real': !c.is_seed }"
                  @click="openDetail(c)">
                <td>{{ (currentPage - 1) * pageSize + idx + 1 }}</td>
                <td class="case-title-cell">
                  <span v-if="c.is_test" class="badge badge-test">TEST</span>
                  <span v-else-if="!c.is_seed" class="badge badge-real">ECHT</span>
                  {{ c.title }}
                </td>
                <td>{{ c.claimant_country }} → {{ c.defendant_country }}</td>
                <td>{{ c.claim_amount?.toFixed(0) ?? '—' }} EUR</td>
                <td>
                  <span class="prob-pill" :class="probClass(c.pipeline?.p_recht)">
                    {{ c.pipeline ? (c.pipeline.p_recht * 100).toFixed(0) + '%' : '—' }}
                  </span>
                </td>
                <td>
                  <span class="prob-pill" :class="probClass(c.pipeline?.p_beweis)">
                    {{ c.pipeline ? (c.pipeline.p_beweis * 100).toFixed(0) + '%' : '—' }}
                  </span>
                </td>
                <td>
                  <span class="prob-pill" :class="probClass(c.pipeline?.p_obsiegen)">
                    {{ c.pipeline ? (c.pipeline.p_obsiegen * 100).toFixed(0) + '%' : '—' }}
                  </span>
                </td>
                <td :class="c.pipeline?.ev_betreiber >= 0 ? 'success' : 'danger'">
                  {{ c.pipeline?.ev_betreiber != null ? c.pipeline.ev_betreiber.toFixed(0) : '—' }}
                </td>
                <td>
                  <span class="outcome-badge" :class="'outcome-' + c.outcome">
                    {{ outcomeLabel(c.outcome) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="pagination" v-if="totalPages > 1">
          <button @click="currentPage = 1" :disabled="currentPage === 1">&laquo;</button>
          <button @click="currentPage--" :disabled="currentPage === 1">&lsaquo;</button>
          <span class="page-info">Seite {{ currentPage }} von {{ totalPages }}</span>
          <button @click="currentPage++" :disabled="currentPage === totalPages">&rsaquo;</button>
          <button @click="currentPage = totalPages" :disabled="currentPage === totalPages">&raquo;</button>
        </div>
      </section>

      <!-- Test Case Form -->
      <section class="card fade-in mt-3">
        <h2>Neuen Testfall anlegen</h2>
        <p class="text-secondary mb-2">
          Erstellen Sie einen eigenen Testfall mit benutzerdefinierten Werten,
          um zu prüfen, wie sich die Wahrscheinlichkeitsberechnung ändert.
        </p>

        <form @submit.prevent="submitTestCase" class="test-form">
          <div class="form-grid">
            <div class="form-group">
              <label>Titel</label>
              <input v-model="testForm.title" type="text" placeholder="z.B. Warenlieferung DE→AT" />
            </div>
            <div class="form-group">
              <label>Klageart</label>
              <select v-model="testForm.claim_type">
                <option value="invoice">Rechnung / Warenlieferung</option>
                <option value="werklohn">Werkvertrag / Dienstleistung</option>
                <option value="refund">Rückforderung</option>
                <option value="damages">Schadensersatz</option>
                <option value="unjust_enrichment">Ungerechtfertigte Bereicherung</option>
                <option value="other">Sonstige</option>
              </select>
            </div>
            <div class="form-group">
              <label>Kläger</label>
              <input v-model="testForm.claimant_name" type="text" />
            </div>
            <div class="form-group">
              <label>Kläger-Land</label>
              <input v-model="testForm.claimant_country" type="text" maxlength="2" placeholder="DE" />
            </div>
            <div class="form-group">
              <label>Beklagter</label>
              <input v-model="testForm.defendant_name" type="text" />
            </div>
            <div class="form-group">
              <label>Beklagter-Land</label>
              <input v-model="testForm.defendant_country" type="text" maxlength="2" placeholder="DE" />
            </div>
            <div class="form-group">
              <label>Gerichts-Land</label>
              <input v-model="testForm.court_country" type="text" maxlength="2" placeholder="DE" />
            </div>
            <div class="form-group">
              <label>Forderungsbetrag (EUR)</label>
              <input v-model.number="testForm.claim_amount" type="number" min="0" max="5000" step="50" />
            </div>
            <div class="form-group span-2">
              <label>Beschreibung</label>
              <textarea v-model="testForm.description" rows="2" placeholder="Kurze Fallbeschreibung..."></textarea>
            </div>
            <div class="form-group span-2">
              <label>Beweismittel</label>
              <textarea v-model="testForm.evidence_desc" rows="2" placeholder="Welche Beweismittel liegen vor?"></textarea>
            </div>

            <div class="form-group">
              <label>p<sub>recht</sub> (Schlüssigkeit)</label>
              <div class="slider-group">
                <input v-model.number="testForm.p_recht" type="range" min="0" max="1" step="0.05" />
                <span class="slider-value" :class="probClass(testForm.p_recht)">{{ (testForm.p_recht * 100).toFixed(0) }}%</span>
              </div>
            </div>
            <div class="form-group">
              <label>p<sub>beweis</sub> (Beweislage)</label>
              <div class="slider-group">
                <input v-model.number="testForm.p_beweis" type="range" min="0" max="1" step="0.05" />
                <span class="slider-value" :class="probClass(testForm.p_beweis)">{{ (testForm.p_beweis * 100).toFixed(0) }}%</span>
              </div>
            </div>
            <div class="form-group">
              <label>p<sub>eintreibung</sub> (Beitreibbarkeit)</label>
              <div class="slider-group">
                <input v-model.number="testForm.p_eintreibung" type="range" min="0" max="1" step="0.05" />
                <span class="slider-value" :class="probClass(testForm.p_eintreibung)">{{ (testForm.p_eintreibung * 100).toFixed(0) }}%</span>
              </div>
            </div>
            <div class="form-group">
              <label>Ergebnis</label>
              <select v-model="testForm.outcome">
                <option value="won">Gewonnen</option>
                <option value="lost">Verloren</option>
                <option value="settled">Verglichen</option>
                <option value="withdrawn">Zurückgezogen</option>
              </select>
            </div>
          </div>

          <!-- Live Preview -->
          <div class="test-preview mt-2" v-if="testForm.p_recht != null">
            <h3>Vorschau</h3>
            <div class="preview-row">
              <span>p<sub>obsiegen</sub> = {{ (testForm.p_recht * testForm.p_beweis * 100).toFixed(1) }}%</span>
              <span>p<sub>gesamt</sub> = {{ (testForm.p_recht * testForm.p_beweis * testForm.p_eintreibung * 100).toFixed(1) }}%</span>
              <span :class="previewEV >= 0 ? 'success' : 'danger'">EV = {{ previewEV.toFixed(0) }} EUR</span>
              <span :class="testForm.p_recht * testForm.p_beweis >= 0.80 && previewEV > 0 ? 'success' : 'danger'">
                {{ testForm.p_recht * testForm.p_beweis >= 0.80 && previewEV > 0 ? 'Annahme empfohlen' : 'Ablehnung' }}
              </span>
            </div>
          </div>

          <div class="form-actions mt-2">
            <button type="submit" class="btn btn-primary" :disabled="submittingTest">
              {{ submittingTest ? 'Wird erstellt...' : 'Testfall erstellen' }}
            </button>
          </div>

          <div v-if="testResult" class="test-result mt-2">
            <p class="success">Testfall erstellt! Die Statistik wird beim nächsten Laden aktualisiert.</p>
            <button @click="loadStats" class="btn btn-secondary mt-1">Statistik neu laden</button>
          </div>
        </form>
      </section>

      <!-- Admin Actions -->
      <section class="card fade-in mt-3">
        <h2>Administration</h2>
        <div class="admin-actions">
          <button @click="seedData" :disabled="seeding" class="btn btn-primary">
            {{ seeding ? 'Seeding...' : '30 Testfälle neu generieren' }}
          </button>
          <button @click="updatePriors" :disabled="updating" class="btn btn-secondary">
            {{ updating ? 'Aktualisiere...' : 'Priors aktualisieren' }}
          </button>
        </div>
        <p v-if="seedMsg" class="mt-1 text-secondary">{{ seedMsg }}</p>
        <p v-if="updateMsg" class="mt-1 text-secondary">{{ updateMsg }}</p>
      </section>

      <!-- Detail Modal -->
      <div v-if="selectedCase" class="modal-overlay" @click.self="selectedCase = null">
        <div class="modal-content">
          <button class="modal-close" @click="selectedCase = null">&times;</button>

          <h2>{{ selectedCase.title }}</h2>

          <div class="detail-grid">
            <div class="detail-section">
              <h3>Parteien</h3>
              <div class="detail-row">
                <span class="detail-label">Kläger:</span>
                <span>{{ selectedCase.claimant_name }} ({{ selectedCase.claimant_country }})</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Beklagter:</span>
                <span>{{ selectedCase.defendant_name }} ({{ selectedCase.defendant_country }})</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Gericht:</span>
                <span>{{ selectedCase.court_country }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Grenzüberschreitend:</span>
                <span>{{ selectedCase.is_cross_border ? 'Ja' : 'Nein' }}</span>
              </div>
            </div>

            <div class="detail-section">
              <h3>Forderung</h3>
              <div class="detail-row">
                <span class="detail-label">Betrag:</span>
                <span>{{ selectedCase.claim_amount?.toFixed(2) }} {{ selectedCase.claim_currency }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Ergebnis:</span>
                <span class="outcome-badge" :class="'outcome-' + selectedCase.outcome">
                  {{ outcomeLabel(selectedCase.outcome) }}
                </span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Netto-EV:</span>
                <span :class="(selectedCase.net_ev || 0) >= 0 ? 'success' : 'danger'">
                  {{ selectedCase.net_ev?.toFixed(2) ?? '—' }} EUR
                </span>
              </div>
            </div>
          </div>

          <div class="detail-section mt-2" v-if="selectedCase.description">
            <h3>Beschreibung</h3>
            <p>{{ selectedCase.description }}</p>
          </div>

          <div class="detail-section mt-2" v-if="selectedCase.evidence_desc">
            <h3>Beweismittel</h3>
            <p>{{ selectedCase.evidence_desc }}</p>
          </div>

          <div class="detail-section mt-2" v-if="selectedCase.assessment">
            <h3>Bewertung</h3>
            <p>{{ selectedCase.assessment }}</p>
          </div>

          <!-- Pipeline Scores in Detail -->
          <div class="detail-section mt-2" v-if="selectedCase.pipeline">
            <h3>Pipeline v3 — Wahrscheinlichkeiten</h3>
            <div class="pipeline-flow pipeline-detail">
              <div class="pipeline-tier">
                <div class="tier-box tier-recht">
                  <span class="tier-value">{{ (selectedCase.pipeline.p_recht * 100).toFixed(1) }}%</span>
                  <span class="tier-name">p<sub>recht</sub></span>
                </div>
              </div>
              <div class="pipeline-arrow">&times;</div>
              <div class="pipeline-tier">
                <div class="tier-box tier-beweis">
                  <span class="tier-value">{{ (selectedCase.pipeline.p_beweis * 100).toFixed(1) }}%</span>
                  <span class="tier-name">p<sub>beweis</sub></span>
                </div>
              </div>
              <div class="pipeline-arrow">=</div>
              <div class="pipeline-tier">
                <div class="tier-box tier-obsiegen">
                  <span class="tier-value">{{ (selectedCase.pipeline.p_obsiegen * 100).toFixed(1) }}%</span>
                  <span class="tier-name">p<sub>obsiegen</sub></span>
                </div>
              </div>
              <div class="pipeline-arrow">&times;</div>
              <div class="pipeline-tier">
                <div class="tier-box tier-eintreib">
                  <span class="tier-value">{{ selectedCase.pipeline.p_eintreibung != null ? (selectedCase.pipeline.p_eintreibung * 100).toFixed(1) + '%' : '—' }}</span>
                  <span class="tier-name">p<sub>eintreibung</sub></span>
                </div>
              </div>
              <div class="pipeline-arrow">=</div>
              <div class="pipeline-tier">
                <div class="tier-box tier-gesamt">
                  <span class="tier-value">{{ selectedCase.pipeline.p_gesamt != null ? (selectedCase.pipeline.p_gesamt * 100).toFixed(1) + '%' : '—' }}</span>
                  <span class="tier-name">p<sub>gesamt</sub></span>
                </div>
              </div>
            </div>

            <div class="pipeline-ev-row mt-2">
              <div class="ev-card">
                <span class="ev-label">EV<sub>Betreiber</sub></span>
                <span class="ev-value" :class="(selectedCase.pipeline.ev_betreiber || 0) >= 0 ? 'success' : 'danger'">
                  {{ selectedCase.pipeline.ev_betreiber?.toFixed(2) ?? '—' }} EUR
                </span>
              </div>
              <div class="ev-card">
                <span class="ev-label">Fallentscheidung</span>
                <span class="ev-value" :class="selectedCase.pipeline.take_case ? 'success' : 'danger'">
                  {{ selectedCase.pipeline.take_case ? 'Annahme empfohlen' : 'Ablehnung' }}
                </span>
              </div>
            </div>

            <!-- Element Scores -->
            <div class="element-scores mt-2" v-if="Object.keys(selectedCase.pipeline.element_scores || {}).length">
              <h4>Beweiselemente</h4>
              <div class="element-bar-list">
                <div class="element-bar-row" v-for="(val, key) in selectedCase.pipeline.element_scores" :key="key">
                  <span class="element-label">{{ elementLabel(key) }}</span>
                  <div class="element-bar-container">
                    <div class="element-bar" :style="{ width: (val * 100) + '%' }" :class="probClass(val)"></div>
                  </div>
                  <span class="element-value">{{ (val * 100).toFixed(0) }}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18nStore } from '../stores/i18n'
import api from '../services/api'

const { t } = useI18nStore()

// State
const stats = ref({})
const seeding = ref(false)
const updating = ref(false)
const seedMsg = ref('')
const updateMsg = ref('')
const selectedCase = ref(null)
const submittingTest = ref(false)
const testResult = ref(null)

// Filters
const searchTerm = ref('')
const outcomeFilter = ref('')
const sortField = ref('title')
const currentPage = ref(1)
const pageSize = 20

// Test form
const testForm = ref({
  title: '',
  claim_type: 'invoice',
  claimant_name: 'Testkläger GmbH',
  claimant_country: 'DE',
  defendant_name: 'Testbeklagter S.r.l.',
  defendant_country: 'IT',
  court_country: 'DE',
  claim_amount: 2000,
  description: '',
  evidence_desc: '',
  p_recht: 0.7,
  p_beweis: 0.6,
  p_eintreibung: 0.75,
  outcome: 'won',
})

// Computed
const allCases = computed(() => stats.value.completed_cases_detail || [])
const pipelineAgg = computed(() => stats.value.pipeline_aggregates)
const bayesSteps = computed(() => stats.value.bayes_learning_progression || [])
const contractBasisSteps = computed(() => bayesSteps.value.filter(s => s.element === 'contract_basis'))

const filteredCases = computed(() => {
  let cases = [...allCases.value]

  // Search filter
  if (searchTerm.value) {
    const term = searchTerm.value.toLowerCase()
    cases = cases.filter(c =>
      (c.title || '').toLowerCase().includes(term) ||
      (c.description || '').toLowerCase().includes(term) ||
      (c.claimant_name || '').toLowerCase().includes(term) ||
      (c.defendant_name || '').toLowerCase().includes(term) ||
      (c.claimant_country || '').toLowerCase().includes(term) ||
      (c.defendant_country || '').toLowerCase().includes(term)
    )
  }

  // Outcome filter
  if (outcomeFilter.value) {
    cases = cases.filter(c => c.outcome === outcomeFilter.value)
  }

  // Sort
  cases.sort((a, b) => {
    switch (sortField.value) {
      case 'p_obsiegen':
        return (b.pipeline?.p_obsiegen || 0) - (a.pipeline?.p_obsiegen || 0)
      case 'p_recht':
        return (b.pipeline?.p_recht || 0) - (a.pipeline?.p_recht || 0)
      case 'p_beweis':
        return (b.pipeline?.p_beweis || 0) - (a.pipeline?.p_beweis || 0)
      case 'amount':
        return (b.claim_amount || 0) - (a.claim_amount || 0)
      case 'ev':
        return (b.pipeline?.ev_betreiber || -9999) - (a.pipeline?.ev_betreiber || -9999)
      default:
        return (a.title || '').localeCompare(b.title || '')
    }
  })

  return cases
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredCases.value.length / pageSize)))

const paginatedCases = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredCases.value.slice(start, start + pageSize)
})

const previewEV = computed(() => {
  const pObs = testForm.value.p_recht * testForm.value.p_beweis
  const costs = 35 + 75 + 50
  const lossCosts = 200
  if (pObs > 0) {
    return pObs * 0.30 * testForm.value.claim_amount - costs - (1 - pObs) * lossCosts
  }
  return -(costs + lossCosts)
})

// Methods
function probClass(val) {
  if (val == null) return ''
  if (val >= 0.7) return 'prob-high'
  if (val >= 0.4) return 'prob-mid'
  return 'prob-low'
}

function outcomeLabel(outcome) {
  const map = { won: 'Gewonnen', lost: 'Verloren', settled: 'Verglichen', withdrawn: 'Zurückgezogen' }
  return map[outcome] || outcome || '—'
}

function elementLabel(key) {
  const map = {
    contract_basis: 'Vertragsbasis',
    performance: 'Leistung',
    amount_due: 'Forderungshöhe',
    non_payment: 'Nichtzahlung',
  }
  return map[key] || key
}

function openDetail(c) {
  selectedCase.value = c
}

async function loadStats() {
  try {
    const res = await api.get('/api/statistics/overview')
    stats.value = res.data
    testResult.value = null
  } catch (err) {
    console.error('Failed to load statistics', err)
  }
}

async function seedData() {
  seeding.value = true
  seedMsg.value = ''
  try {
    const res = await api.post('/api/statistics/seed')
    seedMsg.value = res.data.message
    await loadStats()
  } catch (err) {
    seedMsg.value = 'Fehler: ' + (err.response?.data?.detail || err.message)
  } finally {
    seeding.value = false
  }
}

async function updatePriors() {
  updating.value = true
  updateMsg.value = ''
  try {
    const res = await api.post('/api/statistics/update-priors')
    const items = res.data.priors || []
    updateMsg.value = items.map(p => `${p.rate_name}: ${(p.posterior_mean * 100).toFixed(1)}%`).join(' | ')
    await loadStats()
  } catch (err) {
    updateMsg.value = 'Fehler: ' + (err.response?.data?.detail || err.message)
  } finally {
    updating.value = false
  }
}

async function submitTestCase() {
  submittingTest.value = true
  testResult.value = null
  try {
    const res = await api.post('/api/statistics/test-case', testForm.value)
    testResult.value = res.data
    await loadStats()
  } catch (err) {
    console.error('Failed to create test case', err)
    testResult.value = { error: err.response?.data?.detail || err.message }
  } finally {
    submittingTest.value = false
  }
}

onMounted(loadStats)
</script>

<style scoped>
.page { padding: 2rem 0; }
.container { max-width: 1200px; margin: 0 auto; padding: 0 1.5rem; }
.mb-2 { margin-bottom: 1rem; }
.mt-1 { margin-top: 0.5rem; }
.mt-2 { margin-top: 1rem; }
.mt-3 { margin-top: 1.5rem; }
.fade-in { animation: fadeIn 0.3s ease-in; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

.card { background: var(--color-bg-card, #fff); border: 1px solid var(--color-border, #e2e8f0); border-radius: 12px; padding: 1.5rem; }
.text-secondary { color: var(--color-text-secondary, #64748b); font-size: 0.9rem; }
.font-semibold { font-weight: 600; }
.success { color: #16a34a; }
.danger { color: #dc2626; }

/* Stats grid */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
.stat-card { text-align: center; }
.stat-value { font-size: 2rem; font-weight: 700; }
.stat-label { font-size: 0.85rem; color: var(--color-text-secondary, #64748b); margin-top: 0.25rem; }

/* Pipeline flow */
.pipeline-flow { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; justify-content: center; padding: 1rem 0; }
.pipeline-tier { text-align: center; }
.tier-label { font-size: 0.75rem; color: var(--color-text-secondary, #64748b); margin-bottom: 0.25rem; }
.tier-box { padding: 0.75rem 1rem; border-radius: 8px; min-width: 90px; }
.tier-value { font-size: 1.25rem; font-weight: 700; display: block; }
.tier-name { font-size: 0.75rem; opacity: 0.8; }
.tier-recht { background: #dbeafe; color: #1d4ed8; }
.tier-beweis { background: #fef3c7; color: #92400e; }
.tier-obsiegen { background: #d1fae5; color: #065f46; }
.tier-eintreib { background: #ede9fe; color: #5b21b6; }
.tier-gesamt { background: #f3e8ff; color: #7c3aed; }
.pipeline-arrow { font-size: 1.25rem; font-weight: 700; color: var(--color-text-secondary, #64748b); }
.pipeline-detail .tier-box { min-width: 70px; padding: 0.5rem 0.75rem; }
.pipeline-detail .tier-value { font-size: 1rem; }

.pipeline-ev-row { display: flex; gap: 1.5rem; flex-wrap: wrap; }
.ev-card { display: flex; align-items: center; gap: 0.5rem; }
.ev-label { font-size: 0.85rem; color: var(--color-text-secondary, #64748b); }
.ev-value { font-weight: 700; font-size: 1.1rem; }

/* Data tables */
.data-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.data-table th, .data-table td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--color-border, #e2e8f0); }
.data-table th { font-weight: 600; color: var(--color-text-secondary, #64748b); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }

/* Cases table */
.cases-table-wrap { overflow-x: auto; }
.cases-table { min-width: 900px; }
.case-row.clickable { cursor: pointer; transition: background 0.15s; }
.case-row.clickable:hover { background: var(--color-bg-hover, #f1f5f9); }
.case-title-cell { max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-test { border-left: 3px solid #a855f7; }
.row-real { border-left: 3px solid #3b82f6; }

/* Badges */
.badge { font-size: 0.65rem; padding: 0.15rem 0.4rem; border-radius: 4px; font-weight: 700; margin-right: 0.25rem; text-transform: uppercase; }
.badge-test { background: #f3e8ff; color: #7c3aed; }
.badge-real { background: #dbeafe; color: #2563eb; }

/* Probability pills */
.prob-pill { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-weight: 600; font-size: 0.85rem; }
.prob-high { background: #dcfce7; color: #166534; }
.prob-mid { background: #fef3c7; color: #92400e; }
.prob-low { background: #fecaca; color: #991b1b; }

/* Outcome badges */
.outcome-badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
.outcome-won { background: #dcfce7; color: #166534; }
.outcome-lost { background: #fecaca; color: #991b1b; }
.outcome-settled { background: #fef3c7; color: #92400e; }
.outcome-withdrawn { background: #e2e8f0; color: #475569; }

/* Pagination */
.pagination { display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-top: 1rem; }
.pagination button { padding: 0.4rem 0.8rem; border: 1px solid var(--color-border, #e2e8f0); border-radius: 6px; background: var(--color-bg-card, #fff); cursor: pointer; }
.pagination button:disabled { opacity: 0.4; cursor: default; }
.page-info { font-size: 0.85rem; color: var(--color-text-secondary, #64748b); }

/* Filter row */
.section-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem; }
.filter-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.search-input { padding: 0.4rem 0.75rem; border: 1px solid var(--color-border, #e2e8f0); border-radius: 6px; font-size: 0.9rem; min-width: 180px; }
.filter-select { padding: 0.4rem 0.75rem; border: 1px solid var(--color-border, #e2e8f0); border-radius: 6px; font-size: 0.85rem; }

/* Test form */
.test-form { max-width: 800px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.form-group { display: flex; flex-direction: column; gap: 0.25rem; }
.form-group.span-2 { grid-column: span 2; }
.form-group label { font-size: 0.85rem; font-weight: 600; color: var(--color-text-secondary, #64748b); }
.form-group input, .form-group select, .form-group textarea {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
  font-size: 0.9rem;
}
.slider-group { display: flex; align-items: center; gap: 0.75rem; }
.slider-group input[type="range"] { flex: 1; }
.slider-value { font-weight: 700; min-width: 3rem; text-align: center; padding: 0.15rem 0.5rem; border-radius: 8px; }

.test-preview { background: var(--color-bg-hover, #f8fafc); padding: 1rem; border-radius: 8px; border: 1px solid var(--color-border, #e2e8f0); }
.test-preview h3 { font-size: 0.9rem; margin-bottom: 0.5rem; }
.preview-row { display: flex; gap: 1.5rem; flex-wrap: wrap; font-weight: 600; }
.test-result { padding: 0.75rem; background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; }

.form-actions { display: flex; gap: 0.75rem; }

/* Buttons */
.btn { padding: 0.6rem 1.2rem; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.9rem; transition: opacity 0.15s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-secondary { background: #e2e8f0; color: #334155; }
.btn-secondary:hover:not(:disabled) { background: #cbd5e1; }

.admin-actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }

/* Bayes chart */
.bayes-chart { padding: 0.5rem 0; }
.bayes-chart-header { display: flex; gap: 1.5rem; margin-bottom: 0.75rem; }
.chart-legend-item { display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot-cb { background: #3b82f6; }
.dot-pf { background: #10b981; }
.bayes-bars { display: flex; flex-direction: column; gap: 0.35rem; }
.bayes-bar-group { display: flex; align-items: center; gap: 0.5rem; }
.bar-label { min-width: 55px; font-size: 0.8rem; color: var(--color-text-secondary, #64748b); text-align: right; }
.bar-container { flex: 1; height: 22px; background: var(--color-bg-hover, #f1f5f9); border-radius: 4px; overflow: hidden; }
.bar { height: 100%; border-radius: 4px; display: flex; align-items: center; padding-left: 0.4rem; font-size: 0.75rem; font-weight: 600; color: #fff; min-width: 30px; transition: width 0.3s; }
.bar-cb { background: #3b82f6; }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 1rem; }
.modal-content { background: var(--color-bg-card, #fff); border-radius: 12px; padding: 2rem; max-width: 800px; width: 100%; max-height: 90vh; overflow-y: auto; position: relative; }
.modal-close { position: absolute; top: 0.75rem; right: 1rem; background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--color-text-secondary, #64748b); }
.modal-close:hover { color: #000; }

.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-top: 1rem; }
.detail-section h3 { font-size: 1rem; margin-bottom: 0.5rem; color: var(--color-text-secondary, #64748b); }
.detail-section h4 { font-size: 0.9rem; margin-bottom: 0.5rem; color: var(--color-text-secondary, #64748b); }
.detail-row { display: flex; gap: 0.5rem; margin-bottom: 0.35rem; font-size: 0.9rem; }
.detail-label { font-weight: 600; min-width: 120px; color: var(--color-text-secondary, #64748b); }

/* Element scores */
.element-bar-list { display: flex; flex-direction: column; gap: 0.4rem; }
.element-bar-row { display: flex; align-items: center; gap: 0.5rem; }
.element-label { min-width: 110px; font-size: 0.85rem; }
.element-bar-container { flex: 1; height: 18px; background: var(--color-bg-hover, #f1f5f9); border-radius: 4px; overflow: hidden; }
.element-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.element-bar.prob-high { background: #22c55e; }
.element-bar.prob-mid { background: #f59e0b; }
.element-bar.prob-low { background: #ef4444; }
.element-value { min-width: 35px; font-size: 0.85rem; font-weight: 600; text-align: right; }

@media (max-width: 768px) {
  .form-grid { grid-template-columns: 1fr; }
  .form-group.span-2 { grid-column: span 1; }
  .detail-grid { grid-template-columns: 1fr; }
  .pipeline-flow { gap: 0.4rem; }
  .tier-box { min-width: 65px; padding: 0.5rem; }
}
</style>
