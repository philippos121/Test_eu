<template>
  <div id="app">
    <Navbar v-if="auth.isAuthenticated" />
    <router-view />
  </div>
</template>

<script setup>
import { useAuthStore } from './stores/auth'
import Navbar from './components/Navbar.vue'

const auth = useAuthStore()
</script>
