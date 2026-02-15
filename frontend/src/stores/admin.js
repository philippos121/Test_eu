import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../services/api'

export const useAdminStore = defineStore('admin', () => {
  const cases = ref([])
  const currentCase = ref(null)
  const currentScore = ref(null)
  const scoreHistory = ref([])
  const events = ref([])
  const traces = ref([])
  const priors = ref([])
  const loading = ref(false)

  // Cases
  async function fetchCases() {
    loading.value = true
    try {
      const { data } = await api.get('/admin/cases')
      cases.value = data
    } finally {
      loading.value = false
    }
  }

  async function fetchCase(id) {
    const { data } = await api.get(`/admin/cases/${id}`)
    currentCase.value = data
    return data
  }

  // Score
  async function fetchScore(caseId) {
    try {
      const { data } = await api.get(`/admin/cases/${caseId}/score`)
      currentScore.value = data
      return data
    } catch (err) {
      if (err.response?.status === 404) {
        currentScore.value = null
        return null
      }
      throw err
    }
  }

  async function computeScore(caseId) {
    loading.value = true
    try {
      const { data } = await api.post(`/admin/cases/${caseId}/score`)
      currentScore.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function fetchScoreHistory(caseId) {
    const { data } = await api.get(`/admin/cases/${caseId}/score/history`)
    scoreHistory.value = data
    return data
  }

  // Events
  async function fetchEvents(caseId) {
    const { data } = await api.get(`/admin/cases/${caseId}/events`)
    events.value = data
    return data
  }

  async function addEvent(caseId, eventType, payload = {}) {
    const { data } = await api.post(`/admin/cases/${caseId}/events`, {
      event_type: eventType,
      payload,
    })
    events.value.push(data)
    return data
  }

  // Traces
  async function fetchTraces(caseId) {
    const { data } = await api.get(`/admin/cases/${caseId}/traces`)
    traces.value = data
    return data
  }

  // Priors
  async function fetchPriors() {
    const { data } = await api.get('/admin/priors')
    priors.value = data
    return data
  }

  async function createPrior(body) {
    const { data } = await api.post('/admin/priors', body)
    priors.value.push(data)
    return data
  }

  async function updatePrior(id, body) {
    const { data } = await api.put(`/admin/priors/${id}`, body)
    const idx = priors.value.findIndex(p => p.id === id)
    if (idx !== -1) priors.value[idx] = data
    return data
  }

  async function deletePrior(id) {
    await api.delete(`/admin/priors/${id}`)
    priors.value = priors.value.filter(p => p.id !== id)
  }

  return {
    cases, currentCase, currentScore, scoreHistory, events, traces, priors, loading,
    fetchCases, fetchCase,
    fetchScore, computeScore, fetchScoreHistory,
    fetchEvents, addEvent,
    fetchTraces,
    fetchPriors, createPrior, updatePrior, deletePrior,
  }
})
