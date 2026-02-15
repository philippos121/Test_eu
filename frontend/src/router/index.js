import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { auth: true },
  },
  {
    path: '/cases/:id',
    name: 'CaseDetail',
    component: () => import('../views/CaseDetail.vue'),
    meta: { auth: true },
  },
  {
    path: '/admin',
    name: 'AdminDashboard',
    component: () => import('../views/AdminDashboard.vue'),
    meta: { auth: true },
  },
  {
    path: '/admin/cases/:id/score',
    name: 'AdminCaseScore',
    component: () => import('../views/AdminCaseScore.vue'),
    meta: { auth: true },
  },
  {
    path: '/admin/priors',
    name: 'AdminPriors',
    component: () => import('../views/AdminPriors.vue'),
    meta: { auth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.auth && !token) {
    return next('/login')
  }
  if (to.meta.guest && token) {
    return next('/')
  }
  next()
})

export default router
