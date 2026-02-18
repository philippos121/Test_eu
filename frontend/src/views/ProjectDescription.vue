<template>
  <div class="page">
    <div class="container project-page">
      <button class="btn btn-outline mb-3" @click="$router.push('/')">
        &larr; {{ t('project.backToHome') }}
      </button>

      <div class="hero-section fade-in">
        <h1>{{ t('project.title') }}</h1>
        <p class="subtitle">{{ t('project.subtitle') }}</p>
      </div>

      <!-- Market Opportunity -->
      <section class="card fade-in mt-3">
        <h2>{{ t('project.whatIsThis') }}</h2>
        <p>{{ t('project.whatIsThisText') }}</p>
        <div class="kpi-row mt-2">
          <div class="kpi-card">
            <div class="kpi-value">5.000 EUR</div>
            <div class="kpi-label">Bagatellgrenze</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-value">27</div>
            <div class="kpi-label">EU-Mitgliedstaaten</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-value">24</div>
            <div class="kpi-label">Amtssprachen</div>
          </div>
        </div>
      </section>

      <!-- Product Architecture -->
      <section class="card fade-in mt-2">
        <h2>{{ t('project.howItWorks') }}</h2>
        <p>{{ t('project.howItWorksText') }}</p>
        <div class="process-flow mt-2">
          <div class="flow-step">
            <div class="flow-icon">1</div>
            <h3>{{ t('project.step1TitleInv') }}</h3>
            <p>{{ t('project.step1DescInv') }}</p>
          </div>
          <div class="flow-arrow">&rarr;</div>
          <div class="flow-step">
            <div class="flow-icon">2</div>
            <h3>{{ t('project.step2TitleInv') }}</h3>
            <p>{{ t('project.step2DescInv') }}</p>
          </div>
          <div class="flow-arrow">&rarr;</div>
          <div class="flow-step">
            <div class="flow-icon">3</div>
            <h3>{{ t('project.step3TitleInv') }}</h3>
            <p>{{ t('project.step3DescInv') }}</p>
          </div>
          <div class="flow-arrow">&rarr;</div>
          <div class="flow-step">
            <div class="flow-icon">4</div>
            <h3>{{ t('project.step4TitleInv') }}</h3>
            <p>{{ t('project.step4DescInv') }}</p>
          </div>
        </div>
      </section>

      <!-- App-Based Customer Access -->
      <section class="card fade-in mt-2">
        <h2>{{ t('project.appAccess') }}</h2>
        <p>{{ t('project.appAccessText') }}</p>
        <div class="arch-diagram mt-2">
          <div class="arch-box arch-app">
            <div class="arch-icon">App</div>
            <h4>Kunden-App</h4>
            <p>Fallerfassung, KI-Chat, Dokumenten-Upload, Statusverfolgung</p>
          </div>
          <div class="arch-arrow">&rarr;</div>
          <div class="arch-box arch-backend">
            <div class="arch-icon">API</div>
            <h4>Backend</h4>
            <p>KI-Agent, Scoring, Formularerstellung, Statistik</p>
          </div>
          <div class="arch-arrow">&rarr;</div>
          <div class="arch-box arch-portal">
            <div class="arch-icon">Portal</div>
            <h4>Admin-Portal</h4>
            <p>Fallmanagement, Risikobewertung, Priorensteuerung</p>
          </div>
        </div>
      </section>

      <!-- Risk Assessment / Probability -->
      <section class="card fade-in mt-2">
        <h2>{{ t('project.probability') }}</h2>
        <p>{{ t('project.probabilityText') }}</p>

        <div class="prob-diagram mt-2">
          <h3>Entscheidungsbaum der Erfolgswahrscheinlichkeit</h3>
          <div class="tree">
            <div class="tree-node root">
              <div class="node-label">p<sub>cash</sub></div>
            </div>
            <div class="tree-level">
              <div class="tree-branch">
                <div class="tree-node">
                  <div class="node-label">p<sub>served</sub></div>
                  <div class="node-desc">Zustellungsrate<br/><small>~70% (ESCP)</small></div>
                </div>
              </div>
              <span class="tree-op">&times;</span>
              <div class="tree-branch">
                <div class="tree-node">
                  <div class="node-label">p<sub>favorable</sub></div>
                  <div class="node-desc">Vergleich / Versäumnis / Sieg</div>
                </div>
              </div>
              <span class="tree-op">&times;</span>
              <div class="tree-branch">
                <div class="tree-node">
                  <div class="node-label">p<sub>collect</sub></div>
                  <div class="node-desc">Inkasso-Erfolg<br/><small>adj. Zahlungsfähigkeit</small></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Statistical Methodology -->
      <section class="card fade-in mt-2">
        <h2>{{ t('project.bayesian') }}</h2>
        <p>{{ t('project.bayesianText') }}</p>

        <div class="bayes-visual mt-2">
          <div class="bayes-step">
            <div class="bayes-icon">&#945;, &#946;</div>
            <h4>Prior</h4>
            <p>Ausgangswissen als Beta-Verteilung Beta(&alpha;, &beta;)</p>
          </div>
          <div class="bayes-arrow">&rarr;</div>
          <div class="bayes-step">
            <div class="bayes-icon">+n</div>
            <h4>Beobachtung</h4>
            <p>Abgeschlossene Fälle liefern Erfolge / Misserfolge</p>
          </div>
          <div class="bayes-arrow">&rarr;</div>
          <div class="bayes-step">
            <div class="bayes-icon">&#945;', &#946;'</div>
            <h4>Posterior</h4>
            <p>Aktualisierte Schätzung Beta(&alpha;+s, &beta;+f)</p>
          </div>
        </div>
      </section>

      <!-- Unit Economics / Expected Value -->
      <section class="card fade-in mt-2">
        <h2>{{ t('project.expectedValue') }}</h2>
        <p>{{ t('project.expectedValueText') }}</p>

        <div class="ev-example mt-2">
          <h3>Beispielrechnung (Betreibersicht)</h3>
          <table class="ev-table">
            <tbody>
              <tr>
                <td>Forderungsbetrag</td>
                <td class="text-right"><strong>3.000,00 EUR</strong></td>
              </tr>
              <tr>
                <td>Erfolgswahrscheinlichkeit (p<sub>cash</sub>)</td>
                <td class="text-right">65%</td>
              </tr>
              <tr>
                <td>Erwartete Zahlung</td>
                <td class="text-right">1.950,00 EUR</td>
              </tr>
              <tr class="sep">
                <td>Gerichtsgebühren</td>
                <td class="text-right danger">-105,00 EUR</td>
              </tr>
              <tr>
                <td>Zustellungskosten</td>
                <td class="text-right danger">-75,00 EUR</td>
              </tr>
              <tr>
                <td>Provision (30% bei Erfolg)</td>
                <td class="text-right danger">-585,00 EUR</td>
              </tr>
              <tr class="total">
                <td><strong>Erwarteter Netto-Ertrag (Betreiber)</strong></td>
                <td class="text-right success"><strong>1.185,00 EUR</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Revenue Model -->
      <section class="card fade-in mt-2">
        <h2>{{ t('project.commission') }}</h2>
        <p>{{ t('project.commissionText') }}</p>

        <div class="commission-highlights mt-2">
          <div class="highlight-card">
            <div class="highlight-value">30%</div>
            <div class="highlight-label">Provision bei Erfolg</div>
          </div>
          <div class="highlight-card">
            <div class="highlight-value">&ge; 80%</div>
            <div class="highlight-label">Min. Erfolgswahrscheinlichkeit</div>
          </div>
          <div class="highlight-card">
            <div class="highlight-value">0 EUR</div>
            <div class="highlight-label">Kostenrisiko Kunde</div>
          </div>
        </div>
      </section>

      <!-- Scalability -->
      <section class="card fade-in mt-2 mb-3">
        <h2>{{ t('project.scalability') }}</h2>
        <p>{{ t('project.scalabilityText') }}</p>
        <div class="scale-features mt-2">
          <div class="scale-item">
            <strong>Mehrsprachig</strong>
            <p>24 EU-Amtssprachen, automatische Spracherkennung</p>
          </div>
          <div class="scale-item">
            <strong>Standardisiert</strong>
            <p>EU-weit einheitliches Verfahren nach VO (EG) Nr. 861/2007</p>
          </div>
          <div class="scale-item">
            <strong>Vollautomatisiert</strong>
            <p>KI-gestützte Sachverhaltsaufnahme, Formularerstellung, Risikobewertung</p>
          </div>
          <div class="scale-item">
            <strong>Adaptive Statistik</strong>
            <p>Wahrscheinlichkeitsschätzungen verbessern sich mit jeder Fallentscheidung</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { useI18nStore } from '../stores/i18n'
const { t } = useI18nStore()
</script>

<style scoped>
.project-page {
  max-width: 900px;
}

.hero-section {
  text-align: center;
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
  color: white;
  padding: 48px 32px;
  border-radius: var(--radius-lg);
}

.hero-section h1 {
  font-size: 2rem;
  margin-bottom: 8px;
}

.subtitle {
  opacity: 0.85;
  font-size: 1.1rem;
}

/* KPI Row */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
}

.kpi-card {
  text-align: center;
  padding: 20px 12px;
  background: var(--bg);
  border-radius: var(--radius);
  border: 2px solid var(--primary);
}

.kpi-value {
  font-size: 1.6rem;
  font-weight: 800;
  color: var(--primary);
}

.kpi-label {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* Process Flow */
.process-flow {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.flow-step {
  flex: 1;
  min-width: 140px;
  max-width: 200px;
  text-align: center;
  padding: 16px 8px;
}

.flow-icon {
  width: 40px;
  height: 40px;
  background: var(--primary);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  margin: 0 auto 8px;
}

.flow-step h3 { font-size: 0.9rem; margin-bottom: 4px; }
.flow-step p { font-size: 0.8rem; color: var(--text-secondary); }

.flow-arrow {
  align-self: center;
  font-size: 1.5rem;
  color: var(--text-light);
  padding-top: 8px;
}

/* Architecture Diagram */
.arch-diagram {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

.arch-box {
  flex: 1;
  min-width: 160px;
  max-width: 220px;
  text-align: center;
  padding: 20px 12px;
  border-radius: var(--radius);
  border: 2px solid var(--border);
}

.arch-app { border-color: var(--success); background: rgba(16, 185, 129, 0.05); }
.arch-backend { border-color: var(--primary); background: rgba(79, 70, 229, 0.05); }
.arch-portal { border-color: var(--warning); background: rgba(245, 158, 11, 0.05); }

.arch-icon {
  font-size: 1.2rem;
  font-weight: 800;
  color: var(--primary);
  margin-bottom: 8px;
}

.arch-app .arch-icon { color: var(--success); }
.arch-portal .arch-icon { color: var(--warning); }

.arch-box h4 { font-size: 0.95rem; margin-bottom: 4px; }
.arch-box p { font-size: 0.78rem; color: var(--text-secondary); }
.arch-arrow { font-size: 1.5rem; color: var(--text-light); }

/* Probability tree */
.prob-diagram {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 24px;
  text-align: center;
}

.prob-diagram h3 { font-size: 1rem; margin-bottom: 16px; }

.tree-level {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.tree-node {
  background: white;
  border: 2px solid var(--primary);
  border-radius: var(--radius);
  padding: 12px 16px;
  min-width: 120px;
}

.tree-node.root {
  background: var(--primary);
  color: white;
  margin-bottom: 16px;
}

.node-label { font-weight: 700; font-size: 1rem; }
.node-desc { font-size: 0.78rem; color: var(--text-secondary); margin-top: 4px; }
.tree-op { font-size: 1.4rem; font-weight: 700; color: var(--primary); }

/* Bayes visual */
.bayes-visual {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

.bayes-step {
  text-align: center;
  flex: 1;
  min-width: 140px;
  max-width: 200px;
  padding: 16px;
  background: var(--bg);
  border-radius: var(--radius);
}

.bayes-icon {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary);
  margin-bottom: 8px;
}

.bayes-step h4 { font-size: 0.95rem; margin-bottom: 4px; }
.bayes-step p { font-size: 0.8rem; color: var(--text-secondary); }
.bayes-arrow { font-size: 1.5rem; color: var(--text-light); }

/* EV table */
.ev-example {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 24px;
}

.ev-example h3 { font-size: 1rem; margin-bottom: 12px; }

.ev-table {
  width: 100%;
  border-collapse: collapse;
}

.ev-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem;
}

.ev-table .text-right { text-align: right; }
.ev-table .danger { color: var(--danger); }
.ev-table .success { color: var(--success); }

.ev-table .sep td { border-top: 2px solid var(--border); }
.ev-table .total td {
  border-top: 2px solid var(--primary);
  border-bottom: none;
  font-size: 1rem;
}

/* Commission highlights */
.commission-highlights {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}

.highlight-card {
  text-align: center;
  padding: 24px 16px;
  background: var(--bg);
  border-radius: var(--radius);
  border: 2px solid var(--primary);
}

.highlight-value {
  font-size: 2rem;
  font-weight: 800;
  color: var(--primary);
}

.highlight-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* Scale features */
.scale-features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.scale-item {
  padding: 16px;
  background: var(--bg);
  border-radius: var(--radius);
  border-left: 3px solid var(--primary);
}

.scale-item strong {
  display: block;
  font-size: 0.95rem;
  margin-bottom: 4px;
}

.scale-item p {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin: 0;
}
</style>
