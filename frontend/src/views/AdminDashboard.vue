<template>
  <div class="page">
    <div class="container">
      <div class="page-header fade-in">
        <h1>Admin Dashboard</h1>
        <router-link to="/admin/priors" class="btn btn-outline">Priors konfigurieren</router-link>
      </div>

      <div class="card fade-in">
        <div class="card-header">
          <h2>Alle Fälle</h2>
          <span class="text-secondary">{{ store.cases.length }} Fälle</span>
        </div>

        <div v-if="store.loading" class="text-center mt-2">
          <p class="loading-dots text-secondary">Laden</p>
        </div>

        <table v-else class="admin-table">
          <thead>
            <tr>
              <th>Titel</th>
              <th>Kläger</th>
              <th>Beklagter</th>
              <th>Betrag</th>
              <th>Status</th>
              <th>LLM %</th>
              <th>p(cash)</th>
              <th>Erstellt</th>
              <th>Aktion</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in store.cases" :key="c.id">
              <td class="cell-title">{{ c.title }}</td>
              <td>{{ c.claimant_name || '—' }}</td>
              <td>{{ c.defendant_name || '—' }}</td>
              <td>{{ c.claim_amount ? `${c.claim_amount.toFixed(2)} ${c.claim_currency || 'EUR'}` : '—' }}</td>
              <td><span :class="['badge', `badge-${c.status}`]">{{ statusLabel(c.status) }}</span></td>
              <td>{{ c.success_probability != null ? (c.success_probability * 100).toFixed(0) + '%' : '—' }}</td>
              <td>
                <span v-if="c.p_cash_success != null" :class="probClass(c.p_cash_success)">
                  {{ (c.p_cash_success * 100).toFixed(0) }}%
                </span>
                <span v-else class="text-secondary">—</span>
              </td>
              <td class="text-secondary">{{ formatDate(c.created_at) }}</td>
              <td>
                <router-link :to="`/admin/cases/${c.id}/score`" class="btn btn-sm btn-primary">Score</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useAdminStore } from '../stores/admin'

const store = useAdminStore()

const STATUS_LABELS = {
  intake: 'Aufnahme',
  applicability_check: 'Anwendbarkeit',
  case_assessment: 'Fallprüfung',
  evidence_collection: 'Beweisaufnahme',
  form_generation: 'Formular',
  completed: 'Abgeschlossen',
  rejected: 'Abgelehnt',
}

function statusLabel(s) { return STATUS_LABELS[s] || s }
function probClass(p) {
  if (p >= 0.5) return 'prob-high'
  if (p >= 0.25) return 'prob-medium'
  return 'prob-low'
}
function formatDate(d) {
  return new Date(d).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

onMounted(() => store.fetchCases())
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.page-header h1 { font-size: 1.4rem; }

.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.admin-table th {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 2px solid var(--border);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.admin-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.admin-table tbody tr:hover {
  background: #f8f9fa;
}
.cell-title {
  font-weight: 500;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.prob-high { color: var(--success); font-weight: 600; }
.prob-medium { color: var(--warning); font-weight: 600; }
.prob-low { color: var(--danger); font-weight: 600; }
</style>
