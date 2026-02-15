import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../services/api'

export const useCaseStore = defineStore('case', () => {
  const cases = ref([])
  const currentCase = ref(null)
  const messages = ref([])
  const documents = ref([])
  const loading = ref(false)

  async function fetchCases() {
    loading.value = true
    try {
      const { data } = await api.get('/cases')
      cases.value = data
    } finally {
      loading.value = false
    }
  }

  async function createCase(title) {
    const { data } = await api.post('/cases', { title })
    cases.value.unshift(data)
    return data
  }

  async function fetchCase(id) {
    const { data } = await api.get(`/cases/${id}`)
    currentCase.value = data
    return data
  }

  async function fetchMessages(caseId) {
    const { data } = await api.get(`/cases/${caseId}/chat`)
    messages.value = data
    return data
  }

  async function sendMessage(caseId, content) {
    loading.value = true
    try {
      const { data } = await api.post(`/cases/${caseId}/chat`, { content })
      messages.value.push(data.message)
      currentCase.value = data.case
      return data
    } finally {
      loading.value = false
    }
  }

  async function fetchDocuments(caseId) {
    const { data } = await api.get(`/cases/${caseId}/documents`)
    documents.value = data
    return data
  }

  async function generateFormA(caseId) {
    const { data } = await api.post(`/cases/${caseId}/documents/generate-form-a`)
    documents.value.unshift(data)
    return data
  }

  function getDownloadUrl(caseId, docId) {
    const token = localStorage.getItem('token')
    return `/api/cases/${caseId}/documents/${docId}/download?token=${token}`
  }

  return {
    cases, currentCase, messages, documents, loading,
    fetchCases, createCase, fetchCase, fetchMessages,
    sendMessage, fetchDocuments, generateFormA, getDownloadUrl,
  }
})
