<template>
  <header class="navbar">
    <div class="navbar-inner container">
      <router-link to="/" class="navbar-brand">
        <img :src="logoUrl" alt="AI:ssociate" class="brand-logo" />
        <span class="brand-text">EU-Bagatellverfahren</span>
      </router-link>

      <nav class="navbar-links">
        <router-link to="/" class="nav-link">Meine Fälle</router-link>
      </nav>

      <div class="navbar-user">
        <span class="user-name" v-if="auth.user">{{ auth.user.full_name }}</span>
        <button class="btn btn-sm btn-outline" @click="handleLogout">Abmelden</button>
      </div>
    </div>
  </header>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import logoUrl from '../assets/images/logo.jpg'

const auth = useAuthStore()
const router = useRouter()

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--header-height);
  background: var(--primary-dark);
  color: white;
  z-index: 100;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.navbar-inner {
  display: flex;
  align-items: center;
  height: 100%;
  gap: 32px;
}

.navbar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: white;
  font-weight: 700;
  font-size: 1.05rem;
  text-decoration: none;
}

.brand-logo {
  height: 32px;
  width: auto;
  object-fit: contain;
  border-radius: 4px;
}

.navbar-links {
  flex: 1;
}

.nav-link {
  color: rgba(255, 255, 255, 0.8);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
  padding: 6px 12px;
  border-radius: var(--radius);
  transition: all 0.2s;
}

.nav-link:hover,
.nav-link.router-link-exact-active {
  color: white;
  background: rgba(255, 255, 255, 0.1);
  text-decoration: none;
}

.navbar-user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-name {
  font-size: 0.85rem;
  opacity: 0.9;
}

.navbar-user .btn-outline {
  color: rgba(255, 255, 255, 0.9);
  border-color: rgba(255, 255, 255, 0.3);
}

.navbar-user .btn-outline:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.6);
  color: white;
}
</style>
